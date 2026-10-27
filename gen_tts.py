import asyncio, subprocess
from pathlib import Path
import edge_tts
import config
import project

PROJ, _story = project.load()
SCENES = _story.SCENES
CFG = config.load(PROJ)
SPEAKERS = CFG["characters"]
config.cast(CFG, SCENES)          # stop early on unknown / off-stage speakers
OUT = PROJ / "audio"; OUT.mkdir(exist_ok=True)


def lines():
    k = 0
    for s in SCENES:
        for ln in s["lines"]:
            yield k, ln
            k += 1


def speak_text(t):
    return t.replace("……", "，").replace("～", "！")


async def one(sem, k, ln):
    sp = SPEAKERS[ln[0]]
    mp3, wav = OUT / f"{k:03d}.mp3", OUT / f"{k:03d}.wav"
    if wav.exists():
        return
    async with sem:
        for attempt in range(5):
            try:
                await edge_tts.Communicate(speak_text(ln[1]), sp["voice"], rate=sp["rate"], pitch=sp["pitch"]).save(str(mp3))
                break
            except Exception as e:
                print("retry", k, e); await asyncio.sleep(2 + attempt * 2)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", "24000", str(wav)], check=True)
    print("ok", k)


async def main():
    sem = asyncio.Semaphore(6)
    await asyncio.gather(*(one(sem, k, ln) for k, ln in lines()))

asyncio.run(main())
