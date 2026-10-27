"""Sprites from the user's reference pixel art. Only the mouth is animated;
eyes come straight from the references (Claude has an open-eye and a closed-eye art)."""
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw

CHAR_DIR = Path(__file__).resolve().parent / "characters"

MOUTH = (110, 36, 40, 255)
TONGUE = (222, 116, 112, 255)


@lru_cache(None)
def _load(name):
    return Image.open(CHAR_DIR / f"spr_{name}.png").convert("RGBA")


def _pad_bottom_center(im, w, h):
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(im, ((w - im.width) // 2, h - im.height))
    return out


def claude(eyes, mouth):
    if eyes == "open":
        im = _load("claude_open").copy()
        d = ImageDraw.Draw(im)
        if mouth == "open":
            skin = im.getpixel((38, 38))
            d.rectangle([39, 36, 43, 38], fill=skin)      # hide the closed-mouth corner dots
            d.rectangle([40, 36, 42, 38], fill=MOUTH); d.rectangle([41, 38, 41, 38], fill=TONGUE)
            d.point((40, 36), fill=skin); d.point((42, 36), fill=skin)
    else:
        im = _load("claude").copy()
        d = ImageDraw.Draw(im)
        if mouth == "open":
            d.rectangle([40, 36, 41, 37], fill=MOUTH); d.point((41, 37), fill=TONGUE)
    return _pad_bottom_center(im, 90, 110)


def gpt(eyes, mouth):
    im = _load("gpt").copy()
    if mouth == "open":
        d = ImageDraw.Draw(im)
        d.rectangle([45, 42, 47, 43], fill=MOUTH); d.point((46, 43), fill=TONGUE)
    return im


def deepseek(eyes, mouth):
    im = _load("deepseek_open").copy()
    d = ImageDraw.Draw(im)
    skin = im.getpixel((35, 35))
    d.rectangle([36, 33, 43, 38], fill=skin)
    if mouth == "open":           # crisp open smile like the reference art
        dark, red, pink = (96, 26, 40, 255), (196, 64, 76, 255), (246, 150, 158, 255)
        for x in range(38, 42): d.point((x, 34), fill=dark)
        d.point((37, 35), fill=dark); d.point((42, 35), fill=dark)
        for x in range(38, 42): d.point((x, 35), fill=red)
        d.point((38, 36), fill=dark); d.point((41, 36), fill=dark)
        d.point((39, 36), fill=pink); d.point((40, 36), fill=pink)
        d.point((39, 37), fill=dark); d.point((40, 37), fill=dark)
    else:
        line = (150, 70, 80, 255)
        for p in ((38, 35), (39, 36), (40, 36), (41, 35)):
            d.point(p, fill=line)
    return im


ANIMATED = {"claude": claude, "gpt": gpt, "deepseek_open": deepseek}   # sprite name -> hand-made mouth animation


def draw(sprite_name, eyes, mouth):
    """Animated sprite if that art has one, else characters/spr_<sprite_name>.png as is."""
    fn = ANIMATED.get(sprite_name)
    return fn(eyes, mouth) if fn else _load(sprite_name).copy()

if __name__ == "__main__":
    z = 10
    boxes = {"claude": (22, 18, 62, 48), "gpt": (28, 24, 68, 54), "deepseek_open": (20, 18, 60, 48)}
    combos = [("open", "closed"), ("open", "open"), ("calm", "closed"), ("calm", "open")]
    out = Image.new("RGBA", (4 * 400, 3 * 300), (247, 240, 230, 255))
    for r, (c, fn) in enumerate(ANIMATED.items()):
        for k, (e, m) in enumerate(combos):
            s = fn(e, m)
            if c == "claude" and e == "open":
                bx = (boxes[c][0] + 2, boxes[c][1] + 2, boxes[c][2] + 2, boxes[c][3] + 2)
            else:
                bx = boxes[c]
            s = s.crop(bx).resize((400, 300), Image.NEAREST)
            out.alpha_composite(s, (k * 400, r * 300))
    out.save("faces3.png")
