"""Make one voice clip per script line: audio/<hash>.wav. Clips that already exist are skipped,
so editing a line (or a character's voice) only regenerates what changed."""
import asyncio, subprocess
import edge_tts
import config
import project

PROJ, _story = project.load()
SCENES = _story.SCENES
CFG = config.load(PROJ)
SPEAKERS = CFG["characters"]
config.cast(CFG, SCENES)          # stop early on unknown / off-stage speakers
OUT = PROJ / "audio"; OUT.mkdir(exist_ok=True)


def clips():
    """(wav path, speaker, text) for every distinct clip the script needs."""
    seen = {}
    for s in SCENES:
        for ln in s["lines"]:
            wav = project.audio_path(PROJ, SPEAKERS[ln[0]], ln[1])
            seen.setdefault(wav, (SPEAKERS[ln[0]], ln[1]))
    return [(wav, sp, text) for wav, (sp, text) in seen.items()]


async def one(sem, wav, sp, text):
    mp3 = wav.with_suffix(".mp3")
    async with sem:
        for attempt in range(5):
            try:
                await edge_tts.Communicate(project.speak_text(text), sp["voice"], rate=sp["rate"], pitch=sp["pitch"]).save(str(mp3))
                break
            except Exception as e:
                print("retry", wav.stem, e, flush=True); await asyncio.sleep(2 + attempt * 2)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", "24000", str(wav)], check=True)
    print("ok", sp["name"], text[:24], flush=True)


async def main():
    todo = [c for c in clips() if not c[0].exists()]
    print(f"需要產生 {len(todo)} 句語音", flush=True)
    sem = asyncio.Semaphore(CFG["audio"]["tts_concurrency"])
    await asyncio.gather(*(one(sem, *c) for c in todo))
    print("done", flush=True)

asyncio.run(main())
