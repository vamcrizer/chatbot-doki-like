"""
Download DavidAU models — file-by-file with retry.
Fixes the 98% stuck issue by downloading each safetensors individually.
"""
import os
import time
from huggingface_hub import HfApi, hf_hub_download

DEST = os.path.expanduser("~/dokichat/models")

MODELS = [
    {
        "repo": "DavidAU/Qwen3.5-4B-Claude-4.6-OS-Auto-Variable-HERETIC-UNCENSORED-THINKING",
        "dir": "qwen3.5-4b-davidau",
        "label": "4B",
    },
    {
        "repo": "DavidAU/Qwen3.5-9B-Claude-4.6-HighIQ-INSTRUCT-HERETIC-UNCENSORED",
        "dir": "qwen3.5-9b-davidau",
        "label": "9B",
    },
]

MAX_RETRIES = 10
RETRY_DELAY = 15


def download_file(repo_id, filename, local_dir, label):
    dest_path = os.path.join(local_dir, filename)
    if os.path.exists(dest_path):
        size_gb = os.path.getsize(dest_path) / (1024**3)
        if size_gb > 0.01:  # >10MB = likely complete
            print(f"  ✅ {filename} already exists ({size_gb:.2f} GB), skipping")
            return True

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  [{label}] Downloading {filename} (attempt {attempt})...")
            t0 = time.time()
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=local_dir,
                force_download=(attempt > 1),  # force on retry
            )
            elapsed = time.time() - t0
            size_gb = os.path.getsize(dest_path) / (1024**3)
            print(f"  ✅ {filename}: {size_gb:.2f} GB in {elapsed:.0f}s")
            return True
        except KeyboardInterrupt:
            print(f"\n⚠️  Cancelled")
            return False
        except Exception as e:
            print(f"  ❌ Attempt {attempt}: {e}")
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * attempt
                print(f"     Retry in {wait}s...")
                time.sleep(wait)
    return False


def download_model(repo_id, local_dir, label):
    os.makedirs(local_dir, exist_ok=True)

    # List all files in repo
    api = HfApi()
    files = list(api.list_repo_files(repo_id))

    # Sort: small files first, safetensors last
    safetensors = sorted([f for f in files if f.endswith('.safetensors')])
    others = sorted([f for f in files if not f.endswith('.safetensors')])

    print(f"\n{'='*60}")
    print(f"[{label}] {repo_id}")
    print(f"  Files: {len(others)} config + {len(safetensors)} safetensors")
    print(f"  Dest:  {local_dir}")
    print(f"{'='*60}")

    # Download config files first (small, fast)
    print(f"\n  --- Config files ---")
    for f in others:
        if not download_file(repo_id, f, local_dir, label):
            return False

    # Download safetensors one by one (large)
    print(f"\n  --- Model weights ---")
    for f in safetensors:
        if not download_file(repo_id, f, local_dir, label):
            return False

    return True


def verify(local_dir, label):
    if not os.path.isdir(local_dir):
        print(f"  [{label}] ❌ Directory not found")
        return
    sf = [f for f in os.listdir(local_dir) if f.endswith('.safetensors')]
    total = sum(os.path.getsize(os.path.join(local_dir, f)) for f in sf)
    print(f"  [{label}] {len(sf)} safetensors, {total/(1024**3):.1f} GB")


if __name__ == "__main__":
    print(f"🚀 DokiChat Model Downloader (file-by-file)")
    print(f"   {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    for m in MODELS:
        local_dir = os.path.join(DEST, m["dir"])
        ok = download_model(m["repo"], local_dir, m["label"])
        if not ok:
            print(f"\n[{m['label']}] Failed. Run again to resume.")
            break

    print(f"\n{'='*60}")
    print("VERIFY")
    for m in MODELS:
        verify(os.path.join(DEST, m["dir"]), m["label"])
    print("Done.")
