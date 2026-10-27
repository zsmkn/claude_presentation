"""Make a title-screen cast card in the same style as the cards cut from cast_cards.png:
rounded card with a soft tinted gradient, the illustration fading out at the bottom, coloured name + grey subtitle.
Add an entry to CARDS and run:  python make_card.py [name ...]"""
import sys
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from extract_cards import round_corners

W, H = 420, 605
FONT_NAME = "C:/Windows/Fonts/segoeuib.ttf"
FONT_SUB = "C:/Windows/Fonts/segoeui.ttf"
BOTTOM = (254, 252, 248)          # every card fades to this near-white at the bottom
SUB_COLOR = (78, 70, 58)

CARDS = {
    "gemini": dict(
        src="references/gemini_illust_ref.png",
        name="Gemini", subtitle="Gemini CLI",
        name_color=(104, 54, 164), tint=(240, 234, 252), border=(230, 226, 234),
        scale=0.44, top=-6,           # illustration scale and where its top edge lands on the card
        fade=(400, 505),               # illustration fades out between these card rows
    ),
}


def cutout_white(im, thr=238):
    """Make the white background transparent (flood fill from the border, so white clothes stay)."""
    rgb = im.convert("RGB")
    a = np.asarray(rgb).astype(int)
    cand = Image.fromarray(((a.min(-1) >= thr) * 255).astype(np.uint8)).copy()
    w, h = cand.size
    for x in range(0, w, 3):
        for y in (0, h - 1):
            if cand.getpixel((x, y)) == 255: ImageDraw.floodfill(cand, (x, y), 128)
    for y in range(0, h, 3):
        for x in (0, w - 1):
            if cand.getpixel((x, y)) == 255: ImageDraw.floodfill(cand, (x, y), 128)
    alpha = Image.fromarray(((np.asarray(cand) != 128) * 255).astype(np.uint8))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def make(spec):
    t = np.linspace(0, 1, H)[:, None, None] ** 0.8
    bg = np.array(spec["tint"]) * (1 - t) + np.array(BOTTOM) * t
    card = Image.fromarray(np.broadcast_to(bg, (H, W, 3)).astype(np.uint8)).convert("RGBA")

    art = cutout_white(Image.open(spec["src"]))
    s = spec["scale"]
    art = art.resize((round(art.width * s), round(art.height * s)), Image.LANCZOS)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.alpha_composite(art, ((W - art.width) // 2, spec["top"])) if spec["top"] >= 0 else \
        layer.alpha_composite(art.crop((0, -spec["top"], art.width, art.height)), ((W - art.width) // 2, 0))
    f0, f1 = spec["fade"]
    ramp = np.clip((f1 - np.arange(H)) / (f1 - f0), 0, 1)[:, None]
    la = np.asarray(layer.getchannel("A")).astype(float) * ramp
    layer.putalpha(Image.fromarray(la.astype(np.uint8)))
    card.alpha_composite(layer)

    d = ImageDraw.Draw(card)
    fn, fs = ImageFont.truetype(FONT_NAME, 30), ImageFont.truetype(FONT_SUB, 19)
    d.text((W / 2, 552), spec["name"], font=fn, fill=spec["name_color"], anchor="ms")
    d.text((W / 2, 591), spec["subtitle"], font=fs, fill=SUB_COLOR, anchor="ms")
    d.rounded_rectangle([0, 0, W - 1, H - 1], 24, outline=spec["border"], width=2)
    return round_corners(card)


if __name__ == "__main__":
    for name in sys.argv[1:] or CARDS:
        make(CARDS[name]).save(f"characters/card_{name}.png")
        print("card", name)
