"""A report folder (projects/<name>/): script in story.json, voice clips in audio/ named by content hash.

story.json
  scenes: [{ch, title, shot, guests: [代號...], note: [大字, 小字], lines: [{who, text, eyes, view, shot}]}]
  pops:   [[台詞包含的字串, 右上角標籤], ...]
Older folders with story.py are converted the first time they are opened (story.py -> story_legacy.py).
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / "projects"
FULL = [0, 0, 1600]


# ---------------------------------------------------------------- voice clips
def speak_text(t):
    return t.replace("……", "，").replace("～", "！")


def audio_key(sp, text):
    """Clip name: changes whenever the line or the speaker's voice / rate / pitch changes."""
    s = f"{sp['voice']}|{sp['rate']}|{sp['pitch']}|{speak_text(text)}"
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def audio_path(proj, sp, text, ext="wav"):
    return Path(proj) / "audio" / f"{audio_key(sp, text)}.{ext}"


# ---------------------------------------------------------------- story.json
def new_story():
    return {"scenes": [new_scene("START", "開場")], "pops": []}


def new_scene(ch="CH-01", title="", shot=""):
    return {"ch": ch, "title": title, "shot": shot, "guests": [], "note": ["", ""], "lines": []}


def new_line(who="C", text="", eyes="o", view=None, shot=None):
    return {"who": who, "text": text, "eyes": eyes, "view": view, "shot": shot}


def read_story(proj):
    proj = Path(proj)
    if not (proj / "story.json").exists() and (proj / "story.py").exists():
        migrate(proj)
    if not (proj / "story.json").exists():
        return new_story()
    with open(proj / "story.json", encoding="utf-8") as f:
        data = json.load(f)
    for sc in data["scenes"]:
        sc.setdefault("guests", []); sc.setdefault("note", ["", ""]); sc.setdefault("shot", "")
    data.setdefault("pops", [])
    return data


def write_story(proj, data):
    """One line object per row, so the file stays readable and diffs stay small."""
    j = lambda v: json.dumps(v, ensure_ascii=False)
    out = ['{', '  "scenes": [']
    for i, sc in enumerate(data["scenes"]):
        head = {k: sc[k] for k in ("ch", "title", "shot", "guests", "note")}
        out.append("    {" + j(head)[1:-1] + ', "lines": [')
        out += [f"      {j(ln)}{',' if k < len(sc['lines']) - 1 else ''}" for k, ln in enumerate(sc["lines"])]
        out.append("    ]}" + ("," if i < len(data["scenes"]) - 1 else ""))
    out.append("  ],")
    out.append('  "pops": [')
    out += [f"    {j(list(p))}{',' if k < len(data['pops']) - 1 else ''}" for k, p in enumerate(data["pops"])]
    out += ["  ]", "}", ""]
    (Path(proj) / "story.json").write_text("\n".join(out), encoding="utf-8")


def as_runtime(data):
    """story.json -> the shape render.py / gen_tts.py use: lines as (who, text, eyes, view, shot) tuples."""
    scenes = []
    for sc in data["scenes"]:
        lines = [(ln["who"], ln["text"], ln["eyes"], tuple(ln["view"]) if ln.get("view") else None, ln.get("shot") or None)
                 for ln in sc["lines"]]
        scenes.append(dict(sc, guests="".join(sc.get("guests", [])), note=tuple(sc.get("note") or ("", "")), lines=lines))
    return SimpleNamespace(SCENES=scenes, POPS=[tuple(p) for p in data.get("pops", [])])


# ---------------------------------------------------------------- story.py -> story.json
def migrate(proj):
    import config
    proj = Path(proj)
    spec = importlib.util.spec_from_file_location("story_legacy", proj / "story.py")
    st = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(st)
    notes = getattr(st, "NOTES", {})
    data = {"scenes": [], "pops": [list(p) for p in getattr(st, "POPS", [])]}
    for sc in st.SCENES:
        data["scenes"].append({
            "ch": sc["ch"], "title": sc["title"], "shot": sc.get("shot", ""), "guests": list(sc.get("guests", "")),
            "note": list(notes.get(sc["ch"], ("", ""))),
            "lines": [new_line(ln[0], ln[1], ln[2], list(ln[3]) if ln[3] else None, ln[4]) for ln in sc["lines"]],
        })
    write_story(proj, data)

    # 片頭大標等文字以前可以寫在 story.py，現在統一放 config.toml [show]
    pcfg = config.read_project(proj)
    show = pcfg.setdefault("show", {})
    for key, attr in (("title", "TITLE"), ("subtitle", "SUBTITLE"), ("topbar", "TOPBAR")):
        if not show.get(key) and getattr(st, attr, ""):
            show[key] = getattr(st, attr)
    config.write_project(proj, pcfg)

    # audio/000.wav ... were numbered in script order; rename them to content-hash names
    speakers = config.load(proj)["characters"]
    k = 0
    for sc in data["scenes"]:
        for ln in sc["lines"]:
            for ext in ("wav", "mp3"):
                old, new = proj / "audio" / f"{k:03d}.{ext}", audio_path(proj, speakers[ln["who"]], ln["text"], ext)
                if old.exists() and not new.exists():
                    old.rename(new)
            k += 1
    (proj / "story.py").rename(proj / "story_legacy.py")
    print(f"已把 {proj.name}/story.py 轉成 story.json（原檔改名為 story_legacy.py）", flush=True)


# ---------------------------------------------------------------- command line
def open_project(proj):
    proj = Path(proj).resolve()
    return proj, as_runtime(read_story(proj))


def load(argv=None):
    argv = sys.argv if argv is None else argv
    if len(argv) < 2:
        sys.exit("用法：python <script>.py projects/<專案資料夾> [...]")
    return open_project(argv[1])
