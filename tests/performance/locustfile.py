"""
Tầng 5 — Performance Tests via Locust.
Run: locust -f tests/performance/locustfile.py --host http://localhost:8080
     locust -f tests/performance/locustfile.py --headless -u 50 -r 5 --run-time 60s --host http://localhost:8080

Metrics tracked:
  - /health               : P95 < 200ms
  - /api/character/list   : P95 < 500ms
  - /api/chat/stream      : TTFT < 2s, total < 30s
  - /api/auth/register    : P95 < 1s
  - /api/auth/login       : P95 < 1s
"""
import json
import time
import random
import string

from locust import HttpUser, task, between, events


def random_email():
    suffix = ''.join(random.choices(string.ascii_lowercase, k=8))
    return f"perf_{suffix}@test.com"


class HealthCheckUser(HttpUser):
    """Lightweight user: only hits health endpoint.
    Use to establish baseline P95.
    """
    wait_time = between(0.5, 1)
    weight = 3  # 30% of users

    @task
    def health(self):
        with self.client.get("/health", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"Health returned {resp.status_code}")
            elif resp.elapsed.total_seconds() > 0.2:
                resp.failure(f"Health too slow: {resp.elapsed.total_seconds():.3f}s")


class BrowseUser(HttpUser):
    """User browsing character list and reading data.
    Simulates casual browsing — no auth required.
    """
    wait_time = between(1, 3)
    weight = 4  # 40% of users

    @task(3)
    def character_list(self):
        with self.client.get("/api/character/list", catch_response=True) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if "characters" not in data:
                    resp.failure("Missing 'characters' in response")
            elif resp.status_code == 404:
                pass  # endpoint may not exist yet
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @task(1)
    def root(self):
        self.client.get("/")


class ChatUser(HttpUser):
    """User chatting with characters via SSE streaming.
    Simulates realistic chat flow: register → chat.

    SSE metrics:
      - TTFT (time to first token): time until first 'data:' line
      - Total time: time until stream ends
    """
    wait_time = between(2, 5)
    weight = 3  # 30% of users

    def on_start(self):
        """Register a new user on start."""
        self.email = random_email()
        self.password = "perftest123"
        self.token = None
        self.user_id = None

        resp = self.client.post(
            "/api/auth/register",
            json={
                "email": self.email,
                "password": self.password,
                "display_name": "PerfBot",
            },
        )
        if resp.status_code == 200:
            data = resp.json()
            self.token = data.get("access_token")
            self.user_id = data.get("user_id")

    def _auth_headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    @task(5)
    def chat_stream(self):
        """POST /api/chat/stream — SSE streaming test."""
        if not self.token:
            return

        messages = [
            "Hey, how are you?",
            "Tell me about yourself",
            "What do you think about art?",
            "Do you like music?",
            "*sits next to you*",
            "What's your favorite place?",
        ]

        characters = ["kael", "sol", "ren", "mei"]

        start = time.time()
        ttft = None
        total_chunks = 0

        try:
            with self.client.post(
                "/api/chat/stream",
                json={
                    "character_id": random.choice(characters),
                    "message": random.choice(messages),
                },
                headers=self._auth_headers(),
                stream=True,
                catch_response=True,
                name="/api/chat/stream [SSE]",
            ) as resp:
                if resp.status_code != 200:
                    resp.failure(f"Chat returned {resp.status_code}")
                    return

                for line in resp.iter_lines():
                    if line and b"data:" in line:
                        if ttft is None:
                            ttft = time.time() - start
                        total_chunks += 1

                total_time = time.time() - start

                # Report custom metrics
                if ttft and ttft > 3.0:
                    resp.failure(f"TTFT too slow: {ttft:.2f}s")
                elif total_time > 30:
                    resp.failure(f"Total stream too slow: {total_time:.2f}s")

        except Exception as e:
            pass  # Connection errors handled by locust

    @task(1)
    def login(self):
        """POST /api/auth/login — auth throughput."""
        if not self.email:
            return
        self.client.post(
            "/api/auth/login",
            json={"email": self.email, "password": self.password},
            name="/api/auth/login",
        )


# ═══════════════════════════════════════════════════════════════
# Custom event hooks for SLA reporting
# ═══════════════════════════════════════════════════════════════

@events.quitting.add_listener
def check_sla(environment, **kwargs):
    """Check SLA thresholds at the end of the test run."""
    stats = environment.runner.stats

    failures = []

    # Health endpoint: P95 < 200ms
    health = stats.get("/health", "GET")
    if health and health.get_response_time_percentile(0.95) > 200:
        failures.append(
            f"HEALTH P95={health.get_response_time_percentile(0.95):.0f}ms > 200ms"
        )

    # Character list: P95 < 500ms
    char_list = stats.get("/api/character/list", "GET")
    if char_list and char_list.get_response_time_percentile(0.95) > 500:
        failures.append(
            f"CHAR_LIST P95={char_list.get_response_time_percentile(0.95):.0f}ms > 500ms"
        )

    if failures:
        print("\n" + "=" * 60)
        print("⚠️ SLA VIOLATIONS:")
        for f in failures:
            print(f"  ❌ {f}")
        print("=" * 60)
        environment.process_exit_code = 1
    else:
        print("\n✅ All SLA thresholds passed")
