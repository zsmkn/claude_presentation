"""Settings: config.toml (global) merged with projects/<name>/config.toml (this report).
Both files can be edited by hand or from studio.py; writing them back keeps the comments below."""
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GLOBAL = ROOT / "config.toml"

# Values used when config.toml leaves them out (older config files don't have these sections).
DEFAULTS = {
    "audio": {"bgm_bpm": 84, "tts_concurrency": 6},
    "video": {"crf": 20, "preset": "medium"},
    "style": {
        "font_cjk": "C:/Windows/Fonts/msjhbd.ttc", "font_latin": "C:/Windows/Fonts/seguibl.ttf",
        "font_mono": "C:/Windows/Fonts/consolab.ttf", "font_symbol": "C:/Windows/Fonts/seguisym.ttf",
        "accent": [232, 102, 28], "ink": [59, 31, 20], "paper": [253, 247, 238], "cream": [247, 240, 230],
        "dot": [228, 214, 196], "muted": [150, 110, 90], "lime": [212, 245, 60],
    },
    "text": {
        "end_card": "THANK YOU", "host_label": "主持", "rec": "REC",
        "hazard_tape": "CAUTION  //  HOLLOW ZONE  //  PROXY ONLY  //  SIGNAL LOST  //  ",
        "symbols": ["∑", "π", "∫", "√", "Δ", "∞", "≈", "λ", "θ", "∂", "H₂O", "∝", "e^iπ"],
    },
    "cards": {},
}

# ---------------------------------------------------------------- comments written into config.toml
HEADER = """# 全域設定。每份報告可以在 projects/<名稱>/config.toml 寫同名欄位，覆寫這裡的值
# （只要寫想改的那幾項就好，其餘沿用這裡）。這個檔案也可以用 studio.py 的「設定」「角色」分頁編輯。"""

SECTION_NOTES = {
    "show": "本次演出：通常寫在各報告自己的 config.toml",
    "timing": "單位：秒",
    "video": "ffmpeg 編碼品質",
    "style": "字型路徑與畫面配色（RGB）",
    "text": "畫面上固定出現的文字",
    "characters": """# ---------------------------------------------------------------- 角色名冊
# 代號 = 劇本台詞的講者欄位。name 顯示在對話框名牌，color 是名牌底色。
# voice / rate / pitch 是 edge-tts 聲線；語音檔以內容命名，改了聲線會自動重新產生。
# sprite：characters/spr_<sprite>.png（claude、gpt、deepseek_open 有嘴巴動畫，寫在 sprites.py）
# hires = true：不是格狀像素圖的高解析度圖，會縮放到和其他角色一樣高，沒有嘴巴動畫
# card：片頭角色卡 characters/card_<card>.png（可以用下方 [cards] 設定 + make_card.py 產生）""",
    "cards": """# ---------------------------------------------------------------- 角色卡產生器（make_card.py）
# 用立繪產生 characters/card_<名稱>.png。scale 立繪縮放、top 立繪頂端落在卡片的 y、
# fade = [開始, 結束]：立繪在這兩個 y 之間淡出。""",
}

KEY_NOTES = {
    "show.host": "主持人（角色代號，見下方 [characters]）",
    "show.guests": "上鏡配角，順序 = 由左到右的站位；留空 = 依劇本有台詞的角色自動判斷",
    "show.title": "片頭大標；留空 = 用資料夾名稱",
    "show.subtitle": "片頭副標",
    "show.topbar": "畫面右上角小字；留空 = 同片頭大標",
    "timing.title_card": "片頭長度",
    "timing.scene_intro": "每段開頭頻道橫幅",
    "timing.line_gap": "台詞之間的停頓",
    "timing.scene_gap": "每段結尾多停的時間",
    "timing.end_card": "片尾謝幕長度",
    "audio.bgm_volume": "BGM 音量倍率（1 = 預設）",
    "audio.sfx_volume": "換頻道雜訊、蓋章音效的音量倍率",
    "audio.bgm_bpm": "BGM 速度",
    "audio.tts_concurrency": "產生語音時同時連線數",
    "video.crf": "越小畫質越好、檔案越大（18–28）",
    "video.preset": "ultrafast … medium … veryslow",
    "layout.guest_x": "配角站位（左上角 x），依上鏡人數取用：1 人、2 人、3 人……；超過就平均分布在第一個到最後一個位置之間",
    "style.accent": "頻道標籤、片頭標題、對話框箭頭",
    "style.ink": "文字與外框",
    "style.paper": "對話框、標題框底色",
    "style.cream": "背景底色",
    "style.dot": "背景點陣",
    "style.muted": "右上角小字、NOTE 小字",
    "style.lime": "蓋章標籤、時間碼",
    "text.end_card": "片尾大字",
    "text.host_label": "片頭主持人標籤：<host_label>  <名字>",
    "text.hazard_tape": "換頻道時飛過的警示膠帶文字",
    "text.symbols": "背景漂浮的符號",
}


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def read(path):
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def read_global():
    return read(GLOBAL)


def read_project(proj):
    return read(Path(proj) / "config.toml")


def merged(proj):
    """Global + this report, colours still as lists (what studio.py edits)."""
    cfg = _merge(DEFAULTS, read_global())
    if proj:
        cfg = _merge(cfg, read_project(proj))
    return cfg


def load(proj):
    cfg = merged(proj)
    for c in cfg["characters"].values():
        c["color"] = tuple(c["color"])
    for k, v in cfg["style"].items():
        if isinstance(v, list):
            cfg["style"][k] = tuple(v)
    return cfg


# ---------------------------------------------------------------- writing TOML
def _val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_val(x) for x in v) + "]"
    raise TypeError(f"無法寫入 TOML：{v!r}")


def _table(out, name, tbl, comments):
    scalars = {k: v for k, v in tbl.items() if not isinstance(v, dict)}
    subs = {k: v for k, v in tbl.items() if isinstance(v, dict)}
    top = name.split(".")[0]
    if comments and "." not in name and SECTION_NOTES.get(name, "").startswith("#"):
        out += ["", SECTION_NOTES[name]]
    if scalars or not subs:
        note = SECTION_NOTES.get(name, "") if comments else ""
        head = f"[{name}]"
        out += ["", f"{head:<32}# {note}" if note and not note.startswith("#") else head]
        width = max(len(f"{k} = {_val(v)}") for k, v in scalars.items()) if scalars else 0
        for k, v in scalars.items():
            line = f"{k} = {_val(v)}"
            note = KEY_NOTES.get(f"{top}.{k}") if comments and "." not in name else None
            out.append(f"{line:<{max(32, width + 2)}}# {note}" if note else line)
    for k, v in subs.items():
        _table(out, f"{name}.{k}", v, comments)


def dumps(data, header="", comments=True):
    out = [header] if header else []
    for k, v in data.items():
        if not isinstance(v, dict):
            out.append(f"{k} = {_val(v)}")
    for k, v in data.items():
        if isinstance(v, dict):
            _table(out, k, v, comments)
    return "\n".join(out).lstrip("\n") + "\n"


def write_global(data):
    GLOBAL.write_text(dumps(data, HEADER), encoding="utf-8")


def write_project(proj, data):
    data = {k: v for k, v in data.items() if v != {}}
    Path(proj, "config.toml").write_text(
        dumps(data, "# 這份報告的設定，只寫和根目錄 config.toml 不同的部分。"), encoding="utf-8")


# ---------------------------------------------------------------- cast check
def check_cast(cfg, scenes):
    """-> (host, guests, error message or None). Guests default to everyone else who has lines or is listed in a scene's guests."""
    chars, show = cfg["characters"], cfg["show"]
    host = show.get("host", "C")
    used = {ln[0] for sc in scenes for ln in sc["lines"]} | {g for sc in scenes for g in sc.get("guests", "")}
    guests = list(show.get("guests") or [c for c in chars if c in used and c != host])
    unknown = [c for c in [host, *guests, *used] if c not in chars]
    if unknown:
        return host, guests, f"設定錯誤：角色代號 {sorted(set(unknown))} 不在 config.toml 的 [characters] 裡"
    if host in guests:
        return host, guests, f"設定錯誤：{host} 不能同時是主持人和配角"
    offstage = sorted(used - {host} - set(guests))
    if offstage:
        return host, guests, f"設定錯誤：劇本裡有 {offstage} 的台詞（或寫在場景 guests），但不在本次的 host / guests 名單"
    return host, guests, None


def cast(cfg, scenes):
    host, guests, err = check_cast(cfg, scenes)
    if err:
        sys.exit(err)
    return host, guests
