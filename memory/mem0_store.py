"""
Mem0 Store — Qdrant in-memory + Ollama embeddings for DokiChat.
Adapted from agent-smart-memo's architecture.

Uses:
- Qdrant in-memory (via qdrant-client, no Docker needed)
- Ollama HTTP API for embeddings (snowflake-arctic-embed)
- JSON file backup for persistence across restarts
"""
import json
import os
import uuid
import httpx
from datetime import datetime
from pathlib import Path
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
)

# ── Ollama Embedding Client ──────────────────────────────────

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "snowflake-arctic-embed2")
EMBED_DIM = 1024  # snowflake-arctic-embed default dimension


def ollama_embed(text: str) -> list[float]:
    """Get embedding vector from Ollama API."""
    resp = httpx.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def ollama_embed_batch(texts: list[str]) -> list[list[float]]:
    """Batch embedding — calls sequentially (Ollama doesn't support batch)."""
    return [ollama_embed(t) for t in texts]


def check_ollama_health() -> bool:
    """Check if Ollama is running and model is available."""
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        if resp.status_code != 200:
            return False
        models = [m["name"] for m in resp.json().get("models", [])]
        # Check if our model exists (with or without :latest tag)
        return any(EMBED_MODEL in m for m in models)
    except Exception:
        return False


# ── Memory Store ─────────────────────────────────────────────

COLLECTION_NAME = "dokichat_memories"
MEMORY_DIR = Path("memory/sessions")


class MemoryStore:
    """Qdrant in-memory + Ollama embeddings. JSON backup for persistence."""

    def __init__(self, user_id: str, character_id: str):
        self.user_id = user_id
        self.character_id = character_id
        self.scope = f"{user_id}_{character_id}"
        self._ollama_ok = check_ollama_health()

        # Init Qdrant in-memory
        self.qdrant = QdrantClient(":memory:")
        dim = EMBED_DIM
        if self._ollama_ok:
            # Probe actual dimension from model
            try:
                test_vec = ollama_embed("test")
                dim = len(test_vec)
            except Exception:
                pass

        self.dim = dim
        self.qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
        )

        # JSON backup
        self._json_path = MEMORY_DIR / f"{self.scope}.json"
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self._data: dict = {"memories": [], "session_summary": ""}
        self._load_json()
        self._reindex_all()

        if self._ollama_ok:
            print(f"[Mem0] ✅ Ollama + Qdrant ready (dim={self.dim}, model={EMBED_MODEL})")
        else:
            print(f"[Mem0] ⚠️ Ollama unavailable — using keyword search fallback")

    # ── JSON persistence ──────────────────────────────────────

    def _load_json(self):
        if self._json_path.exists():
            self._data = json.loads(self._json_path.read_text(encoding="utf-8"))

    def _save_json(self):
        self._json_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Qdrant indexing ───────────────────────────────────────

    def _reindex_all(self):
        """Re-index all memories from JSON into Qdrant on startup."""
        if not self._ollama_ok or not self._data["memories"]:
            return

        for m in self._data["memories"]:
            try:
                vector = ollama_embed(m["text"])
                self.qdrant.upsert(
                    collection_name=COLLECTION_NAME,
                    points=[PointStruct(
                        id=m["id"],
                        vector=vector,
                        payload={
                            "text": m["text"],
                            "type": m.get("type", "user_fact"),
                            "scope": self.scope,
                            "created_at": m.get("created_at", ""),
                        },
                    )],
                )
            except Exception as e:
                print(f"[Mem0] Reindex error: {e}")

    COSINE_DEDUP_THRESHOLD = 0.92  # strict — Vietnamese short texts have high baseline cosine

    def add(self, facts: list[dict]):
        """Add facts. Each: {text, type, confidence}. Dedup via cosine similarity."""
        for fact in facts:
            # Cosine dedup: embed new fact, compare against existing
            if self._is_duplicate(fact["text"]):
                continue

            mem_id = str(uuid.uuid4())
            entry = {
                "id": mem_id,
                "text": fact["text"],
                "type": fact.get("type", "user_fact"),
                "confidence": fact.get("confidence", 0.8),
                "created_at": datetime.now().isoformat(),
            }
            self._data["memories"].append(entry)

            # Index in Qdrant if Ollama available
            if self._ollama_ok:
                try:
                    vector = ollama_embed(fact["text"])
                    self.qdrant.upsert(
                        collection_name=COLLECTION_NAME,
                        points=[PointStruct(
                            id=mem_id,
                            vector=vector,
                            payload={
                                "text": fact["text"],
                                "type": fact.get("type", "user_fact"),
                                "scope": self.scope,
                                "created_at": entry["created_at"],
                            },
                        )],
                    )
                except Exception as e:
                    print(f"[Mem0] Embed error: {e}")

        self._save_json()

    def search(self, query: str, top_k: int = 10) -> list[str]:
        """Semantic search if Ollama available, else keyword fallback."""
        if self._ollama_ok:
            try:
                vector = ollama_embed(query)
                results = self.qdrant.query_points(
                    collection_name=COLLECTION_NAME,
                    query=vector,
                    query_filter=Filter(
                        must=[FieldCondition(key="scope", match=MatchValue(value=self.scope))]
                    ),
                    limit=top_k,
                )
                return [
                    r.payload["text"]
                    for r in results.points
                    if r.payload and r.score > 0.2
                ]
            except Exception as e:
                print(f"[Mem0] Search error: {e}, fallback to keyword")

        # Keyword fallback
        return self._keyword_search(query, top_k)

    def get_all(self) -> list[dict]:
        return self._data["memories"]

    def update_summary(self, summary: str):
        self._data["session_summary"] = summary
        self._save_json()

    def get_summary(self) -> str:
        return self._data.get("session_summary", "")

    def clear(self):
        self._data = {"memories": [], "session_summary": ""}
        self._save_json()
        # Recreate Qdrant collection
        self.qdrant.delete_collection(COLLECTION_NAME)
        self.qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
        )

    # ── Internal helpers ──────────────────────────────────────

    COSINE_DEDUP_THRESHOLD = 0.95   # near-identical meaning
    WORD_OVERLAP_THRESHOLD = 0.5    # at least half words shared

    def _is_duplicate(self, new_text: str) -> bool:
        """Hybrid dedup: cosine similarity AND word overlap must both agree.

        Pure cosine fails for short Vietnamese texts (high baseline ~0.90).
        We require BOTH:
          - cosine ≥ 0.95 (very similar meaning), OR
          - cosine ≥ 0.90 AND word overlap ≥ 0.5 (similar meaning + shared words)
        """
        if not self._data["memories"]:
            return False

        new_words = set(new_text.lower().split())

        if self._ollama_ok:
            try:
                new_vec = ollama_embed(new_text)
                results = self.qdrant.query_points(
                    collection_name=COLLECTION_NAME,
                    query=new_vec,
                    query_filter=Filter(
                        must=[FieldCondition(key="scope", match=MatchValue(value=self.scope))]
                    ),
                    limit=3,  # check top 3 candidates
                )
                for r in results.points:
                    if not r.payload:
                        continue
                    existing_text = r.payload.get("text", "")
                    cosine = r.score

                    # Rule 1: Very high cosine = definite duplicate
                    if cosine >= self.COSINE_DEDUP_THRESHOLD:
                        print(f"[Mem0] Dedup (cosine): '{new_text[:40]}' ≈ "
                              f"'{existing_text[:40]}' (cos={cosine:.3f})")
                        return True

                    # Rule 2: High cosine + word overlap = likely duplicate
                    existing_words = set(existing_text.lower().split())
                    if new_words and existing_words:
                        overlap = len(new_words & existing_words) / min(len(new_words), len(existing_words))
                        if cosine >= 0.90 and overlap >= self.WORD_OVERLAP_THRESHOLD:
                            print(f"[Mem0] Dedup (hybrid): '{new_text[:40]}' ≈ "
                                  f"'{existing_text[:40]}' (cos={cosine:.3f}, words={overlap:.2f})")
                            return True

                return False
            except Exception as e:
                print(f"[Mem0] Dedup error: {e}, fallback to word overlap")

        # Pure word overlap fallback (no Ollama)
        for m in self._data["memories"]:
            existing_words = set(m["text"].lower().split())
            if new_words and existing_words:
                overlap = len(new_words & existing_words) / min(len(new_words), len(existing_words))
                if overlap > 0.7:
                    return True
        return False

    def _keyword_search(self, query: str, top_k: int) -> list[str]:
        query_words = set(query.lower().split())
        scored = []
        for m in self._data["memories"]:
            text_words = set(m["text"].lower().split())
            overlap = len(query_words & text_words)
            if overlap > 0:
                scored.append((overlap, m["text"]))
        scored.sort(reverse=True)
        return [text for _, text in scored[:top_k]]


def create_memory_store(user_id: str, character_id: str) -> MemoryStore:
    """Factory — always returns MemoryStore (auto-detects Ollama)."""
    return MemoryStore(user_id, character_id)
