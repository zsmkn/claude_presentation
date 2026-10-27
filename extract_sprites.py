from PIL import Image
import numpy as np
from collections import deque
import sys

def resample(path, crop=None):
    src = Image.open(path).convert("RGB")
    if crop: src = src.crop(crop)
    A = np.asarray(src).astype(float); L = np.asarray(src.convert("L")).astype(float)
    h, w = L.shape
    def pp(axis):
        g = np.abs(np.diff(L[h//6:h*5//6, w//6:w*5//6], axis=axis)).mean(1-axis)
        g = g-g.mean(); x = np.arange(len(g))
        p = max(np.arange(2.0, 6.0, 0.002), key=lambda p: abs((g*np.exp(2j*np.pi*x/p)).sum()))
        ph = np.angle((g*np.exp(2j*np.pi*x/p)).sum())
        off = (w//6 if axis == 1 else h//6)
        edge = ((-ph/(2*np.pi))*p) % p + off + 0.5
        return p, edge
    px, ex = pp(1); py, ey = pp(0)
    xs = np.arange(ex % px + px/2, w-1.01, px); ys = np.arange(ey % py + py/2, h-1.01, py)
    def samp(x, y):
        x0, y0 = int(x), int(y); fx, fy = x-x0, y-y0
        return A[y0,x0]*(1-fx)*(1-fy)+A[y0,x0+1]*fx*(1-fy)+A[y0+1,x0]*(1-fx)*fy+A[y0+1,x0+1]*fx*fy
    return np.array([[samp(x, y) for x in xs] for y in ys]).astype(int), (px, py)

def cutout(g, tol=22, dark=150):
    H, W, _ = g.shape
    s = g.sum(-1)
    out = np.zeros((H, W), bool)
    q = deque()
    for y in range(H):
        for x in (0, W-1): q.append((y, x)); out[y, x] = True
    for x in range(W):
        for y in (0, H-1): q.append((y, x)); out[y, x] = True
    while q:
        y, x = q.popleft()
        for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
            ny, nx = y+dy, x+dx
            if 0 <= ny < H and 0 <= nx < W and not out[ny, nx] and s[ny, nx] < dark and np.abs(g[ny, nx]-g[y, x]).sum() < tol:
                out[ny, nx] = True; q.append((ny, nx))
    a = (~out).astype(np.uint8)*255
    im = Image.fromarray(np.dstack([g.clip(0,255).astype(np.uint8), a]), "RGBA")
    im = im.crop(im.getbbox())
    rgb = im.convert("RGB").quantize(64, method=Image.Quantize.MEDIANCUT).convert("RGB")
    return Image.merge("RGBA", (*rgb.split(), im.getchannel("A")))

if __name__ == "__main__":
    for src, name in (("references/claude_pixel_open.png", "claude_open"), ("references/deepseek_pixel_open.png", "deepseek_open")):
        g, p = resample(src)
        im = cutout(g)
        im.save(f"characters/spr_{name}.png"); print(name, p, im.size)
