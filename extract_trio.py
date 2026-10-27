from PIL import Image, ImageDraw, ImageFont
import numpy as np
from collections import deque
g = np.asarray(Image.open("references/trio_grid.png").convert("RGB")).astype(int)
H, W, _ = g.shape
bg = np.array([6, 12, 24])
dist = np.abs(g - bg).sum(-1)
# flood from border through near-bg pixels
out = np.zeros((H, W), bool)
q = deque([(y, x) for y in range(H) for x in (0, W - 1)] + [(y, x) for x in range(W) for y in (0, H - 1)])
for y, x in q: out[y, x] = True
while q:
    y, x = q.popleft()
    for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
        ny, nx = y+dy, x+dx
        if 0 <= ny < H and 0 <= nx < W and not out[ny, nx] and dist[ny, nx] < 70:
            out[ny, nx] = True; q.append((ny, nx))
alpha = ((~out) & (dist >= 40)).astype(np.uint8) * 255
rgba = np.dstack([g.astype(np.uint8), alpha])
img = Image.fromarray(rgba, "RGBA")
# split into three by column gaps
colsum = alpha.sum(0)
runs = []; inr = False
for x, c in enumerate(colsum):
    if c > 0 and not inr: s = x; inr = True
    elif c == 0 and inr:
        if x - s > 20: runs.append((s, x))
        inr = False
print(runs)
names = ["gpt", "claude", "deepseek"]
for (x0, x1), n in zip(runs, names):
    sub = img.crop((x0, 0, x1, H))
    bb = sub.getbbox(); sub = sub.crop(bb)
    # palette clean-up
    rgb = sub.convert("RGB").quantize(48, method=Image.Quantize.MEDIANCUT).convert("RGB")
    sub = Image.merge("RGBA", (*rgb.split(), sub.getchannel("A")))
    sub.save(f"characters/spr_{n}.png")
    print(n, sub.size)
    # debug zoom with grid coords
    z = 7
    zz = Image.new("RGBA", (sub.width * z, sub.height * z), (247, 240, 230, 255))
    zz.alpha_composite(sub.resize((sub.width * z, sub.height * z), Image.NEAREST))
    d = ImageDraw.Draw(zz)
    for x in range(0, sub.width, 5):
        d.line([(x*z, 0), (x*z, zz.height)], fill=(0, 160, 0, 90) if x % 10 else (255, 0, 0, 140))
    for y in range(0, sub.height, 5):
        d.line([(0, y*z), (zz.width, y*z)], fill=(0, 160, 0, 90) if y % 10 else (255, 0, 0, 140))
    zz.crop((0, 0, zz.width, min(zz.height, 60*z))).save(f"dbg_{n}.png")
