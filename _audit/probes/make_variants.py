"""Generate degraded/altered variants of the sample clip with OpenCV only.
Writes into _audit/sandbox/variants/.  Usage (from _audit/sandbox): python make_variants.py <video>
"""
import os, sys
import cv2, numpy as np

src = sys.argv[1]
os.makedirs("variants", exist_ok=True)
cap = cv2.VideoCapture(src)
fps = cap.get(5)
frames = []
while True:
    ok, f = cap.read()
    if not ok:
        break
    frames.append(f)
H, W = frames[0].shape[:2]
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
rng = np.random.default_rng(0)

def write(name, fs, size=None):
    h, w = fs[0].shape[:2]
    vw = cv2.VideoWriter(f"variants/{name}.mp4", fourcc, fps, (w, h))
    for f in fs:
        vw.write(f)
    vw.release()
    print(name, w, h, len(fs))

write("mirror", [cv2.flip(f, 1) for f in frames])
write("dark", [np.clip(f.astype(np.float32) * 0.18 + rng.normal(0, 6, f.shape), 0, 255).astype(np.uint8) for f in frames])
def occlude(f):
    g = f.copy(); g[int(H * 0.78):] = 0; return g   # feet/ankles hidden (e.g. furniture, frame crop)
write("occluded_feet", [occlude(f) for f in frames])
write("two_people", [np.hstack([f, cv2.flip(f, 1)]) for f in frames])
write("rotated90", [cv2.rotate(f, cv2.ROTATE_90_CLOCKWISE) for f in frames])
# 60 s @ 1080x1920 for performance (loop + upscale)
big = [cv2.resize(f, (1080, 1920), interpolation=cv2.INTER_LINEAR) for f in frames]
n = int(60 * fps)
vw = cv2.VideoWriter("variants/long_1080p_60s.mp4", fourcc, fps, (1080, 1920))
for i in range(n):
    vw.write(big[i % len(big)])
vw.release()
print("long_1080p_60s", 1080, 1920, n)
