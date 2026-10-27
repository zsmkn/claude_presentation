"""Split references/cast_cards.png (one screenshot with three cards) into one card per character,
so the title screen can line up whichever characters are in this episode."""
from PIL import Image, ImageDraw

CARDS = {  # x0, x1 of each card's outer border in the screenshot; the cards start at y = 8
    "claude": (5, 422),
    "gpt": (446, 867),
    "deepseek": (896, 1314),
}
TOP = 8
RADIUS = 24


def round_corners(im, r=RADIUS):
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width - 1, im.height - 1], r, fill=255)
    im.putalpha(m)
    return im


if __name__ == "__main__":
    src = Image.open("references/cast_cards.png").convert("RGBA")
    for name, (x0, x1) in CARDS.items():
        card = round_corners(src.crop((x0, TOP, x1 + 1, src.height)))
        card.save(f"characters/card_{name}.png")
        print(name, card.size)
