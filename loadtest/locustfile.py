"""Load test (Plan V3 Phase 4): the API's light endpoints under concurrent users, and how long one
analysis holds the single pose-model slot. Never point it at production.

    uv run python loadtest/make_users.py 50 loadtest/out/tokens.txt   # same DATABASE_URL/JWT_SECRET
    uv run --with locust locust -f loadtest/locustfile.py --headless -u 50 -r 10 -t 60s \\
        --host http://localhost:8000 --csv loadtest/out/run

Each simulated user takes one of the prepared accounts, then browses: session list, health check, and (rarely) an
analysis status poll for a job that doesn't exist. Analyses themselves run one at a time per process
(app/api/analysis.py), so their capacity is 1 / (seconds per analysis), measured separately with
loadtest/analysis_time.py.
"""

import itertools
import os

from locust import HttpUser, between, task

TOKENS = itertools.cycle(open(os.environ.get("LOADTEST_TOKENS", "loadtest/out/tokens.txt")).read().split())


class Browser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        self.client.headers["Authorization"] = f"Bearer {next(TOKENS)}"

    @task(5)
    def sessions(self) -> None:
        self.client.get("/sessions")

    @task(2)
    def health(self) -> None:
        self.client.get("/healthz")

    @task(1)
    def poll_missing_job(self) -> None:
        with self.client.get("/analyses/not-a-job", name="/analyses/[id]", catch_response=True) as r:
            if r.status_code == 404:
                r.success()
