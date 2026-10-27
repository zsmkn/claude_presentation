"""Render the presentation video: pixel-style VN layout hosted by Claude.
python render.py projects/<name>                    full video -> presentation.mp4
python render.py projects/<name> preview 5 30 #12   preview frames at 5 s, 30 s and the middle of line 12"""
import math, subprocess, sys, wave
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import config
import project
import sprites

PROJ, _story = project.load()
PREVIEW = len(sys.argv) > 2 and sys.argv[2] == "preview"
SCENES = _story.SCENES
POPS = _story.POPS
CFG = config.load(PROJ)
SPEAKERS = CFG["characters"]
HOST, GUESTS = config.cast(CFG, SCENES)
SHOW, TIMING, AUDIO, STYLE, TEXT = CFG["show"], CFG["timing"], CFG["audio"], CFG["style"], CFG["text"]
# 片頭大標、片頭副標、畫面右上角小字：config.toml > 資料夾名稱
TITLE = SHOW.get("title") or PROJ.name
SUBTITLE = SHOW.get("subtitle", "")
TOPBAR = SHOW.get("topbar") or TITLE

FPS = TIMING["fps"]
VW, VH = 1920, 1080
SR = 24000
SHOTS = PROJ / "shots"
FONT_B = STYLE["font_cjk"]
FONT_LAT = STYLE["font_latin"]
FONT_MONO = STYLE["font_mono"]
FONT_SYM = STYLE["font_symbol"]

CREAM = STYLE["cream"]
DOT = STYLE["dot"]
INK = STYLE["ink"]
PAPER = STYLE["paper"]
ORANGE = STYLE["accent"]
MUTED = STYLE["muted"]
LIME = STYLE["lime"]

MON = (636, 132, 1184, 666)          # monitor inner x, y, w, h
DLG = (60, 836, 1800, 214)           # dialog box x, y, w, h
HOST_CX, HOST_BOTTOM = 325, 812     # host sprite: bottom-centre anchor, scale 5
GUEST_BOTTOM = 836                   # scale 4


def guest_slots(n):
    table = CFG["layout"]["guest_x"]
    if n <= len(table):
        return table[n - 1] if n else []
    a, b = table[-1][0], table[-1][-1]
    return [round(a + (b - a) * i / (n - 1)) for i in range(n)]


GUEST_X = dict(zip(GUESTS, guest_slots(len(GUESTS))))
# curtain call: host in the middle, guests split on both sides, centres 370 px apart
_line = GUESTS[:len(GUESTS) // 2] + [HOST] + GUESTS[len(GUESTS) // 2:]
END_CAST = tuple((who, round(960 + (i - (len(_line) - 1) / 2) * 370) - 150) for i, who in enumerate(_line))
LINE_GAP = TIMING["line_gap"]
SCENE_INTRO = TIMING["scene_intro"]




@lru_cache(None)
def font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)


_MISSING = {}


def has_glyph(path, ch):
    key = (path, ch)
    if key not in _MISSING:
        f = font(path, 40)
        def r(c):
            im = Image.new("L", (80, 80)); ImageDraw.Draw(im).text((10, 10), c, font=f, fill=255); return im.tobytes()
        _MISSING[key] = r(ch) != r("󰀀")
    return _MISSING[key]


def draw_mixed(d, xy, text, size, fill):
    x, y = xy
    fb, fs = font(FONT_B, size), font(FONT_SYM, size)
    for ch in text:
        f = fb if has_glyph(FONT_B, ch) else fs
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch)


def pixel_box(w, h, fill=PAPER, border=INK, bw=5, shadow=10):
    im = Image.new("RGBA", (w + shadow, h + shadow), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([shadow, shadow, w + shadow - 1, h + shadow - 1], fill=INK + (255,))
    d.rectangle([0, 0, w - 1, h - 1], fill=border + (255,))
    d.rectangle([bw, bw, w - 1 - bw, h - 1 - bw], fill=fill + (255,))
    return im


def tag(text, color, size=44, padx=18, pady=6):
    f = font(FONT_LAT if text.isascii() else FONT_B, size)
    bb = f.getbbox(text, stroke_width=3)
    w, h = bb[2] - bb[0] + padx * 2, size + pady * 2 + 8
    im = Image.new("RGBA", (w + 6, h + 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], fill=INK + (255,))
    d.rectangle([4, 4, w - 5, h - 5], fill=color + (255,))
    d.text((padx - bb[0], pady + 2 - bb[1] + (size - (bb[3] - bb[1])) // 2), text, font=f, fill="white",
           stroke_width=3, stroke_fill=INK)
    return im


# ---------------- static background ----------------
def base_bg():
    im = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # monitor frame
    mx, my, mw, mh = MON
    fr = pixel_box(mw + 40, mh + 40, fill=(40, 30, 28), bw=6, shadow=12)
    im.alpha_composite(fr, (mx - 20, my - 20))
    d = ImageDraw.Draw(im)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.rectangle([mx - 8 + i * 22, my - 15, mx + 4 + i * 22, my - 4], fill=c)
    return im


def scene_bg(base, sc):
    im = base.copy()
    d = ImageDraw.Draw(im)
    # top bar: channel tag + title
    t = tag(sc["ch"], ORANGE, 40)
    im.alpha_composite(t, (40, 26))
    d.text((40 + t.width + 22, 28), sc["title"], font=font(FONT_B, 50), fill=INK)
    sub = TOPBAR
    f = font(FONT_B, 26)
    d.text((VW - 40 - d.textlength(sub, font=f), 44), sub, font=f, fill=MUTED)
    # note box
    nb = pixel_box(500, 112, fill=(255, 251, 244), bw=4, shadow=8)
    im.alpha_composite(nb, (60, 116))
    nt = tag("NOTE", (60, 60, 70), 22, 10, 2)
    im.alpha_composite(nt, (76, 100))
    a, b = sc["note"]
    d = ImageDraw.Draw(im)
    draw_mixed(d, (86, 138), a, 38, INK)
    draw_mixed(d, (86, 186), b, 26, MUTED)
    return im


# ---------------- sprites ----------------
@lru_cache(None)
def sprite(who, eyes, mouth, scale, flip=False):
    im = sprites.draw(SPEAKERS[who]["sprite"], eyes, mouth)
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if SPEAKERS[who].get("hires"):  # hi-res art: shrink smoothly to the height of a ~110-row pixel sprite
        h = 110 * scale
        return im.resize((round(im.width * h / im.height), h), Image.LANCZOS)
    return im.resize((im.width * scale, im.height * scale), Image.NEAREST)


EYES = {"o": "open", "s": "smile", "c": "calm"}


# ---------------- monitor content ----------------
@lru_cache(None)
def shot(name):
    return Image.open(SHOTS / name).convert("RGB")


def clamp_view(img, v):
    x, y, w = v
    h = w * 9 / 16
    w = min(w, img.width); h = w * 9 / 16
    if h > img.height:
        h = img.height; w = h * 16 / 9
    x = max(0, min(x, img.width - w)); y = max(0, min(y, img.height - h))
    return (x, y, w, h)


_mon_cache = {}


def monitor_img(name, view):
    key = (name, tuple(round(v, 1) for v in view))
    if key in _mon_cache:
        return _mon_cache[key]
    img = shot(name)
    x, y, w, h = clamp_view(img, view)
    out = img.resize((MON[2], MON[3]), Image.BILINEAR, box=(x, y, x + w, y + h))
    if len(_mon_cache) > 4:
        _mon_cache.clear()
    _mon_cache[key] = out
    return out


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


rng = np.random.default_rng(7)


def static_noise(w, h, tint=(0, 0, 0), amt=1.0):
    n = rng.integers(0, 255, (h // 6 + 1, w // 6 + 1), dtype=np.uint8)
    arr = np.repeat(np.repeat(n, 6, 0), 6, 1)[:h, :w]
    rgb = np.stack([arr * 0.8 + tint[0] * 0.2, arr * 0.8 + tint[1] * 0.2, arr * 0.8 + tint[2] * 0.2], -1)
    return Image.fromarray(rgb.astype(np.uint8))


# ---------------- dialog ----------------
@lru_cache(None)
def dialog_base(who):
    x, y, w, h = DLG
    im = pixel_box(w, h, fill=PAPER, bw=6, shadow=12)
    t = tag(SPEAKERS[who]["name"], SPEAKERS[who]["color"], 40)
    canvas = Image.new("RGBA", (im.width, im.height + 40), (0, 0, 0, 0))
    canvas.alpha_composite(im, (0, 40))
    canvas.alpha_composite(t, (34, 0))
    return canvas


def layout_text(text, f, maxw):
    lines, cur = [], ""
    for ch in text:
        if f.getlength(cur + ch) > maxw and cur:
            if ch in "，。、！？；：」）…～":
                cur += ch; lines.append(cur); cur = ""; continue
            lines.append(cur); cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


TXT_F = font(FONT_B, 46)


def dialog_img(who, text, n, show_arrow):
    im = dialog_base(who).copy()
    d = ImageDraw.Draw(im)
    lines = layout_text(text, TXT_F, DLG[2] - 120)
    left = n
    for i, ln in enumerate(lines[:3]):
        part = ln[:max(0, left)]
        left -= len(ln)
        d.text((60, 40 + 46 + i * 62), part, font=TXT_F, fill=INK)
    if show_arrow:
        ax, ay = DLG[2] - 60, 40 + DLG[3] - 50
        d.polygon([(ax, ay), (ax + 22, ay), (ax + 11, ay + 14)], fill=ORANGE)
    return im


# ---------------- timeline ----------------
def load_audio(who, text):
    path = project.audio_path(PROJ, SPEAKERS[who], text)
    if not path.exists():
        if not PREVIEW:
            sys.exit(f"缺少語音：{SPEAKERS[who]['name']}「{text}」，請先執行 gen_tts.py")
        return np.zeros(int(SR * max(1.0, len(text) * 0.2)), np.float32)   # preview without TTS: silence
    with wave.open(str(path)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    return a


def build_timeline():
    tl, k, t = [], 0, TIMING["title_card"]   # title card first
    for si, sc in enumerate(SCENES):
        t += SCENE_INTRO
        sc_lines = sc["lines"]
        for li, ln in enumerate(sc_lines):
            a = load_audio(ln[0], ln[1])
            dur = len(a) / SR
            hop = SR // FPS
            rms = np.array([np.sqrt(np.mean(a[i:i + hop] ** 2)) if i < len(a) else 0 for i in range(0, len(a) + hop, hop)])
            thr = max(0.02, np.percentile(rms, 90) * 0.28)
            pop = next((p for sub, p in POPS if sub in ln[1]), None)
            tl.append(dict(k=k, si=si, li=li, who=ln[0], text=ln[1], eyes=ln[2], view=ln[3], shot=ln[4],
                           start=t, dur=dur, rms=rms, thr=thr, audio=a, pop=pop))
            t += dur + LINE_GAP
            k += 1
        t += TIMING["scene_gap"]
    return tl, t + TIMING["end_card"]


def resolve_views(tl):
    cur_shot, cur_view, prev_si = None, (0, 0, 1600), -1
    for e in tl:
        sc = SCENES[e["si"]]
        if e["si"] != prev_si:
            cur_shot, cur_view, prev_si = sc["shot"], (0, 0, 1600), e["si"]
        if e["shot"]:
            cur_shot = e["shot"]
        if e["view"]:
            cur_view = e["view"]
        e["shot_r"], e["view_r"] = cur_shot, cur_view


def guest_windows(tl):
    """guest -> list of (t_in, t_out)"""
    wins = {g: [] for g in GUESTS}
    for si, sc in enumerate(SCENES):
        ev = [e for e in tl if e["si"] == si]
        s0, s1 = ev[0]["start"] - 0.4, ev[-1]["start"] + ev[-1]["dur"] + 0.3
        for g in GUESTS:
            if g in sc["guests"]:
                wins[g].append((s0, s1 + 3.5))
                continue
            idx = [i for i, e in enumerate(ev) if e["who"] == g]
            if not idx:
                continue
            groups, cur = [], [idx[0], idx[0]]
            for i in idx[1:]:
                if i - cur[1] <= 3:
                    cur[1] = i
                else:
                    groups.append(cur); cur = [i, i]
            groups.append(cur)
            for a, b in groups:
                end = ev[min(b + 1, len(ev) - 1)]
                wins[g].append((ev[a]["start"] - 0.35, end["start"] + end["dur"] + 0.2))
    return wins


# ---------------- audio mix ----------------
def build_audio(tl, total, scene_starts):
    n = int(total * SR) + SR
    mix = np.zeros(n, np.float32)
    for e in tl:
        s = int(e["start"] * SR)
        mix[s:s + len(e["audio"])] += e["audio"] * AUDIO["voice_volume"]
    # static whoosh at channel switches
    for t0 in scene_starts:
        s = int(t0 * SR); L = int(0.35 * SR)
        nz = np.random.default_rng(1).standard_normal(L).astype(np.float32)
        nz = np.convolve(nz, np.ones(6) / 6, "same") * np.linspace(1, 0, L) * 0.10 * AUDIO["sfx_volume"]
        mix[s:s + L] += nz
    for e in tl:
        if e.get("pop"):
            s = int((e["start"] + 0.25) * SR); L = int(0.09 * SR)
            tt = np.arange(L) / SR
            fq = 900 + 900 * tt / tt[-1]
            sq = np.sign(np.sin(2 * np.pi * np.cumsum(fq) / SR)) * np.exp(-tt * 30) * 0.07 * AUDIO["sfx_volume"]
            mix[s:s + L] += sq.astype(np.float32)
    # soft chiptune BGM
    bpm = AUDIO["bgm_bpm"]; beat = 60 / bpm
    chords = [(261.6, 329.6, 392.0), (220.0, 261.6, 329.6), (174.6, 220.0, 261.6), (196.0, 246.9, 293.7)]
    t = np.arange(n) / SR
    bgm = np.zeros(n, np.float32)
    step = beat / 2
    nsteps = int(total / step) + 1
    env_len = int(step * SR)
    env = np.exp(-np.linspace(0, 5, env_len)).astype(np.float32)
    for i in range(nsteps):
        ch = chords[(i // 16) % 4]
        f = ch[[0, 1, 2, 1][i % 4]] * 2
        s = int(i * step * SR)
        seg = np.arange(env_len) / SR
        wave_ = np.sign(np.sin(2 * np.pi * f * seg)) * 0.5 + np.sin(2 * np.pi * f * seg) * 0.5
        e2 = min(env_len, n - s)
        if e2 <= 0:
            break
        bgm[s:s + e2] += (wave_ * env)[:e2] * 0.022
        if i % 4 == 0:
            bf = ch[0] / 2
            L = min(int(beat * 2 * SR), n - s)
            sg = np.arange(L) / SR
            bgm[s:s + L] += (np.sin(2 * np.pi * bf * sg) * np.exp(-sg * 1.5)).astype(np.float32) * 0.035
    bgm = np.convolve(bgm, np.ones(4) / 4, "same")
    fade = np.minimum(1, np.minimum(t / 2, (total - t) / 3)).clip(0, 1)
    mix += bgm * fade * AUDIO["bgm_volume"]
    mix = np.clip(mix, -1, 1)
    with wave.open(str(PROJ / "mix.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())


# ---------------- frame composition ----------------
SYMS = TEXT["symbols"]


@lru_cache(None)
def sym_img(s):
    f = font(FONT_SYM, 54)
    bb = f.getbbox(s)
    im = Image.new("RGBA", (bb[2] + 8, bb[3] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4, 4), s, font=f, fill=DOT[:3] + (150,))
    return im


def draw_syms(fr, t):
    for i, s in enumerate(SYMS):
        x = (i * 157 + t * (8 + i % 5 * 3)) % (VW + 200) - 100
        y = 60 + (i * 83) % 760 + 14 * math.sin(t * 0.7 + i)
        fr.alpha_composite(sym_img(s), (int(x), int(y)))


def title_card(t, base):
    fr = base.copy()
    draw_syms(fr, t)
    box = pixel_box(1240, 210, fill=PAPER, bw=7, shadow=14)
    fr.alpha_composite(box, (340, 40))
    d = ImageDraw.Draw(fr)
    s = TITLE
    # Segoe UI Black 沒有中文字形，中文標題改用正黑體
    f1 = font(FONT_LAT, 96) if s.isascii() else font(FONT_B, 92)
    d.text((960 - d.textlength(s, font=f1) / 2, 50), s, font=f1, fill=ORANGE, stroke_width=5, stroke_fill=INK)
    f2 = font(FONT_B, 40)
    s2 = SUBTITLE
    d.text((960 - d.textlength(s2, font=f2) / 2, 178), s2, font=f2, fill=INK)
    k = ease(t / 0.8)
    c = cast_img()
    fr.alpha_composite(c, (960 - c.width // 2, 300 + int((1 - k) * 60)))
    tg = tag(TEXT["host_label"] + "  " + SPEAKERS[HOST]["name"], SPEAKERS[HOST]["color"], 34)
    fr.alpha_composite(tg, (960 - c.width // 2 + 60, 290))
    return fr


@lru_cache(None)
def cast_img():
    """Host card first, then the guests', side by side (cards are characters/card_<name>.png)."""
    cards = [Image.open(project.ROOT / "characters" / f"card_{SPEAKERS[w]['card']}.png").convert("RGBA")
             for w in [HOST, *GUESTS]]
    gap = 24
    total = sum(c.width for c in cards) + gap * (len(cards) - 1)
    k = min(1.2, 1720 / total)
    im = Image.new("RGBA", (round(total * k), round(max(c.height for c in cards) * k)), (0, 0, 0, 0))
    x = 0
    for c in cards:
        c = c.resize((round(c.width * k), round(c.height * k)), Image.LANCZOS)
        im.alpha_composite(c, (round(x), 0))
        x += c.width + gap * k
    return im


def end_card(t, base):
    fr = base.copy()
    draw_syms(fr, t)
    box = pixel_box(1000, 230, fill=PAPER, bw=7, shadow=14)
    fr.alpha_composite(box, (460, 120))
    d = ImageDraw.Draw(fr)
    f1 = font(FONT_LAT, 120) if s.isascii() else font(FONT_B, 112)
    s = TEXT["end_card"]
    d.text((960 - d.textlength(s, font=f1) / 2, 140), s, font=f1, fill=ORANGE, stroke_width=5, stroke_fill=INK)
    for who, x in END_CAST:
        bob = 8 if int(t * 2.5 + x) % 2 else 0
        sp = sprite(who, "smile", "smile", 4)
        fr.alpha_composite(sp, (x + 150 - sp.width // 2, 980 - sp.height - bob))
    return fr


@lru_cache(None)
def hazard_tape():
    w, h = 2700, 58
    im = Image.new("RGBA", (w, h), LIME + (255,))
    d = ImageDraw.Draw(im)
    for x in range(-h, w, 36):                    # black chevrons top & bottom
        d.polygon([(x, 0), (x + 18, 0), (x + 10, 7), (x - 8, 7)], fill=(16, 16, 16, 255))
        d.polygon([(x, h - 7), (x + 18, h - 7), (x + 10, h), (x - 8, h)], fill=(16, 16, 16, 255))
    txt = TEXT["hazard_tape"]
    f = font(FONT_LAT if txt.isascii() else FONT_B, 30)
    x = 0
    while x < w:
        d.text((x, 9), txt, font=f, fill=(16, 16, 16, 255))
        x += d.textlength(txt, font=f)
    return im


@lru_cache(None)
def tape_rot(angle):
    return hazard_tape().rotate(angle, resample=Image.BICUBIC, expand=True)


def _paste_clip(fr, im, x, y):
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(VW, x + im.width), min(VH, y + im.height)
    if x1 <= x0 or y1 <= y0:
        return
    fr.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def draw_tapes(fr, ts):
    if ts > 1.25:
        return
    for k, (angle, y, dirn) in enumerate(((-6, 300, 1), (4, 560, -1))):
        tp = tape_rot(angle)
        reveal = ease((ts - k * 0.08) / 0.28)
        if reveal <= 0:
            continue
        out = ease((ts - 0.95) / 0.3)
        x = -380 + dirn * 140 * ts
        cw = max(1, int(tp.width * reveal))
        piece = tp.crop((0, 0, cw, tp.height)) if dirn > 0 else tp.crop((tp.width - cw, 0, tp.width, tp.height))
        px = int(x) if dirn > 0 else int(x + tp.width - cw)
        py = int(y - tp.height / 2 + out * (900 if k else -700))
        _paste_clip(fr, piece, px, py)


@lru_cache(None)
def scanlines():
    im = Image.new("RGBA", (MON[2], MON[3]), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for y in range(0, MON[3], 3):
        d.line([(0, y), (MON[2], y)], fill=(0, 0, 0, 34))
    return im


@lru_cache(None)
def pop_img(text):
    f = font(FONT_LAT if text.isascii() else FONT_B, 50)
    tw = int(f.getlength(text))
    w, h, sk = tw + 70, 84, 22
    im = Image.new("RGBA", (w + sk + 12, h + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(sk + 10, 10), (w + sk + 10, 10), (w + 10, h + 10), (10, h + 10)], fill=(16, 16, 16, 255))
    d.polygon([(sk, 0), (w + sk, 0), (w, h), (0, h)], fill=(16, 16, 16, 255))
    d.polygon([(sk + 5, 5), (w + sk - 7, 5), (w - 5, h - 5), (7, h - 5)], fill=LIME + (255,))
    d.text((35 + sk // 2, 8), text, font=f, fill=(16, 16, 16, 255))
    return im.rotate(5, resample=Image.BICUBIC, expand=True)


def draw_pop(fr, e, t):
    if not e.get("pop"):
        return
    t0 = e["start"] + 0.25
    t1 = e["start"] + e["dur"] + LINE_GAP
    if not t0 <= t < t1:
        return
    im = pop_img(e["pop"])
    k = (t - t0) / 0.16
    sc = 1.6 - 0.6 * ease(k) if k < 1 else 1.0
    a = min(1.0, (t1 - t) / 0.15)
    if sc != 1.0:
        im = im.resize((int(im.width * sc), int(im.height * sc)), Image.BILINEAR)
    if a < 1:
        im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    shake = int(6 * math.sin(t * 70)) if k < 2 else 0
    cx, cy = MON[0] + MON[2] - 250, MON[1] + 92
    _paste_clip(fr, im, cx - im.width // 2 + shake, cy - im.height // 2)


def glitch_np(a, strength, seed, y0=0, y1=None, x0=0, x1=None):
    rng = np.random.default_rng(seed)
    y1 = y1 or a.shape[0]; x1 = x1 or a.shape[1]
    reg = a[y0:y1, x0:x1].copy()
    h = reg.shape[0]
    for _ in range(int(5 + 8 * strength)):
        yy = int(rng.integers(0, max(1, h - 8))); hh = int(rng.integers(3, 34))
        dx = int(rng.integers(-60, 60) * strength)
        reg[yy:yy + hh] = np.roll(reg[yy:yy + hh], dx, axis=1)
    sh = max(1, int(9 * strength))
    reg[..., 0] = np.roll(reg[..., 0], sh, axis=1)
    reg[..., 2] = np.roll(reg[..., 2], -sh, axis=1)
    a[y0:y1, x0:x1] = reg


def main(limit=None, only=None):
    tl, total = build_timeline()
    resolve_views(tl)
    wins = guest_windows(tl)
    scene_starts = []
    for si in range(len(SCENES)):
        first = next(e for e in tl if e["si"] == si)
        scene_starts.append(first["start"] - SCENE_INTRO)
    build_audio(tl, total, scene_starts)
    print(f"total {total:.1f}s, {len(tl)} lines", flush=True)

    base = base_bg()
    plain = Image.new("RGBA", (VW, VH), CREAM + (255,))
    pd = ImageDraw.Draw(plain)
    for y in range(12, VH, 28):
        for x in range(12, VW, 28):
            pd.rectangle([x, y, x + 3, y + 3], fill=DOT)
    scene_bgs = [scene_bg(base, sc) for sc in SCENES]

    nframes = int(total * FPS)
    frames = range(nframes)
    if only is not None:   # seconds, or "#k" = the middle of script line k (0-based, counted through all scenes)
        at = lambda x: tl[int(x[1:])]["start"] + tl[int(x[1:])]["dur"] * 0.6 if x.startswith("#") else float(x)
        frames = [int(at(x) * FPS) for x in only]
    out = None
    if only is None:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{VW}x{VH}",
               "-r", str(FPS), "-i", "-", "-i", str(PROJ / "mix.wav"), "-c:v", "libx264",
               "-preset", CFG["video"]["preset"], "-crf", str(CFG["video"]["crf"]),
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
               str(PROJ / "presentation.mp4")]
        out = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    ei = 0
    prev_view = {}
    for fi in frames:
        t = fi / FPS
        if limit and fi > limit:
            break
        if t < scene_starts[0]:
            fr = title_card(t, plain)
        elif t > tl[-1]["start"] + tl[-1]["dur"] + 0.8:
            fr = end_card(t, plain)
        else:
            # current/last event
            while ei + 1 < len(tl) and tl[ei + 1]["start"] <= t:
                ei += 1
            while ei > 0 and tl[ei]["start"] > t:
                ei -= 1
            si = max(i for i, s in enumerate(scene_starts) if s <= t)
            e = tl[ei]
            if e["si"] != si:   # in scene intro, before first line
                e = next(x for x in tl if x["si"] == si)
                speaking = False
                prev_e = None
            else:
                speaking = e["start"] <= t < e["start"] + e["dur"]
                prev_e = tl[ei - 1] if ei > 0 and tl[ei - 1]["si"] == si else None
            fr = plain.copy()
            draw_syms(fr, t)
            fr.alpha_composite(scene_bgs[si])

            # monitor: camera ease from previous view
            view = e["view_r"]
            if prev_e is not None and prev_e["shot_r"] == e["shot_r"]:
                k = ease((t - e["start"]) / 0.8)
                pv = prev_e["view_r"]
                view = tuple(pv[i] + (view[i] - pv[i]) * k for i in range(3))
            mon = monitor_img(e["shot_r"], view)
            fr.paste(mon, (MON[0], MON[1]))
            ts = t - scene_starts[si]
            cut = prev_e is not None and prev_e["shot_r"] != e["shot_r"] and 0 <= t - e["start"] < 0.18
            if ts < 0.45 or cut:
                fr.paste(static_noise(MON[2], MON[3], ORANGE), (MON[0], MON[1]))
            fr.alpha_composite(scanlines(), (MON[0], MON[1]))
            dd = ImageDraw.Draw(fr)
            if int(t * 1.5) % 2 == 0:
                dd.ellipse([MON[0] + 18, MON[1] + 16, MON[0] + 34, MON[1] + 32], fill=(255, 60, 60))
            fm = font(FONT_MONO, 22)
            dd.text((MON[0] + 42, MON[1] + 12), TEXT["rec"], font=fm, fill=(255, 255, 255))
            tc = f"{SCENES[si]['ch']}  {int(t // 60):02d}:{int(t % 60):02d}:{int(t * FPS) % FPS:02d}"
            dd.text((MON[0] + MON[2] - 18 - dd.textlength(tc, font=fm), MON[1] + 12), tc, font=fm, fill=LIME)
            # channel banner
            if ts < SCENE_INTRO + 0.6:
                a = 1.0 if ts < SCENE_INTRO else 1 - (ts - SCENE_INTRO) / 0.6
                slide = (1 - ease(ts / 0.35)) * -300
                bn = tag(SCENES[si]["ch"] + "  " + SCENES[si]["title"] if SCENES[si]["ch"] not in ("START",) else TITLE, ORANGE, 64, 30, 10)
                bn2 = bn.copy()
                if a < 1:
                    bn2.putalpha(bn.getchannel("A").point(lambda v: int(v * a)))
                fr.alpha_composite(bn2, (int(MON[0] + MON[2] / 2 - bn.width / 2 + slide), MON[1] + MON[3] // 2 - bn.height // 2))

            draw_tapes(fr, ts)

            # guests
            for g in GUESTS:
                vis = 0.0
                for a0, a1 in wins[g]:
                    if a0 <= t <= a1:
                        vis = min(ease((t - a0) / 0.3), ease((a1 - t) / 0.3))
                if vis <= 0:
                    continue
                g_speak = speaking and e["who"] == g
                mouth = "closed"
                eyes = "open"
                if e["who"] == g:
                    eyes = EYES[e["eyes"]] if e["eyes"] != "c" else "calm"
                    if g_speak:
                        fi_l = int((t - e["start"]) * FPS)
                        mouth = "open" if fi_l < len(e["rms"]) and e["rms"][fi_l] > e["thr"] else ("smile" if e["eyes"] == "s" else "closed")
                    elif e["eyes"] == "s":
                        mouth = "smile"
                bob = 6 if (g_speak and int(t * 6) % 2) else 0
                sp = sprite(g, eyes, mouth, 4)
                y = GUEST_BOTTOM - sp.height + int((1 - vis) * 480) - bob
                fr.alpha_composite(sp.crop((0, 0, sp.width, min(sp.height, VH - y))) if y + sp.height > VH else sp, (GUEST_X[g], y))

            # host
            c_speak = speaking and e["who"] == HOST
            eyes, mouth = "open", "closed"
            if e["who"] == HOST and (t >= e["start"]):
                eyes = EYES[e["eyes"]]
                if c_speak:
                    fi_l = int((t - e["start"]) * FPS)
                    mouth = "open" if fi_l < len(e["rms"]) and e["rms"][fi_l] > e["thr"] else ("smile" if e["eyes"] == "s" else "closed")
                elif e["eyes"] == "s":
                    mouth = "smile"
            if e["who"] != HOST or t < e["start"]:
                eyes = "open"
            breathe = 8 if int(t / 1.2) % 2 else 0
            sp = sprite(HOST, eyes, mouth, 5)
            fr.alpha_composite(sp, (HOST_CX - sp.width // 2, HOST_BOTTOM - sp.height + breathe))

            # dialog
            if t >= e["start"] - 0.05 and (e["si"] == si):
                p = (t - e["start"]) / max(0.4, e["dur"] * 0.85)
                n = int(len(e["text"]) * min(1, max(0, p))) if p < 1 else len(e["text"])
                arrow = p >= 1 and int(t * 3) % 2 == 0
                dl = dialog_img(e["who"], e["text"], n, arrow)
                fr.alpha_composite(dl, (DLG[0], DLG[1] - 40))
                draw_pop(fr, e, t)
        rgb = np.array(fr.convert("RGB"))
        if scene_starts[0] <= t <= tl[-1]["start"] + tl[-1]["dur"]:
            si_g = max(i for i, s0 in enumerate(scene_starts) if s0 <= t)
            ts_g = t - scene_starts[si_g]
            if ts_g < 0.4:                                        # channel switch: full-frame glitch
                glitch_np(rgb, 1.0 - ts_g / 0.4, fi)
            elif (t % 6.7) < 0.13:                                # occasional monitor glitch
                glitch_np(rgb, 0.5, fi, MON[1], MON[1] + MON[3], MON[0], MON[0] + MON[2])
        if out:
            out.stdin.write(rgb.tobytes())
        else:
            path = PROJ / f"preview_{t:07.2f}.png"
            Image.fromarray(rgb).save(path)
            print("PREVIEW", path, flush=True)
        if fi % (FPS * 30) == 0:
            print(f"{t:.0f}s / {total:.0f}s", flush=True)
    if out:
        out.stdin.close(); out.wait()


if __name__ == "__main__":
    if PREVIEW:
        main(only=sys.argv[3:])
    else:
        main()
