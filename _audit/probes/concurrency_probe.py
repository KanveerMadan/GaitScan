"""Does one /analyze request block the whole server? (async def + CPU-bound sync work)
Assumes uvicorn is serving src.api.main:app on 127.0.0.1:8765 from _audit/sandbox.
Usage: python concurrency_probe.py <video>
"""
import sys, time, threading, httpx

BASE = "http://127.0.0.1:8765"
video = sys.argv[1]
tok = httpx.post(f"{BASE}/auth/register", json={"email": f"load{time.time()}@x.io", "password": "pw12345678"}).json()["access_token"]

lat = []
done = threading.Event()
def poll():
    while not done.is_set():
        t = time.perf_counter()
        httpx.get(f"{BASE}/status", timeout=300)
        lat.append((round(time.perf_counter() - t0, 2), round(time.perf_counter() - t, 2)))
        time.sleep(0.5)

t0 = time.perf_counter()
th = threading.Thread(target=poll); th.start()
time.sleep(1.5)
with open(video, "rb") as f:
    r = httpx.post(f"{BASE}/analyze", headers={"Authorization": f"Bearer {tok}"},
                   files={"video": ("v.mp4", f, "video/mp4")}, timeout=600)
analyze_s = time.perf_counter() - t0 - 1.5
time.sleep(1.5); done.set(); th.join()
print("analyze status", r.status_code, "wall", round(analyze_s, 1), "s")
print("health-check latencies (t_since_start, latency_s):", lat)
print("max /status latency during analysis:", max(l for _, l in lat), "s")
