"""Presentation Studio — GUI for everything that used to be edited in code:
script (story.json), stamps, cast, characters / voices / cards (config.toml) and render settings.
Run:  python studio.py"""
import asyncio
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import winsound
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

import config
import project
import sprites

ROOT = project.ROOT
STATE = ROOT / ".studio_state.json"

# ---------------------------------------------------------------- theme: 簡約理工風
BG, PANEL, LINE, GRID = "#F4F4F1", "#FFFFFF", "#D5D5CF", "#E9E9E4"
INK, MUTED, ACCENT, ACCENT_SOFT = "#17191C", "#84867F", "#E8661C", "#FBE5D6"
OK, BAD, BAD_SOFT = "#2E8B57", "#C8382E", "#FBE1DF"
UI = ("Microsoft JhengHei UI", 10)
UI_L = ("Microsoft JhengHei UI", 12)
MONO = ("Consolas", 10)
MONO_B = ("Consolas", 10, "bold")
MONO_S = ("Consolas", 9)
HEAD = ("Consolas", 11, "bold")
DPI = 1.0           # screen scaling (set at start-up); tree column widths and row height follow it


def px(n):
    return round(n * DPI)

EYES = {"o": "睜眼", "s": "微笑", "c": "閉眼"}
VOICES = [
    "zh-TW-HsiaoChenNeural", "zh-TW-HsiaoYuNeural", "zh-TW-YunJheNeural",
    "zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural", "zh-CN-YunxiNeural", "zh-CN-YunjianNeural", "zh-CN-YunyangNeural",
    "zh-CN-YunxiaNeural", "zh-CN-liaoning-XiaobeiNeural", "zh-CN-shaanxi-XiaoniNeural",
    "zh-HK-HiuGaaiNeural", "zh-HK-HiuMaanNeural", "zh-HK-WanLungNeural",
]
# 設定分頁：(區段標題, config 區段, [(鍵, 型別, 標籤)])
SETTINGS = [
    ("TIMING", "timing", [("fps", "int", "影格率"), ("title_card", "float", "片頭 s"), ("scene_intro", "float", "頻道橫幅 s"),
                          ("line_gap", "float", "台詞間隔 s"), ("scene_gap", "float", "段落結尾 s"), ("end_card", "float", "片尾 s")]),
    ("AUDIO", "audio", [("voice_volume", "float", "人聲音量"), ("bgm_volume", "float", "BGM 音量"), ("sfx_volume", "float", "音效音量"),
                        ("bgm_bpm", "int", "BGM 速度"), ("tts_concurrency", "int", "TTS 連線數")]),
    ("VIDEO", "video", [("crf", "int", "CRF 畫質"), ("preset", "preset", "編碼速度")]),
    ("LAYOUT", "layout", [("guest_x", "json", "配角站位")]),
    ("STYLE", "style", [("font_cjk", "font", "中文字型"), ("font_latin", "font", "英文粗體"), ("font_mono", "font", "等寬字型"),
                        ("font_symbol", "font", "符號字型"), ("accent", "color", "強調色"), ("ink", "color", "墨色"),
                        ("paper", "color", "紙色"), ("cream", "color", "背景"), ("dot", "color", "背景點"),
                        ("muted", "color", "次要文字"), ("lime", "color", "螢光色")]),
    ("TEXT", "text", [("end_card", "str", "片尾大字"), ("host_label", "str", "主持標籤"), ("rec", "str", "錄影字樣"),
                      ("hazard_tape", "str", "警示膠帶"), ("symbols", "list", "漂浮符號")]),
]
PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]


def rgb_hex(c):
    return "#%02X%02X%02X" % tuple(c[:3])


def hex_rgb(s):
    s = s.strip().lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", s):
        raise ValueError(s)
    return [int(s[i:i + 2], 16) for i in (0, 2, 4)]


def parse(kind, s):
    s = s.strip()
    if kind == "int":
        return int(s)
    if kind == "float":
        return float(s)
    if kind == "color":
        return hex_rgb(s)
    if kind == "json":
        return json.loads(s)
    if kind == "list":
        return s.split()
    return s


def fmt(kind, v):
    if kind == "color":
        return rgb_hex(v)
    if kind == "json":
        return json.dumps(v, ensure_ascii=False)
    if kind == "list":
        return " ".join(v)
    return str(v)


def clamp_view(iw, ih, v):
    """Same framing as render.clamp_view: (x, y, w) on the screenshot -> clamped 16:9 box."""
    x, y, w = v
    w = min(w, iw); h = w * 9 / 16
    if h > ih:
        h = ih; w = h * 16 / 9
    return max(0, min(x, iw - w)), max(0, min(y, ih - h)), w, h


def guest_slots(table, n):
    if n <= len(table):
        return table[n - 1] if n else []
    a, b = table[-1][0], table[-1][-1]
    return [round(a + (b - a) * i / (n - 1)) for i in range(n)]


# ---------------------------------------------------------------- small widgets
def setup_style(root):
    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=BG, foreground=INK, font=UI, bordercolor=LINE, lightcolor=BG, darkcolor=BG,
                 troughcolor=GRID, focuscolor=BG, selectbackground=ACCENT_SOFT, selectforeground=INK,
                 fieldbackground=PANEL, insertcolor=INK)
    st.configure("TFrame", background=BG)
    st.configure("TLabel", background=BG, foreground=INK)
    st.configure("Muted.TLabel", foreground=MUTED, font=MONO_S)
    st.configure("Key.TLabel", foreground=INK, font=MONO)
    st.configure("Head.TLabel", font=HEAD)
    st.configure("Num.TLabel", font=HEAD, foreground=ACCENT)
    st.configure("Bad.TLabel", foreground=BAD, font=UI)
    st.configure("Ok.TLabel", foreground=OK, font=UI)
    st.configure("TButton", background=PANEL, foreground=INK, borderwidth=1, relief="flat", padding=(8, 2), width=-4,
                 bordercolor=LINE, lightcolor=PANEL, darkcolor=PANEL, font=UI)
    st.map("TButton", background=[("pressed", GRID), ("active", GRID), ("disabled", BG)],
           foreground=[("disabled", MUTED)], bordercolor=[("active", INK)])
    st.configure("Tool.TButton", padding=(6, 1), font=MONO_B)
    st.configure("Accent.TButton", background=INK, foreground="#FFFFFF", bordercolor=INK, lightcolor=INK, darkcolor=INK)
    st.map("Accent.TButton", background=[("pressed", ACCENT), ("active", ACCENT), ("disabled", LINE)],
           bordercolor=[("active", ACCENT)])
    for w in ("TEntry", "TCombobox", "TSpinbox"):
        st.configure(w, fieldbackground=PANEL, bordercolor=LINE, lightcolor=PANEL, darkcolor=PANEL, padding=3,
                     arrowcolor=INK, background=PANEL)
        st.map(w, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", PANEL)],
               fieldbackground=[("readonly", PANEL), ("disabled", BG)])
    st.configure("Bad.TEntry", fieldbackground=BAD_SOFT, bordercolor=BAD)
    st.configure("TCheckbutton", background=BG, indicatorbackground=PANEL, indicatorforeground=PANEL,
                 indicatorcolor=PANEL, focuscolor=BG)
    st.map("TCheckbutton", indicatorcolor=[("selected", ACCENT)], background=[("active", BG)])
    st.configure("TRadiobutton", background=BG, indicatorcolor=PANEL, focuscolor=BG)
    st.map("TRadiobutton", indicatorcolor=[("selected", ACCENT)], background=[("active", BG)])
    st.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=INK, rowheight=px(24), borderwidth=0, font=UI)
    st.map("Treeview", background=[("selected", ACCENT_SOFT)], foreground=[("selected", INK)])
    st.configure("Treeview.Heading", background=BG, foreground=MUTED, font=MONO_B, relief="flat", borderwidth=0,
                 bordercolor=LINE, padding=(4, 4))
    st.map("Treeview.Heading", background=[("active", GRID)])
    st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(12, 6, 0, 0))
    st.configure("TNotebook.Tab", background=BG, foreground=MUTED, font=MONO_B, padding=(16, 6), borderwidth=0,
                 bordercolor=BG, lightcolor=BG)
    st.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", INK)],
           lightcolor=[("selected", ACCENT)], expand=[("selected", (0, 0, 0, 0))])
    st.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=GRID, bordercolor=GRID,
                 lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
    st.configure("Vertical.TScrollbar", background=BG, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED,
                 lightcolor=BG, darkcolor=BG, arrowsize=11)
    st.configure("TPanedwindow", background=BG)
    st.configure("Sash", sashthickness=6, background=BG, bordercolor=BG, lightcolor=BG)
    root.option_add("*TCombobox*Listbox.font", UI)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_SOFT)
    root.option_add("*TCombobox*Listbox.selectForeground", INK)


def section(parent, num, title, sub=""):
    """Header row:  01  SCENES  段落 ─────────"""
    f = ttk.Frame(parent)
    ttk.Label(f, text=num, style="Num.TLabel").pack(side="left")
    ttk.Label(f, text=" " + title, style="Head.TLabel").pack(side="left")
    if sub:
        ttk.Label(f, text="  " + sub, style="Muted.TLabel").pack(side="left")
    tk.Frame(f, height=1, bg=LINE).pack(side="left", fill="x", expand=True, padx=(10, 0))
    return f


def text_widget(parent, height=3, font=UI_L):
    return tk.Text(parent, height=height, wrap="char", font=font, bg=PANEL, fg=INK, relief="flat",
                   highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT, insertbackground=INK,
                   padx=8, pady=6, undo=True, selectbackground=ACCENT_SOFT)


def tree(parent, cols, height=8):
    """cols: [(id, heading, width, stretch)]"""
    box = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
    tv = ttk.Treeview(box, columns=[c[0] for c in cols], show="headings", height=height, selectmode="browse")
    for cid, head, w, stretch in cols:
        tv.heading(cid, text=head, anchor="w")
        tv.column(cid, width=px(w), minwidth=px(28), stretch=stretch, anchor="w")
    sb = ttk.Scrollbar(box, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    tv.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    tv.tag_configure("muted", foreground=MUTED)
    tv.tag_configure("bad", foreground=BAD)
    return box, tv


class ColorField(ttk.Frame):
    def __init__(self, parent, var, width=9):
        super().__init__(parent)
        self.var = var
        self.entry = ttk.Entry(self, textvariable=var, width=width, font=MONO)
        self.entry.pack(side="left")
        self.sw = tk.Label(self, width=3, bg=PANEL, relief="flat", highlightthickness=1, highlightbackground=LINE,
                           cursor="hand2")
        self.sw.pack(side="left", padx=(4, 0), fill="y")
        self.sw.bind("<Button-1>", self.pick)
        var.trace_add("write", lambda *a: self.paint())
        self.paint()

    def paint(self):
        try:
            self.sw.configure(bg=rgb_hex(hex_rgb(self.var.get())))
        except ValueError:
            self.sw.configure(bg=BG)

    def pick(self, _=None):
        try:
            init = rgb_hex(hex_rgb(self.var.get()))
        except ValueError:
            init = "#888888"
        c = colorchooser.askcolor(init, parent=self)
        if c and c[1]:
            self.var.set(c[1].upper())


# ---------------------------------------------------------------- the app
class Studio:
    def __init__(self, root):
        self.root = root
        root.title("Presentation Studio")
        root.configure(bg=BG)
        root.geometry("1560x940")
        root.minsize(1200, 760)
        root.state("zoomed")
        global DPI
        DPI = root.winfo_fpixels("1i") / 96
        setup_style(root)
        self._loading = False
        self.proj = None
        self.story = project.new_story()
        self.gcfg = config.read_global()
        self.pcfg = {}
        self.dirty = set()           # {"story", "global", "project"}
        self.si, self.li = 0, None
        self.proc, self.q = None, queue.Queue()
        self.images = {}             # keep PhotoImage references alive
        self._img_cache = {}
        self.cam = None              # camera canvas state
        self.task_total = 0
        self.blank = tk.PhotoImage(width=1, height=1)

        self.build_header()
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=12)
        self.nb.bind("<<NotebookTabChanged>>", self.on_tab)
        self.build_script_tab()
        self.build_pops_tab()
        self.build_show_tab()
        self.build_chars_tab()
        self.build_settings_tab()
        self.build_output_tab()
        self.build_status()

        root.bind_all("<Control-s>", lambda e: self.save_all())
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_projects()
        last = self.read_state().get("project")
        names = self.project_names()
        if names:
            self.open_project(last if last in names else names[0])
        self.root.after(80, self.poll_task)

    # ------------------------------------------------------------ helpers
    def cfg(self):
        """Merged settings from the in-memory (possibly unsaved) files."""
        return config._merge(config._merge(config.DEFAULTS, self.gcfg), self.pcfg)

    def chars(self):
        return self.cfg()["characters"]

    def mark(self, *what):
        self.dirty.update(what)
        self.update_status()

    def bind(self, var, fn):
        var.trace_add("write", lambda *a: None if self._loading else fn(var.get()))

    def shots(self):
        d = self.proj / "shots" if self.proj else None
        if not d or not d.exists():
            return []
        return sorted(p.name for p in d.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))

    def runtime(self):
        return project.as_runtime(self.story)

    def audio_ok(self, ln):
        sp = self.chars().get(ln["who"])
        return bool(sp) and project.audio_path(self.proj, sp, ln["text"]).exists()

    def line_k(self, si, li):
        return sum(len(s["lines"]) for s in self.story["scenes"][:si]) + li

    def image(self, path):
        path = Path(path)
        if not path.exists():
            return None
        key = (path, path.stat().st_mtime)
        if key not in self._img_cache:
            if len(self._img_cache) > 24:
                self._img_cache.clear()
            self._img_cache[key] = Image.open(path).convert("RGBA")
        return self._img_cache[key]

    def photo(self, slot, im):
        ph = ImageTk.PhotoImage(im)
        self.images[slot] = ph
        return ph

    def read_state(self):
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    # ------------------------------------------------------------ header / status
    def build_header(self):
        h = ttk.Frame(self.root)
        h.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Button(h, text="輸出影片", style="Accent.TButton", command=self.run_render).pack(side="right")
        ttk.Button(h, text="產生語音", command=self.run_tts).pack(side="right", padx=6)
        ttk.Button(h, text="儲存 Ctrl+S", command=self.save_all).pack(side="right")
        tk.Frame(h, width=14, height=14, bg=ACCENT).pack(side="left", padx=(0, 10))
        ttk.Label(h, text="PRESENTATION STUDIO", font=("Consolas", 14, "bold")).pack(side="left")
        ttk.Label(h, text="  report video editor", style="Muted.TLabel").pack(side="left", pady=(4, 0))
        ttk.Label(h, text="     PROJECT", style="Muted.TLabel").pack(side="left", padx=(24, 6))
        self.v_proj = tk.StringVar()
        self.cb_proj = ttk.Combobox(h, textvariable=self.v_proj, state="readonly", width=26, font=MONO)
        self.cb_proj.pack(side="left")
        self.cb_proj.bind("<<ComboboxSelected>>", lambda e: self.switch_project(self.v_proj.get()))
        ttk.Button(h, text="＋ 新報告", command=self.new_project).pack(side="left", padx=6)
        ttk.Button(h, text="開啟資料夾", command=lambda: self.proj and os.startfile(self.proj)).pack(side="left")
        tk.Frame(self.root, height=1, bg=LINE).pack(fill="x", padx=12, pady=(4, 0))

    def build_status(self):
        tk.Frame(self.root, height=1, bg=LINE).pack(fill="x", padx=12)
        s = ttk.Frame(self.root)
        s.pack(fill="x", padx=12, pady=4)
        self.v_status = tk.StringVar()
        ttk.Label(s, textvariable=self.v_status, font=MONO_S, foreground=MUTED).pack(side="left")
        self.v_dirty = tk.StringVar()
        self.lb_dirty = ttk.Label(s, textvariable=self.v_dirty, font=MONO_B, foreground=ACCENT)
        self.lb_dirty.pack(side="right")

    def update_status(self):
        if not self.proj:
            return
        lines = [ln for sc in self.story["scenes"] for ln in sc["lines"]]
        chars = self.chars()
        have, secs = 0, 0.0
        for ln in lines:
            sp = chars.get(ln["who"])
            p = project.audio_path(self.proj, sp, ln["text"]) if sp else None
            if p and p.exists():
                have += 1
                secs += max(0, p.stat().st_size - 44) / 48000      # 24 kHz mono 16-bit
            else:
                secs += max(1.0, len(ln["text"]) * 0.2)
        t = self.cfg()["timing"]
        secs += t["title_card"] + t["end_card"] + len(lines) * t["line_gap"] + \
            len(self.story["scenes"]) * (t["scene_intro"] + t["scene_gap"])
        self.v_status.set(f"{self.proj.name}  │  {len(self.story['scenes'])} SCENES  │  {len(lines)} LINES  │  "
                          f"AUDIO {have}/{len(lines)}  │  LENGTH ≈ {int(secs // 60):02d}:{int(secs % 60):02d}")
        self.v_dirty.set("● 未儲存  " + " · ".join(sorted(self.dirty)) if self.dirty else "")

    # ------------------------------------------------------------ projects
    def project_names(self):
        return sorted(p.name for p in project.PROJECTS.iterdir()
                      if p.is_dir() and ((p / "story.json").exists() or (p / "story.py").exists()))

    def refresh_projects(self):
        self.cb_proj["values"] = self.project_names()

    def ask_save(self):
        """True = go on, False = cancelled."""
        if not self.dirty:
            return True
        r = messagebox.askyesnocancel("尚未儲存", "有尚未儲存的變更，要先儲存嗎？", parent=self.root)
        if r is None:
            return False
        if r:
            self.save_all()
        return True

    def switch_project(self, name):
        if self.proj and name == self.proj.name:
            return
        if not self.ask_save():
            self.v_proj.set(self.proj.name)
            return
        self.open_project(name)

    def open_project(self, name):
        self.proj = project.PROJECTS / name
        self.story = project.read_story(self.proj)
        self.gcfg = config.read_global()
        self.pcfg = config.read_project(self.proj)
        self.dirty.clear()
        self.v_proj.set(name)
        self.si, self.li = 0, None
        try:
            STATE.write_text(json.dumps({"project": name}), encoding="utf-8")
        except OSError:
            pass
        self.reload_all()

    def reload_all(self):
        self.refresh_scenes(0)
        self.refresh_pops()
        self.load_show()
        self.refresh_chars()
        self.load_settings()
        self.update_status()
        self.show_preview(None)

    def new_project(self):
        name = simpledialog.askstring("新報告", "資料夾名稱（英數、底線）：", parent=self.root)
        if not name:
            return
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", name) or (project.PROJECTS / name).exists():
            messagebox.showerror("新報告", "名稱只能用英數、底線、連字號，且不能和現有資料夾重複。", parent=self.root)
            return
        if not self.ask_save():
            return
        copy = self.proj and messagebox.askyesno(
            "新報告", f"要以目前的「{self.proj.name}」為範本嗎？\n（複製劇本、設定與截圖，不含語音和影片）", parent=self.root)
        dst = project.PROJECTS / name
        (dst / "shots").mkdir(parents=True)
        if copy:
            for f in ("story.json", "config.toml"):
                if (self.proj / f).exists():
                    shutil.copy2(self.proj / f, dst / f)
            for f in (self.proj / "shots").glob("*"):
                shutil.copy2(f, dst / "shots" / f.name)
        else:
            project.write_story(dst, project.new_story())
            config.write_project(dst, {"show": {"host": "C", "guests": [], "title": name, "subtitle": "", "topbar": ""}})
        self.refresh_projects()
        self.open_project(name)

    # ------------------------------------------------------------ saving
    def on_tab(self, _=None):
        if not self.proj:
            return
        i = self.nb.index("current")
        if i == 1:
            self.refresh_pops(self.pop_i())
        elif i == 2:
            self.refresh_guests()

    def save_all(self):
        if not self.proj or not self.dirty:
            return
        if "story" in self.dirty:
            project.write_story(self.proj, self.story)
        if "global" in self.dirty:
            config.write_global(self.gcfg)
        if "project" in self.dirty:
            config.write_project(self.proj, self.pcfg)
        self.dirty.clear()
        self.update_status()
        self.flash("已儲存")

    def flash(self, msg):
        self.v_dirty.set(msg)
        self.lb_dirty.configure(foreground=OK)
        self.root.after(1500, lambda: (self.lb_dirty.configure(foreground=ACCENT), self.update_status()))

    def on_close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("工作進行中", "還有工作在執行，要中止並關閉嗎？", parent=self.root):
                return
            self.proc.kill()
        if self.ask_save():
            self.root.destroy()

    # ============================================================ 01 SCRIPT
    def build_script_tab(self):
        tab = ttk.Frame(self.nb, padding=(0, 10, 0, 0))
        self.nb.add(tab, text=" 01  劇本 ")
        pw = ttk.PanedWindow(tab, orient="horizontal")
        pw.pack(fill="both", expand=True)

        # --- scenes
        left = ttk.Frame(pw, width=270)
        pw.add(left, weight=0)
        section(left, "01", "SCENES", "段落").pack(fill="x", pady=(0, 6))
        box, self.tv_sc = tree(left, [("i", "#", 34, False), ("ch", "CH", 74, False), ("title", "標題", 120, True),
                                      ("n", "句", 36, False)], height=20)
        box.pack(fill="both", expand=True)
        self.tv_sc.bind("<<TreeviewSelect>>", self.on_scene_select)
        bar = ttk.Frame(left)
        bar.pack(fill="x", pady=6)
        for txt, fn in (("＋", self.scene_add), ("⧉", self.scene_dup), ("－", self.scene_del),
                        ("↑", lambda: self.scene_move(-1)), ("↓", lambda: self.scene_move(1))):
            ttk.Button(bar, text=txt, width=3, style="Tool.TButton", command=fn).pack(side="left", padx=(0, 4))

        # --- scene form + lines + line form
        mid = ttk.Frame(pw)
        pw.add(mid, weight=1)
        section(mid, "02", "SCENE", "段落設定").pack(fill="x", padx=10, pady=(0, 6))
        f = ttk.Frame(mid)
        f.pack(fill="x", padx=10)
        self.v_ch, self.v_title, self.v_shot = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.v_note_a, self.v_note_b = tk.StringVar(), tk.StringVar()
        ttk.Label(f, text="頻道", style="Key.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.v_ch, width=10, font=MONO).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(f, text="標題", style="Key.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Entry(f, textvariable=self.v_title).grid(row=0, column=3, sticky="we", padx=6)
        ttk.Label(f, text="截圖", style="Key.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        sf = ttk.Frame(f)
        sf.grid(row=1, column=1, columnspan=3, sticky="w", padx=6, pady=(6, 0))
        self.cb_shot = ttk.Combobox(sf, textvariable=self.v_shot, width=24, font=MONO)
        self.cb_shot.pack(side="left")
        ttk.Button(sf, text="加入截圖…", command=self.add_shots).pack(side="left", padx=6)
        ttk.Label(sf, text="整段在台", style="Key.TLabel").pack(side="left", padx=(14, 6))
        self.fr_sc_guests = ttk.Frame(sf)
        self.fr_sc_guests.pack(side="left")
        ttk.Label(f, text="NOTE", style="Key.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(f, textvariable=self.v_note_a, width=22).grid(row=2, column=1, columnspan=2, sticky="we", padx=6, pady=(6, 0))
        ttk.Entry(f, textvariable=self.v_note_b).grid(row=2, column=3, sticky="we", padx=6, pady=(6, 0))
        f.columnconfigure(3, weight=1)
        self.bind(self.v_ch, lambda v: self.set_scene("ch", v.strip()))
        self.bind(self.v_title, lambda v: self.set_scene("title", v))
        self.bind(self.v_shot, lambda v: self.set_scene("shot", v.strip()))
        self.bind(self.v_note_a, lambda v: self.set_note(0, v))
        self.bind(self.v_note_b, lambda v: self.set_note(1, v))
        self.sc_guest_vars = {}

        section(mid, "03", "LINES", "台詞  ·  Ctrl+Enter 在下方新增一句").pack(fill="x", padx=10, pady=(14, 6))
        box, self.tv_ln = tree(mid, [("k", "#", 44, False), ("who", "講者", 84, False), ("eyes", "表情", 46, False),
                                     ("text", "台詞", 400, True), ("view", "鏡頭 x,y,w", 120, False),
                                     ("shot", "換圖", 90, False), ("au", "音", 30, False)], height=12)
        box.pack(fill="both", expand=True, padx=10)
        self.tv_ln.bind("<<TreeviewSelect>>", self.on_line_select)
        self.tv_ln.bind("<Double-Button-1>", lambda e: self.txt.focus_set())
        bar = ttk.Frame(mid)
        bar.pack(fill="x", padx=10, pady=6)
        for txt, fn in (("＋", self.line_add), ("⧉", self.line_dup), ("－", self.line_del),
                        ("↑", lambda: self.line_move(-1)), ("↓", lambda: self.line_move(1))):
            ttk.Button(bar, text=txt, width=3, style="Tool.TButton", command=fn).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="▶ 播放語音", command=self.play_line).pack(side="left", padx=(12, 4))
        ttk.Button(bar, text="重新錄這句", command=self.redo_line).pack(side="left")
        ttk.Button(bar, text="預覽這句畫面", style="Accent.TButton", command=self.preview_line).pack(side="right")

        section(mid, "04", "LINE", "台詞編輯").pack(fill="x", padx=10, pady=(8, 6))
        f = ttk.Frame(mid)
        f.pack(fill="x", padx=10, pady=(0, 6))
        self.v_who, self.v_eyes = tk.StringVar(), tk.StringVar()
        self.v_inherit = tk.BooleanVar()
        self.v_vx, self.v_vy, self.v_vw = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.v_lshot = tk.StringVar()
        ttk.Label(f, text="講者", style="Key.TLabel").grid(row=0, column=0, sticky="w")
        top = ttk.Frame(f)
        top.grid(row=0, column=1, sticky="w")
        self.cb_who = ttk.Combobox(top, textvariable=self.v_who, state="readonly", width=16, font=MONO)
        self.cb_who.pack(side="left", padx=(6, 18))
        ttk.Label(top, text="表情", style="Key.TLabel").pack(side="left", padx=(0, 6))
        for k, lab in EYES.items():
            ttk.Radiobutton(top, text=f"{k} {lab}", value=k, variable=self.v_eyes).pack(side="left", padx=(0, 8))
        self.txt = text_widget(f, 3)
        self.txt.grid(row=1, column=0, columnspan=2, sticky="we", pady=6)
        self.txt.bind("<<Modified>>", self.on_text_modified)
        self.txt.bind("<Control-Return>", lambda e: (self.line_add(), "break")[1])
        ttk.Label(f, text="鏡頭", style="Key.TLabel").grid(row=2, column=0, sticky="w")
        vf = ttk.Frame(f)
        vf.grid(row=2, column=1, sticky="w")
        ttk.Checkbutton(vf, text="沿用上一句", variable=self.v_inherit).pack(side="left", padx=(6, 10))
        self.view_entries = []
        for lab, var in (("x", self.v_vx), ("y", self.v_vy), ("w", self.v_vw)):
            ttk.Label(vf, text=lab, style="Muted.TLabel").pack(side="left")
            e = ttk.Spinbox(vf, textvariable=var, from_=0, to=9999, increment=20, width=5, font=MONO)
            e.pack(side="left", padx=(3, 8))
            self.view_entries.append(e)
        ttk.Button(vf, text="全畫面", command=lambda: self.set_view([0, 0, 1600])).pack(side="left", padx=(0, 14))
        ttk.Label(vf, text="換圖", style="Key.TLabel").pack(side="left", padx=(0, 6))
        self.cb_lshot = ttk.Combobox(vf, textvariable=self.v_lshot, width=18, font=MONO)
        self.cb_lshot.pack(side="left")
        f.columnconfigure(1, weight=1)
        self.bind(self.v_who, lambda v: self.set_line("who", v.split(" ")[0]))
        self.bind(self.v_eyes, lambda v: self.set_line("eyes", v))
        self.bind(self.v_lshot, lambda v: self.set_line("shot", v.strip() or None))
        self.bind(self.v_inherit, lambda v: self.on_inherit(v))
        for var in (self.v_vx, self.v_vy, self.v_vw):
            self.bind(var, lambda v: self.on_view_typed())

        # --- camera + preview
        right = ttk.Frame(pw, width=560)
        pw.add(right, weight=0)
        section(right, "05", "CAMERA", "鏡頭取景").pack(fill="x", padx=(10, 0), pady=(0, 6))
        self.CW, self.CH = 540, 400
        self.canvas = tk.Canvas(right, width=self.CW, height=self.CH, bg=GRID, highlightthickness=1,
                                highlightbackground=LINE)
        self.canvas.pack(padx=(10, 0))
        self.v_caminfo = tk.StringVar()
        ttk.Label(right, textvariable=self.v_caminfo, style="Muted.TLabel").pack(anchor="w", padx=(10, 0), pady=(4, 0))
        ttk.Label(right, text="框內拖曳＝移動 · 框外拖曳＝重新框選 · 滾輪＝縮放 · 雙擊＝全畫面",
                  style="Muted.TLabel").pack(anchor="w", padx=(10, 0))
        self.canvas.bind("<ButtonPress-1>", self.cam_press)
        self.canvas.bind("<B1-Motion>", self.cam_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.canvas.bind("<MouseWheel>", self.cam_wheel)
        self.canvas.bind("<Double-Button-1>", lambda e: self.set_view([0, 0, 1600]))
        section(right, "06", "PREVIEW", "成品畫面").pack(fill="x", padx=(10, 0), pady=(10, 6))
        self.lb_prev = tk.Label(right, bg=GRID, width=540, height=304, text="按「預覽這句畫面」", fg=MUTED, font=MONO_S,
                                image=self.blank, compound="center", highlightthickness=1, highlightbackground=LINE)
        self.lb_prev.pack(padx=(10, 0))
        self.lb_prev.bind("<Button-1>", lambda e: self.last_preview and os.startfile(self.last_preview))
        self.last_preview = None

    # --- scenes
    def scene(self):
        sc = self.story["scenes"]
        return sc[self.si] if 0 <= self.si < len(sc) else None

    def refresh_scenes(self, select=None):
        tv = self.tv_sc
        tv.delete(*tv.get_children())
        for i, sc in enumerate(self.story["scenes"]):
            tv.insert("", "end", iid=str(i), values=(i, sc["ch"], sc["title"], len(sc["lines"])))
        if select is not None and self.story["scenes"]:
            select = max(0, min(select, len(self.story["scenes"]) - 1))
            tv.selection_set(str(select)); tv.see(str(select))
            self.si = select
            self.load_scene()

    def refresh_scene_row(self):
        sc = self.scene()
        if sc and self.tv_sc.exists(str(self.si)):
            self.tv_sc.item(str(self.si), values=(self.si, sc["ch"], sc["title"], len(sc["lines"])))

    def on_scene_select(self, _=None):
        sel = self.tv_sc.selection()
        if sel and int(sel[0]) != self.si:
            self.si = int(sel[0])
            self.load_scene()

    def load_scene(self):
        sc = self.scene()
        if not sc:
            return
        self._loading = True
        self.v_ch.set(sc["ch"]); self.v_title.set(sc["title"]); self.v_shot.set(sc["shot"])
        note = sc.get("note") or ["", ""]
        self.v_note_a.set(note[0]); self.v_note_b.set(note[1])
        shots = self.shots()
        self.cb_shot["values"] = shots
        self.cb_lshot["values"] = [""] + shots
        for w in self.fr_sc_guests.winfo_children():
            w.destroy()
        self.sc_guest_vars = {}
        host = self.cfg()["show"].get("host", "C")
        for code, c in self.chars().items():
            if code == host:
                continue
            v = tk.BooleanVar(value=code in sc["guests"])
            ttk.Checkbutton(self.fr_sc_guests, text=f"{code} {c['name']}", variable=v,
                            command=self.on_scene_guests).pack(side="left", padx=(0, 8))
            self.sc_guest_vars[code] = v
        self._loading = False
        self.li = None
        self.refresh_lines(0 if sc["lines"] else None)

    def set_scene(self, key, v):
        sc = self.scene()
        if sc and sc[key] != v:
            sc[key] = v
            self.refresh_scene_row()
            self.mark("story")
            if key == "shot":
                self.draw_camera()

    def set_note(self, i, v):
        sc = self.scene()
        if sc:
            sc["note"] = list(sc.get("note") or ["", ""])
            sc["note"][i] = v
            self.mark("story")

    def on_scene_guests(self):
        sc = self.scene()
        sc["guests"] = [c for c, v in self.sc_guest_vars.items() if v.get()]
        self.mark("story")

    def scene_add(self):
        n = len(self.story["scenes"])
        self.story["scenes"].insert(self.si + 1, project.new_scene(f"CH-{n:02d}", "新段落", self.scene()["shot"] if self.scene() else ""))
        self.mark("story"); self.refresh_scenes(self.si + 1)

    def scene_dup(self):
        if self.scene():
            self.story["scenes"].insert(self.si + 1, json.loads(json.dumps(self.scene())))
            self.mark("story"); self.refresh_scenes(self.si + 1)

    def scene_del(self):
        sc = self.scene()
        if not sc or len(self.story["scenes"]) == 1:
            return
        if sc["lines"] and not messagebox.askyesno("刪除段落", f"刪除「{sc['ch']} {sc['title']}」和裡面 {len(sc['lines'])} 句台詞？", parent=self.root):
            return
        del self.story["scenes"][self.si]
        self.mark("story"); self.refresh_scenes(self.si - 1 if self.si else 0)

    def scene_move(self, d):
        s, j = self.story["scenes"], self.si + d
        if 0 <= j < len(s):
            s[self.si], s[j] = s[j], s[self.si]
            self.mark("story"); self.refresh_scenes(j)

    def add_shots(self):
        if not self.proj:
            return
        files = filedialog.askopenfilenames(parent=self.root, title="加入截圖",
                                            filetypes=[("圖片", "*.png *.jpg *.jpeg *.webp"), ("全部", "*.*")])
        (self.proj / "shots").mkdir(exist_ok=True)
        for f in files:
            shutil.copy2(f, self.proj / "shots" / Path(f).name)
        if files:
            shots = self.shots()
            self.cb_shot["values"] = shots
            self.cb_lshot["values"] = [""] + shots
            if not self.v_shot.get():
                self.v_shot.set(Path(files[0]).name)

    # --- lines
    def line(self):
        sc = self.scene()
        if sc and self.li is not None and 0 <= self.li < len(sc["lines"]):
            return sc["lines"][self.li]
        return None

    def line_values(self, i, ln):
        c = self.chars().get(ln["who"])
        who = f"{ln['who']} {c['name']}" if c else f"{ln['who']} ?"
        view = ",".join(str(v) for v in ln["view"]) if ln.get("view") else "↑"
        return (self.line_k(self.si, i), who, EYES.get(ln["eyes"], ln["eyes"]), ln["text"], view,
                ln.get("shot") or "", "●" if self.audio_ok(ln) else "○")

    def refresh_lines(self, select=None):
        tv = self.tv_ln
        tv.delete(*tv.get_children())
        sc = self.scene()
        chars = self.chars()
        self.cb_who["values"] = [f"{k} {c['name']}" for k, c in chars.items()]
        for i, ln in enumerate(sc["lines"] if sc else []):
            tv.insert("", "end", iid=str(i), values=self.line_values(i, ln),
                      tags=("bad",) if ln["who"] not in chars else ())
        if select is not None and sc and sc["lines"]:
            select = max(0, min(select, len(sc["lines"]) - 1))
            tv.selection_set(str(select)); tv.see(str(select))
            self.li = select
            self.load_line()
        else:
            self.li = None
            self.load_line()

    def refresh_line_row(self):
        ln = self.line()
        if ln and self.tv_ln.exists(str(self.li)):
            self.tv_ln.item(str(self.li), values=self.line_values(self.li, ln))

    def on_line_select(self, _=None):
        sel = self.tv_ln.selection()
        if sel and int(sel[0]) != self.li:
            self.li = int(sel[0])
            self.load_line()

    def load_line(self):
        ln = self.line()
        self._loading = True
        state = "normal" if ln else "disabled"
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        if ln:
            c = self.chars().get(ln["who"])
            self.v_who.set(f"{ln['who']} {c['name']}" if c else ln["who"])
            self.v_eyes.set(ln["eyes"])
            self.txt.insert("1.0", ln["text"])
            self.v_lshot.set(ln.get("shot") or "")
            self.v_inherit.set(ln.get("view") is None)
            v = ln.get("view") or self.resolved(self.li)[1]
            self.v_vx.set(v[0]); self.v_vy.set(v[1]); self.v_vw.set(v[2])
        else:
            for var in (self.v_who, self.v_eyes, self.v_lshot, self.v_vx, self.v_vy, self.v_vw):
                var.set("")
        self.txt.configure(state=state)
        self.txt.edit_modified(False)
        self.txt.edit_reset()
        for e in self.view_entries:
            e.configure(state="disabled" if not ln or self.v_inherit.get() else "normal")
        self._loading = False
        self.draw_camera()

    def set_line(self, key, v):
        ln = self.line()
        if ln and ln.get(key) != v:
            ln[key] = v
            self.refresh_line_row()
            self.mark("story")
            if key == "shot":
                self.draw_camera()
            if key in ("who", "text"):
                self.update_status()

    def on_text_modified(self, _=None):
        if not self.txt.edit_modified():
            return
        self.txt.edit_modified(False)
        if not self._loading:
            self.set_line("text", self.txt.get("1.0", "end-1c").replace("\n", ""))

    def on_inherit(self, inherit):
        ln = self.line()
        if not ln:
            return
        for e in self.view_entries:
            e.configure(state="disabled" if inherit else "normal")
        if inherit:
            self.set_line("view", None)
        else:
            self.set_line("view", list(self.resolved(self.li)[1]))
        self.load_line()

    def on_view_typed(self):
        if self.v_inherit.get():
            return
        try:
            v = [int(float(self.v_vx.get())), int(float(self.v_vy.get())), int(float(self.v_vw.get()))]
        except ValueError:
            return
        if v[2] > 0:
            self.set_line("view", v)
            self.draw_camera()

    def set_view(self, v):
        ln = self.line()
        if not ln:
            return
        v = [int(round(x)) for x in v]
        ln["view"] = v
        self._loading = True
        self.v_inherit.set(False)
        self.v_vx.set(v[0]); self.v_vy.set(v[1]); self.v_vw.set(v[2])
        for e in self.view_entries:
            e.configure(state="normal")
        self._loading = False
        self.refresh_line_row()
        self.mark("story")
        self.draw_camera()

    def new_line_here(self, ln):
        sc = self.scene()
        i = (self.li + 1) if self.li is not None else len(sc["lines"])
        sc["lines"].insert(i, ln)
        self.mark("story"); self.refresh_scene_row(); self.refresh_lines(i)
        self.txt.focus_set()

    def line_add(self):
        if self.scene() is None:
            return
        cur = self.line()
        who = cur["who"] if cur else self.cfg()["show"].get("host", "C")
        self.new_line_here(project.new_line(who, "", "o"))

    def line_dup(self):
        if self.line():
            self.new_line_here(dict(self.line()))

    def line_del(self):
        sc = self.scene()
        if self.line():
            del sc["lines"][self.li]
            self.mark("story"); self.refresh_scene_row(); self.refresh_lines(max(0, self.li - 1))

    def line_move(self, d):
        sc, j = self.scene(), (self.li or 0) + d
        if self.line() and 0 <= j < len(sc["lines"]):
            L = sc["lines"]
            L[self.li], L[j] = L[j], L[self.li]
            self.mark("story"); self.refresh_lines(j)

    def resolved(self, li):
        """(shot, view) in effect at line li of the current scene, the way render.resolve_views works."""
        sc = self.scene()
        shot, view = sc["shot"], [0, 0, 1600]
        for ln in sc["lines"][:li + 1]:
            shot = ln.get("shot") or shot
            view = ln.get("view") or view
        return shot, view

    def play_line(self):
        ln = self.line()
        if not ln:
            return
        sp = self.chars().get(ln["who"])
        p = project.audio_path(self.proj, sp, ln["text"]) if sp else None
        if not p or not p.exists():
            self.flash_msg("這句還沒有語音，先按「產生語音」")
            return
        winsound.PlaySound(str(p), winsound.SND_FILENAME | winsound.SND_ASYNC)

    def redo_line(self):
        ln = self.line()
        if not ln:
            return
        sp = self.chars().get(ln["who"])
        for ext in ("wav", "mp3"):
            p = project.audio_path(self.proj, sp, ln["text"], ext)
            if p.exists():
                p.unlink()
        self.refresh_line_row()
        self.run_tts()

    def preview_line(self):
        if self.line() is None:
            return
        self.run_task("預覽", ["render.py", self.rel(), "preview", f"#{self.line_k(self.si, self.li)}"], switch=False)

    def flash_msg(self, msg):
        self.v_dirty.set(msg)
        self.root.after(2500, self.update_status)

    # --- camera canvas
    def draw_camera(self):
        cv = self.canvas
        cv.delete("all")
        self.cam = None
        sc = self.scene()
        if not sc or not self.proj:
            return
        li = self.li if self.li is not None else -1
        shot, view = self.resolved(li) if li >= 0 else (sc["shot"], [0, 0, 1600])
        im = self.image(self.proj / "shots" / shot) if shot else None
        for x in range(0, self.CW, 20):
            cv.create_line(x, 0, x, self.CH, fill="#E0E0DA")
        for y in range(0, self.CH, 20):
            cv.create_line(0, y, self.CW, y, fill="#E0E0DA")
        if im is None:
            cv.create_text(self.CW / 2, self.CH / 2, text=f"找不到截圖  {shot or '(未設定)'}", fill=MUTED, font=MONO)
            self.v_caminfo.set("")
            return
        s = min((self.CW - 16) / im.width, (self.CH - 16) / im.height)
        ox, oy = (self.CW - im.width * s) / 2, (self.CH - im.height * s) / 2
        x, y, w, h = clamp_view(im.width, im.height, view)
        small = im.convert("RGB").resize((round(im.width * s), round(im.height * s)), Image.BILINEAR)
        dim = Image.blend(small, Image.new("RGB", small.size, (20, 20, 20)), 0.55)
        box = tuple(round(v * s) for v in (x, y, x + w, y + h))
        dim.paste(small.crop(box), box[:2])
        cv.create_image(ox, oy, anchor="nw", image=self.photo("cam", dim))
        X0, Y0, X1, Y1 = ox + x * s, oy + y * s, ox + (x + w) * s, oy + (y + h) * s
        inherited = self.line() is not None and self.line().get("view") is None
        cv.create_rectangle(X0, Y0, X1, Y1, outline=ACCENT, width=2, dash=(6, 4) if inherited else None)
        L = 10
        for cx, cy, dx, dy in ((X0, Y0, 1, 1), (X1, Y0, -1, 1), (X0, Y1, 1, -1), (X1, Y1, -1, -1)):
            cv.create_line(cx, cy, cx + dx * L, cy, fill=ACCENT, width=4)
            cv.create_line(cx, cy, cx, cy + dy * L, fill=ACCENT, width=4)
        cv.create_line((X0 + X1) / 2 - 6, (Y0 + Y1) / 2, (X0 + X1) / 2 + 6, (Y0 + Y1) / 2, fill=ACCENT)
        cv.create_line((X0 + X1) / 2, (Y0 + Y1) / 2 - 6, (X0 + X1) / 2, (Y0 + Y1) / 2 + 6, fill=ACCENT)
        label = f" {int(x)},{int(y)}  w{int(w)} " + (" 沿用 " if inherited else "")
        t = cv.create_text(X0 + 4, Y0 + 4, anchor="nw", text=label, fill="#FFFFFF", font=MONO_S)
        cv.create_rectangle(cv.bbox(t), fill=ACCENT, width=0)
        cv.tag_raise(t)
        self.cam = dict(s=s, ox=ox, oy=oy, iw=im.width, ih=im.height, box=(x, y, w))
        self.v_caminfo.set(f"SHOT {shot}   {im.width}×{im.height}px   VIEW x={int(x)} y={int(y)} w={int(w)} "
                           f"({w / im.width * 100:.0f}% 寬)")

    def cam_xy(self, e):
        c = self.cam
        return (e.x - c["ox"]) / c["s"], (e.y - c["oy"]) / c["s"]

    def cam_press(self, e):
        if not self.cam or not self.line():
            self._drag = None
            return
        px, py = self.cam_xy(e)
        x, y, w = self.cam["box"]
        inside = x <= px <= x + w and y <= py <= y + w * 9 / 16
        self._drag = dict(mode="move" if inside else "new", px=px, py=py, box=(x, y, w))

    def cam_drag(self, e):
        d = getattr(self, "_drag", None)
        if not d:
            return
        px, py = self.cam_xy(e)
        if d["mode"] == "move":
            x, y, w = d["box"]
            self.set_view(clamp_view(self.cam["iw"], self.cam["ih"], (x + px - d["px"], y + py - d["py"], w))[:3])
        else:
            w = max(80, abs(px - d["px"]), abs(py - d["py"]) * 16 / 9)
            x = d["px"] if px >= d["px"] else d["px"] - w
            y = d["py"] if py >= d["py"] else d["py"] - w * 9 / 16
            self.set_view(clamp_view(self.cam["iw"], self.cam["ih"], (x, y, w))[:3])

    def cam_wheel(self, e):
        if not self.cam or not self.line():
            return
        x, y, w = self.cam["box"]
        k = 0.92 if e.delta > 0 else 1 / 0.92
        nw = max(80, min(self.cam["iw"], w * k))
        cx, cy = x + w / 2, y + w * 9 / 32
        self.set_view(clamp_view(self.cam["iw"], self.cam["ih"], (cx - nw / 2, cy - nw * 9 / 32, nw))[:3])

    def show_preview(self, path):
        self.last_preview = path
        for lb, slot, w in ((self.lb_prev, "prev", 540), (self.lb_out_prev, "outprev", 760)):
            if not path:
                lb.configure(image=self.blank, text="尚無預覽")
                continue
            im = self.image(path)
            ph = self.photo(slot, im.resize((w, round(w * im.height / im.width)), Image.LANCZOS))
            lb.configure(image=ph, text="", width=w, height=round(w * im.height / im.width))

    # ============================================================ 02 POPS
    def build_pops_tab(self):
        tab = ttk.Frame(self.nb, padding=(0, 10, 0, 0))
        self.nb.add(tab, text=" 02  蓋章 ")
        left = ttk.Frame(tab)
        left.pack(side="left", fill="both", expand=True)
        section(left, "01", "STAMPS", "台詞包含觸發字串時，螢幕右上角跳出螢光標籤").pack(fill="x", pady=(0, 6))
        box, self.tv_pop = tree(left, [("i", "#", 40, False), ("trig", "觸發字串", 300, True),
                                       ("label", "標籤", 220, True), ("hits", "命中", 60, False)], height=22)
        box.pack(fill="both", expand=True)
        self.tv_pop.bind("<<TreeviewSelect>>", lambda e: self.load_pop())
        bar = ttk.Frame(left)
        bar.pack(fill="x", pady=6)
        for txt, fn in (("＋", self.pop_add), ("－", self.pop_del), ("↑", lambda: self.pop_move(-1)), ("↓", lambda: self.pop_move(1))):
            ttk.Button(bar, text=txt, width=3, style="Tool.TButton", command=fn).pack(side="left", padx=(0, 4))

        right = ttk.Frame(tab, width=620)
        right.pack(side="left", fill="both", padx=(16, 0))
        right.pack_propagate(False)
        section(right, "02", "EDIT", "編輯").pack(fill="x", pady=(0, 6))
        f = ttk.Frame(right)
        f.pack(fill="x")
        self.v_pop_t, self.v_pop_l = tk.StringVar(), tk.StringVar()
        ttk.Label(f, text="觸發字串", style="Key.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(f, textvariable=self.v_pop_t, width=40).grid(row=0, column=1, sticky="we", padx=6)
        ttk.Label(f, text="標籤", style="Key.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(f, textvariable=self.v_pop_l, width=40, font=MONO).grid(row=1, column=1, sticky="we", padx=6)
        f.columnconfigure(1, weight=1)
        ttk.Label(right, text="同一句命中多個時，用清單裡最上面那個。", style="Muted.TLabel").pack(anchor="w", pady=4)
        self.bind(self.v_pop_t, lambda v: self.set_pop(0, v))
        self.bind(self.v_pop_l, lambda v: self.set_pop(1, v))
        section(right, "03", "MATCHES", "命中的台詞").pack(fill="x", pady=(14, 6))
        box, self.tv_hit = tree(right, [("k", "#", 44, False), ("ch", "CH", 70, False), ("text", "台詞", 400, True)], height=14)
        box.pack(fill="both", expand=True)
        self.tv_hit.bind("<Double-Button-1>", self.jump_hit)
        ttk.Label(right, text="雙擊跳到該句", style="Muted.TLabel").pack(anchor="w", pady=4)

    def all_lines(self):
        k = 0
        for si, sc in enumerate(self.story["scenes"]):
            for li, ln in enumerate(sc["lines"]):
                yield k, si, li, sc, ln
                k += 1

    def pop_hits(self, trig):
        return [x for x in self.all_lines() if trig and trig in x[4]["text"]]

    def refresh_pops(self, select=None):
        tv = self.tv_pop
        tv.delete(*tv.get_children())
        for i, (trig, lab) in enumerate(self.story["pops"]):
            n = len(self.pop_hits(trig))
            tv.insert("", "end", iid=str(i), values=(i, trig, lab, n), tags=() if n else ("bad",))
        if select is not None and self.story["pops"]:
            select = max(0, min(select, len(self.story["pops"]) - 1))
            tv.selection_set(str(select)); tv.see(str(select))
        self.load_pop()

    def pop_i(self):
        sel = self.tv_pop.selection()
        return int(sel[0]) if sel else None

    def load_pop(self):
        i = self.pop_i()
        self._loading = True
        p = self.story["pops"][i] if i is not None else ["", ""]
        self.v_pop_t.set(p[0]); self.v_pop_l.set(p[1])
        self._loading = False
        self.refresh_hits()

    def refresh_hits(self):
        self.tv_hit.delete(*self.tv_hit.get_children())
        i = self.pop_i()
        if i is None:
            return
        for k, si, li, sc, ln in self.pop_hits(self.story["pops"][i][0]):
            self.tv_hit.insert("", "end", iid=f"{si}:{li}", values=(k, sc["ch"], ln["text"]))

    def set_pop(self, j, v):
        i = self.pop_i()
        if i is None:
            return
        self.story["pops"][i][j] = v
        n = len(self.pop_hits(self.story["pops"][i][0]))
        self.tv_pop.item(str(i), values=(i, *self.story["pops"][i], n), tags=() if n else ("bad",))
        self.mark("story")
        self.refresh_hits()

    def pop_add(self):
        i = self.pop_i()
        i = len(self.story["pops"]) if i is None else i + 1
        self.story["pops"].insert(i, ["", "NEW"])
        self.mark("story"); self.refresh_pops(i)

    def pop_del(self):
        i = self.pop_i()
        if i is not None:
            del self.story["pops"][i]
            self.mark("story"); self.refresh_pops(i - 1 if i else 0)

    def pop_move(self, d):
        i = self.pop_i()
        P = self.story["pops"]
        if i is not None and 0 <= i + d < len(P):
            P[i], P[i + d] = P[i + d], P[i]
            self.mark("story"); self.refresh_pops(i + d)

    def jump_hit(self, _=None):
        sel = self.tv_hit.selection()
        if not sel:
            return
        si, li = map(int, sel[0].split(":"))
        self.nb.select(0)
        self.refresh_scenes(si)
        self.refresh_lines(li)

    # ============================================================ 03 SHOW
    def build_show_tab(self):
        tab = ttk.Frame(self.nb, padding=(0, 10, 0, 0))
        self.nb.add(tab, text=" 03  演出 ")
        left = ttk.Frame(tab, width=640)
        left.pack(side="left", fill="y")
        section(left, "01", "TITLES", "片頭與標題列（本報告）").pack(fill="x", pady=(0, 8))
        f = ttk.Frame(left)
        f.pack(fill="x")
        self.v_show = {}
        for r, (key, lab, hint) in enumerate((("title", "片頭大標", "留空 = 資料夾名稱"), ("subtitle", "片頭副標", ""),
                                              ("topbar", "右上角小字", "留空 = 同片頭大標"))):
            ttk.Label(f, text=lab, style="Key.TLabel").grid(row=r, column=0, sticky="w", pady=4)
            v = tk.StringVar()
            ttk.Entry(f, textvariable=v, width=52).grid(row=r, column=1, sticky="we", padx=8)
            ttk.Label(f, text=hint, style="Muted.TLabel").grid(row=r, column=2, sticky="w")
            self.bind(v, lambda val, k=key: self.set_show(k, val))
            self.v_show[key] = v

        section(left, "02", "CAST", "主持人與上鏡配角").pack(fill="x", pady=(22, 8))
        f = ttk.Frame(left)
        f.pack(fill="x")
        ttk.Label(f, text="主持人", style="Key.TLabel").grid(row=0, column=0, sticky="w")
        self.v_host = tk.StringVar()
        self.cb_host = ttk.Combobox(f, textvariable=self.v_host, state="readonly", width=18, font=MONO)
        self.cb_host.grid(row=0, column=1, sticky="w", padx=8)
        self.cb_host.bind("<<ComboboxSelected>>", lambda e: self.set_host(self.v_host.get().split(" ")[0]))
        self.v_auto = tk.BooleanVar()
        ttk.Checkbutton(f, text="配角自動判斷（劇本裡有台詞的角色）", variable=self.v_auto,
                        command=self.on_auto_guests).grid(row=0, column=2, sticky="w", padx=12)
        g = ttk.Frame(left)
        g.pack(fill="x", pady=10)
        lb_opts = dict(font=UI, bg=PANEL, fg=INK, relief="flat", highlightthickness=1, highlightbackground=LINE,
                       selectbackground=ACCENT_SOFT, selectforeground=INK, activestyle="none", height=7, width=22,
                       exportselection=False)
        ttk.Label(g, text="候補", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(g, text="上鏡（順序 = 由左到右站位）", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        self.lb_avail = tk.Listbox(g, **lb_opts)
        self.lb_avail.grid(row=1, column=0)
        mb = ttk.Frame(g)
        mb.grid(row=1, column=1, padx=8)
        for txt, fn in (("加入 →", self.guest_add), ("← 移除", self.guest_remove), ("↑", lambda: self.guest_move(-1)),
                        ("↓", lambda: self.guest_move(1))):
            ttk.Button(mb, text=txt, command=fn, width=8).pack(pady=2)
        self.lb_stage = tk.Listbox(g, **lb_opts)
        self.lb_stage.grid(row=1, column=2)
        self.v_castmsg = tk.StringVar()
        self.lb_castmsg = ttk.Label(left, textvariable=self.v_castmsg, wraplength=600)
        self.lb_castmsg.pack(anchor="w", pady=4)

        right = ttk.Frame(tab)
        right.pack(side="left", fill="both", expand=True, padx=(24, 0))
        section(right, "03", "STAGE", "站位示意（1920×1080，1:3）").pack(fill="x", pady=(0, 8))
        self.stage = tk.Canvas(right, width=640, height=360, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        self.stage.pack(anchor="w")
        ttk.Label(right, text="配角站位的 x 座標在「05 設定 › LAYOUT › guest_x」。", style="Muted.TLabel").pack(anchor="w", pady=6)

    def show_cfg(self):
        return self.pcfg.setdefault("show", {})

    def load_show(self):
        self._loading = True
        show = self.cfg()["show"]
        for k, v in self.v_show.items():
            v.set(self.pcfg.get("show", {}).get(k, ""))
        chars = self.chars()
        self.cb_host["values"] = [f"{k} {c['name']}" for k, c in chars.items()]
        host = show.get("host", "C")
        self.v_host.set(f"{host} {chars[host]['name']}" if host in chars else host)
        self.v_auto.set(not show.get("guests"))
        self._loading = False
        self.refresh_guests()

    def set_show(self, key, v):
        self.show_cfg()[key] = v
        self.mark("project")

    def set_host(self, code):
        show = self.show_cfg()
        show["host"] = code
        if code in show.get("guests", []):
            show["guests"].remove(code)
        self.mark("project")
        self.refresh_guests()
        self.load_scene()

    def current_guests(self):
        rt = self.runtime()
        return config.check_cast(self.cfg(), rt.SCENES)

    def refresh_guests(self):
        host, guests, err = self.current_guests()
        chars = self.chars()
        self.lb_avail.delete(0, "end"); self.lb_stage.delete(0, "end")
        for g in guests:
            self.lb_stage.insert("end", f"{g}  {chars.get(g, {}).get('name', '?')}")
        for k, c in chars.items():
            if k != host and k not in guests:
                self.lb_avail.insert("end", f"{k}  {c['name']}")
        state = "disabled" if self.v_auto.get() else "normal"
        self.lb_avail.configure(state=state); self.lb_stage.configure(state=state)
        self.v_castmsg.set(err or f"OK  ·  主持 {host}  ·  配角 {', '.join(guests) or '（無）'}")
        self.lb_castmsg.configure(style="Bad.TLabel" if err else "Ok.TLabel")
        self.draw_stage(host, guests)

    def on_auto_guests(self):
        if self.v_auto.get():
            self.show_cfg()["guests"] = []
        else:
            self.show_cfg()["guests"] = list(self.current_guests()[1])
        self.mark("project")
        self.refresh_guests()

    def stage_list(self):
        return list(self.show_cfg().get("guests") or self.current_guests()[1])

    def guest_add(self):
        sel = self.lb_avail.curselection()
        if sel and not self.v_auto.get():
            g = self.stage_list() + [self.lb_avail.get(sel[0]).split()[0]]
            self.show_cfg()["guests"] = g
            self.mark("project"); self.refresh_guests()

    def guest_remove(self):
        sel = self.lb_stage.curselection()
        if sel and not self.v_auto.get():
            g = self.stage_list()
            del g[sel[0]]
            self.show_cfg()["guests"] = g
            self.mark("project"); self.refresh_guests()

    def guest_move(self, d):
        sel = self.lb_stage.curselection()
        g = self.stage_list()
        if sel and not self.v_auto.get() and 0 <= sel[0] + d < len(g):
            i = sel[0]
            g[i], g[i + d] = g[i + d], g[i]
            self.show_cfg()["guests"] = g
            self.mark("project"); self.refresh_guests()
            self.lb_stage.selection_set(i + d)

    def draw_stage(self, host, guests):
        cv, k = self.stage, 1 / 3
        cv.delete("all")
        for x in range(0, 640, 20):
            cv.create_line(x, 0, x, 360, fill=GRID)
        for y in range(0, 360, 20):
            cv.create_line(0, y, 640, y, fill=GRID)
        R = lambda x, y, w, h, **kw: cv.create_rectangle(x * k, y * k, (x + w) * k, (y + h) * k, **kw)
        R(636, 132, 1184, 666, outline=INK, fill="#2A2A2A")
        cv.create_text((636 + 592) * k, (132 + 333) * k, text="MONITOR", fill="#888", font=MONO_S)
        R(60, 836, 1800, 214, outline=INK, fill=PANEL)
        cv.create_text(80 * k, 900 * k, anchor="w", text="DIALOG", fill=MUTED, font=MONO_S)
        R(60, 116, 500, 112, outline=INK, fill=PANEL)
        cv.create_text(80 * k, 172 * k, anchor="w", text="NOTE", fill=MUTED, font=MONO_S)
        chars = self.chars()
        if host in chars:   # host sprite: ~90×110 px × 5, bottom-centre at (325, 812)
            R(325 - 225, 812 - 550, 450, 550, outline=ACCENT, width=2, dash=(4, 3))
            cv.create_text(325 * k, 520 * k, text=f"HOST\n{chars[host]['name']}", fill=ACCENT, font=MONO_B, justify="center")
        table = self.cfg()["layout"]["guest_x"]
        for g, x in zip(guests, guest_slots(table, len(guests))):
            R(x, 836 - 440, 360, 440, outline=INK, width=1, dash=(3, 3))
            cv.create_text((x + 180) * k, 600 * k, text=f"{g}\n{chars.get(g, {}).get('name', '?')}\nx={x}",
                           fill=INK, font=MONO_S, justify="center")

    # ============================================================ 04 CHARACTERS
    def build_chars_tab(self):
        tab = ttk.Frame(self.nb, padding=(0, 10, 0, 0))
        self.nb.add(tab, text=" 04  角色 ")
        left = ttk.Frame(tab, width=260)
        left.pack(side="left", fill="y")
        section(left, "01", "ROSTER", "角色名冊（全域）").pack(fill="x", pady=(0, 6))
        box, self.tv_ch = tree(left, [("code", "代號", 54, False), ("name", "名稱", 120, True), ("anim", "動畫", 46, False)], height=16)
        box.pack(fill="both", expand=True)
        self.tv_ch.bind("<<TreeviewSelect>>", lambda e: self.load_char())
        bar = ttk.Frame(left)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="＋ 新角色", command=self.char_add).pack(side="left")
        ttk.Button(bar, text="刪除", command=self.char_del).pack(side="left", padx=6)

        mid = ttk.Frame(tab)
        mid.pack(side="left", fill="both", expand=True, padx=(18, 0))
        section(mid, "02", "PERSONA", "名牌與聲線").pack(fill="x", pady=(0, 8))
        f = ttk.Frame(mid)
        f.pack(fill="x")
        self.v_c = {k: tk.StringVar() for k in ("name", "color", "voice", "rate", "pitch", "sprite", "card")}
        self.v_hires = tk.BooleanVar()
        ttk.Label(f, text="名稱", style="Key.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.v_c["name"], width=20).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(f, text="名牌色", style="Key.TLabel").grid(row=0, column=2, sticky="w")
        ColorField(f, self.v_c["color"]).grid(row=0, column=3, sticky="w", padx=8)
        self.plate = tk.Label(f, text="", font=("Segoe UI Black", 14), fg="#FFFFFF", padx=14, pady=2,
                              highlightthickness=3, highlightbackground="#3B1F14")
        self.plate.grid(row=0, column=4, sticky="w", padx=12)
        ttk.Label(f, text="聲線", style="Key.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        self.cb_voice = ttk.Combobox(f, textvariable=self.v_c["voice"], values=VOICES, width=30, font=MONO)
        self.cb_voice.grid(row=1, column=1, columnspan=2, sticky="w", padx=8)
        ttk.Button(f, text="載入完整聲線清單", command=self.load_voices).grid(row=1, column=3, columnspan=2, sticky="w", padx=8)
        ttk.Label(f, text="語速", style="Key.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.v_c["rate"], width=10, font=MONO).grid(row=2, column=1, sticky="w", padx=8)
        ttk.Label(f, text="音高", style="Key.TLabel").grid(row=2, column=2, sticky="w")
        ttk.Entry(f, textvariable=self.v_c["pitch"], width=10, font=MONO).grid(row=2, column=3, sticky="w", padx=8)
        ttk.Label(f, text="例：+16%  ·  -4Hz", style="Muted.TLabel").grid(row=2, column=4, sticky="w", padx=12)
        ttk.Label(f, text="試聽", style="Key.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        self.v_sample = tk.StringVar(value="各位好，今天由我來為大家報告。")
        ttk.Entry(f, textvariable=self.v_sample, width=44).grid(row=3, column=1, columnspan=3, sticky="we", padx=8)
        ttk.Button(f, text="▶ 試聽", command=self.audition).grid(row=3, column=4, sticky="w", padx=12)
        ttk.Label(mid, text="改了聲線、語速或音高，用到這個角色的台詞會在下次「產生語音」時自動重錄。",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

        section(mid, "03", "SPRITE", "像素立繪").pack(fill="x", pady=(18, 8))
        f2 = ttk.Frame(mid)
        f2.pack(fill="x")
        ttk.Label(f2, text="圖檔", style="Key.TLabel").grid(row=0, column=0, sticky="w")
        self.cb_sprite = ttk.Combobox(f2, textvariable=self.v_c["sprite"], width=20, font=MONO)
        self.cb_sprite.grid(row=0, column=1, sticky="w", padx=8)
        ttk.Checkbutton(f2, text="高解析度圖（不是格狀像素圖，縮放到同高）", variable=self.v_hires).grid(row=0, column=2, sticky="w", padx=8)
        ttk.Button(f2, text="匯入 spr_*.png…", command=lambda: self.import_art("spr")).grid(row=0, column=3, padx=8)
        self.v_anim = tk.StringVar()
        ttk.Label(f2, textvariable=self.v_anim, style="Muted.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=4)
        self.sprite_cv = tk.Canvas(mid, width=560, height=330, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        self.sprite_cv.pack(anchor="w")
        self._anim_tick = 0
        self.root.after(260, self.animate_sprite)

        right = ttk.Frame(tab, width=470)
        right.pack(side="left", fill="y", padx=(18, 0))
        right.pack_propagate(False)
        section(right, "04", "CARD", "片頭角色卡").pack(fill="x", pady=(0, 8))
        f3 = ttk.Frame(right)
        f3.pack(fill="x")
        ttk.Label(f3, text="角色卡", style="Key.TLabel").pack(side="left")
        self.cb_card = ttk.Combobox(f3, textvariable=self.v_c["card"], width=16, font=MONO)
        self.cb_card.pack(side="left", padx=8)
        ttk.Button(f3, text="匯入 card_*.png…", command=lambda: self.import_art("card")).pack(side="left")
        body = ttk.Frame(right)
        body.pack(fill="both", expand=True, pady=8)
        self.card_lb = tk.Label(body, bg=GRID, width=180, height=260, image=self.blank, compound="center",
                                highlightthickness=1, highlightbackground=LINE)
        self.card_lb.pack(side="left", anchor="n")
        self.card_form = ttk.Frame(body)
        self.card_form.pack(side="left", fill="both", expand=True, padx=(12, 0), anchor="n")

        for key in ("name", "color", "voice", "rate", "pitch", "sprite", "card"):
            self.bind(self.v_c[key], lambda v, k=key: self.set_char(k, v))
        self.bind(self.v_hires, lambda v: self.set_char("hires", v))

    def char_code(self):
        sel = self.tv_ch.selection()
        return sel[0] if sel else None

    def refresh_chars(self, select=None):
        tv = self.tv_ch
        cur = select or self.char_code()
        tv.delete(*tv.get_children())
        for k, c in self.gcfg.get("characters", {}).items():
            tv.insert("", "end", iid=k, values=(k, c["name"], "嘴" if c.get("sprite") in sprites.ANIMATED else "—"))
        names = lambda pre: sorted(p.stem[len(pre):] for p in (ROOT / "characters").glob(f"{pre}*.png"))
        self.cb_sprite["values"] = names("spr_")
        self.cb_card["values"] = names("card_")
        kids = tv.get_children()
        if kids:
            cur = cur if cur in kids else kids[0]
            tv.selection_set(cur)
        self.load_char()

    def load_char(self):
        code = self.char_code()
        c = self.gcfg.get("characters", {}).get(code)
        if not c:
            return
        self._loading = True
        for k, v in self.v_c.items():
            v.set(rgb_hex(c[k]) if k == "color" else c.get(k, ""))
        self.v_hires.set(bool(c.get("hires")))
        self._loading = False
        self.paint_char()
        self.load_card_form()

    def set_char(self, key, v):
        code = self.char_code()
        c = self.gcfg.get("characters", {}).get(code)
        if not c:
            return
        if key == "color":
            try:
                v = hex_rgb(v)
            except ValueError:
                return
        if key == "hires" and not v:
            c.pop("hires", None)
        else:
            c[key] = v
        self.mark("global")
        self.tv_ch.item(code, values=(code, c["name"], "嘴" if c.get("sprite") in sprites.ANIMATED else "—"))
        self.paint_char()
        if key == "card":
            self.load_card_form()
        if key in ("voice", "rate", "pitch", "name"):
            self.refresh_lines(self.li)
            self.update_status()

    def paint_char(self):
        code = self.char_code()
        c = self.gcfg["characters"].get(code)
        if not c:
            return
        self.plate.configure(text=c["name"], bg=rgb_hex(c["color"]))
        sp = c.get("sprite", "")
        self.v_anim.set(f"characters/spr_{sp}.png  ·  " + ("有嘴巴動畫（寫在 sprites.py）" if sp in sprites.ANIMATED
                                                          else "沒有嘴巴動畫，直接使用原圖"))
        card = ROOT / "characters" / f"card_{c.get('card', '')}.png"
        im = self.image(card)
        if im:
            h = 260
            self.card_lb.configure(image=self.photo("card", im.resize((round(im.width * h / im.height), h), Image.LANCZOS)),
                                   text="", width=round(im.width * h / im.height), height=h)
        else:
            self.card_lb.configure(image=self.blank, text=f"找不到\ncard_{c.get('card', '')}.png", fg=MUTED, font=MONO_S,
                                   width=180, height=260)
        self._anim_tick = 0
        self.draw_sprite()

    def draw_sprite(self):
        cv = self.sprite_cv
        cv.delete("all")
        code = self.char_code()
        c = self.gcfg.get("characters", {}).get(code)
        if not c or not (ROOT / "characters" / f"spr_{c.get('sprite', '')}.png").exists():
            cv.create_text(280, 165, text="找不到立繪", fill=MUTED, font=MONO)
            return
        for x in range(0, 560, 16):
            cv.create_line(x, 0, x, 330, fill=GRID)
        for y in range(0, 330, 16):
            cv.create_line(0, y, 560, y, fill=GRID)
        poses = [("open", "closed"), ("open", "open"), ("calm", "closed"), ("smile", "smile")]
        x = 10
        for i, (eyes, mouth) in enumerate(poses if c["sprite"] in sprites.ANIMATED else poses[:1]):
            if i == 1:
                mouth = "open" if self._anim_tick % 2 else "closed"
            try:
                im = sprites.draw(c["sprite"], eyes, mouth)
            except Exception as e:   # broken art file
                cv.create_text(280, 165, text=str(e), fill=BAD, font=MONO_S)
                return
            if c.get("hires"):
                im = im.resize((round(im.width * 300 / im.height), 300), Image.LANCZOS)
            else:
                k = max(1, 300 // im.height)
                im = im.resize((im.width * k, im.height * k), Image.NEAREST)
            cv.create_image(x, 320, anchor="sw", image=self.photo(f"spr{i}", im))
            cv.create_text(x + 4, 6, anchor="nw", text=["正常", "說話", "閉眼", "微笑"][i], fill=MUTED, font=MONO_S)
            x += im.width + 4
            if x > 560:
                break

    def animate_sprite(self):
        self._anim_tick += 1
        if self.nb.index("current") == 3:
            c = self.gcfg.get("characters", {}).get(self.char_code() or "")
            if c and c.get("sprite") in sprites.ANIMATED:
                self.draw_sprite()
        self.root.after(260, self.animate_sprite)

    def load_card_form(self):
        f = self.card_form
        for w in f.winfo_children():
            w.destroy()
        code = self.char_code()
        c = self.gcfg["characters"].get(code, {})
        name = c.get("card", "")
        cards = self.gcfg.setdefault("cards", {})
        ttk.Label(f, text="角色卡產生器（make_card.py）", style="Key.TLabel").pack(anchor="w")
        if name not in cards:
            ttk.Label(f, text=f"card_{name} 沒有產生設定。\n用一張白底立繪，就能做出同風格的角色卡。",
                      style="Muted.TLabel", justify="left").pack(anchor="w", pady=6)
            ttk.Button(f, text="建立產生設定", command=lambda: self.card_new(name, c)).pack(anchor="w")
            return
        spec = cards[name]
        g = ttk.Frame(f)
        g.pack(fill="x", pady=4)
        fields = [("src", "立繪", "str"), ("name", "名字", "str"), ("subtitle", "副標", "str"),
                  ("name_color", "名字色", "color"), ("tint", "頂部底色", "color"), ("border", "邊框", "color"),
                  ("scale", "縮放", "float"), ("top", "頂端 y", "int"), ("fade", "淡出 y", "json")]
        for r, (key, lab, kind) in enumerate(fields):
            ttk.Label(g, text=lab, style="Key.TLabel").grid(row=r, column=0, sticky="w", pady=2)
            v = tk.StringVar(value=fmt(kind, spec.get(key, "")) if key in spec else "")
            if kind == "color":
                w = ColorField(g, v)
            elif key == "src":
                w = ttk.Frame(g)
                ttk.Entry(w, textvariable=v, width=18, font=MONO_S).pack(side="left")
                ttk.Button(w, text="…", width=2, style="Tool.TButton",
                           command=lambda v=v: self.pick_file(v, "立繪", [("圖片", "*.png *.jpg")])).pack(side="left", padx=2)
            else:
                w = ttk.Entry(g, textvariable=v, width=20, font=MONO if kind != "str" else UI)
            w.grid(row=r, column=1, sticky="w", padx=6)

            def setter(val, key=key, kind=kind, w=w):
                try:
                    spec[key] = parse(kind, val)
                except ValueError:
                    return
                self.mark("global")
            v.trace_add("write", lambda *a, v=v, s=setter: s(v.get()))
        ttk.Button(f, text="產生角色卡", style="Accent.TButton",
                   command=lambda: self.run_task("角色卡", ["make_card.py", name], on_done=self.paint_char, switch=False)
                   ).pack(anchor="w", pady=8)

    def card_new(self, name, c):
        if not name:
            messagebox.showinfo("角色卡", "先在「角色卡」欄填一個名稱。", parent=self.root)
            return
        self.gcfg["cards"][name] = dict(src="references/", name=c.get("name", name), subtitle="",
                                        name_color=list(c.get("color", [80, 80, 80])), tint=[244, 238, 230],
                                        border=[230, 226, 234], scale=0.44, top=0, fade=[400, 505])
        self.mark("global")
        self.load_card_form()

    def pick_file(self, var, title, types):
        p = filedialog.askopenfilename(parent=self.root, title=title, filetypes=types + [("全部", "*.*")], initialdir=ROOT)
        if p:
            try:
                var.set(Path(p).resolve().relative_to(ROOT).as_posix())
            except ValueError:
                var.set(Path(p).as_posix())

    def import_art(self, kind):
        p = filedialog.askopenfilename(parent=self.root, title="匯入圖片", filetypes=[("PNG", "*.png")])
        if not p:
            return
        stem = Path(p).stem
        stem = stem[len(kind) + 1:] if stem.startswith(kind + "_") else stem
        name = simpledialog.askstring("匯入", f"存成 characters/{kind}_<名稱>.png，名稱：", initialvalue=stem, parent=self.root)
        if not name:
            return
        shutil.copy2(p, ROOT / "characters" / f"{kind}_{name}.png")
        sprites._load.cache_clear()
        self.refresh_chars()
        self.v_c["sprite" if kind == "spr" else "card"].set(name)

    def char_add(self):
        code = simpledialog.askstring("新角色", "角色代號（劇本講者欄位，例如 K）：", parent=self.root)
        if not code:
            return
        code = code.strip()
        chars = self.gcfg.setdefault("characters", {})
        if not re.fullmatch(r"[A-Za-z0-9_]+", code) or code in chars:
            messagebox.showerror("新角色", "代號只能用英數與底線，且不能重複。", parent=self.root)
            return
        chars[code] = dict(name=code, color=[90, 90, 90], voice=VOICES[0], rate="+15%", pitch="+0Hz",
                           sprite=self.cb_sprite["values"][0] if self.cb_sprite["values"] else "", card="")
        self.mark("global")
        self.refresh_chars(code)
        self.load_scene()

    def char_del(self):
        code = self.char_code()
        if not code:
            return
        used = sum(ln["who"] == code for *_, ln in self.all_lines())
        msg = f"從全域名冊刪除「{code} {self.gcfg['characters'][code]['name']}」？"
        if used:
            msg += f"\n\n這份報告還有 {used} 句是這個角色的台詞，刪除後要改講者才能渲染。"
        if messagebox.askyesno("刪除角色", msg, icon="warning", parent=self.root):
            del self.gcfg["characters"][code]
            self.mark("global")
            self.refresh_chars()
            self.refresh_lines(self.li)
            self.refresh_guests()

    def load_voices(self):
        def work():
            try:
                import edge_tts
                vs = asyncio.run(edge_tts.list_voices())
                names = sorted(v["ShortName"] for v in vs)
                zh = [n for n in names if n.startswith("zh-")]
                self.root.after(0, lambda: (self.cb_voice.configure(values=zh + [n for n in names if n not in zh]),
                                            self.flash_msg(f"已載入 {len(names)} 種聲線")))
            except Exception as e:
                self.root.after(0, lambda: self.flash_msg(f"載入聲線失敗：{e}"))
        self.flash_msg("載入聲線清單中…")
        threading.Thread(target=work, daemon=True).start()

    def audition(self):
        c = self.gcfg["characters"].get(self.char_code())
        if not c:
            return
        text, voice, rate, pitch = self.v_sample.get(), c["voice"], c["rate"], c["pitch"]

        def work():
            try:
                import edge_tts
                tmp = Path(tempfile.gettempdir()) / "studio_audition"
                mp3, wav = tmp.with_suffix(".mp3"), tmp.with_suffix(".wav")
                asyncio.run(edge_tts.Communicate(project.speak_text(text), voice, rate=rate, pitch=pitch).save(str(mp3)))
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), str(wav)], check=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                winsound.PlaySound(str(wav), winsound.SND_FILENAME | winsound.SND_ASYNC)
                self.root.after(0, lambda: self.flash_msg("▶ 播放中"))
            except Exception as e:
                self.root.after(0, lambda: self.flash_msg(f"試聽失敗：{e}"))
        self.flash_msg("產生試聽語音中…")
        threading.Thread(target=work, daemon=True).start()

    # ============================================================ 05 SETTINGS
    def build_settings_tab(self):
        tab = ttk.Frame(self.nb, padding=(0, 10, 0, 0))
        self.nb.add(tab, text=" 05  設定 ")
        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Label(top, text="SCOPE", style="Muted.TLabel").pack(side="left", padx=(0, 8))
        self.v_scope = tk.StringVar(value="global")
        ttk.Radiobutton(top, text="全域  config.toml", value="global", variable=self.v_scope,
                        command=self.load_settings).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(top, text="本報告覆寫  projects/<名稱>/config.toml", value="project", variable=self.v_scope,
                        command=self.load_settings).pack(side="left")
        self.v_scope_hint = tk.StringVar()
        ttk.Label(top, textvariable=self.v_scope_hint, style="Muted.TLabel").pack(side="left", padx=16)

        wrap = ttk.Frame(tab)
        wrap.pack(fill="both", expand=True, pady=(10, 0))
        cv = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=cv.yview)
        self.set_body = ttk.Frame(cv)
        self.set_body.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=self.set_body, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        cv.bind("<Enter>", lambda e: cv.bind_all("<MouseWheel>", lambda ev: cv.yview_scroll(-ev.delta // 120, "units")))
        cv.bind("<Leave>", lambda e: cv.unbind_all("<MouseWheel>"))

    def load_settings(self):
        body = self.set_body
        for w in body.winfo_children():
            w.destroy()
        proj_scope = self.v_scope.get() == "project"
        self.v_scope_hint.set("留空 = 沿用全域值；只寫這份報告想改的項目" if proj_scope else
                              "所有報告共用；報告可以在「本報告覆寫」改個別項目")
        base = config._merge(config.DEFAULTS, self.gcfg)
        target = self.pcfg if proj_scope else self.gcfg
        cols = [ttk.Frame(body), ttk.Frame(body)]
        cols[0].grid(row=0, column=0, sticky="n", padx=(0, 40))
        cols[1].grid(row=0, column=1, sticky="n")
        for n, (title, sec, fields) in enumerate(SETTINGS):
            col = cols[0] if title in ("TIMING", "AUDIO", "VIDEO", "LAYOUT") else cols[1]
            section(col, f"{n + 1:02d}", title, f"[{sec}]").pack(fill="x", pady=(10 if n else 0, 6))
            g = ttk.Frame(col)
            g.pack(fill="x")
            for r, (key, kind, lab) in enumerate(fields):
                gval = base.get(sec, {}).get(key)
                own = target.get(sec, {}).get(key)
                ttk.Label(g, text=lab, width=10).grid(row=r, column=0, sticky="w", pady=2)
                ttk.Label(g, text=key, style="Muted.TLabel", width=15).grid(row=r, column=1, sticky="w")
                v = tk.StringVar(value="" if own is None else fmt(kind, own))
                width = 44 if kind in ("font", "str", "json", "list") else 12
                if kind == "color":
                    w = ColorField(g, v)
                    entry = w.entry
                elif kind == "preset":
                    w = entry = ttk.Combobox(g, textvariable=v, values=([""] if proj_scope else []) + PRESETS, width=12, font=MONO)
                elif kind == "font":
                    w = ttk.Frame(g)
                    entry = ttk.Entry(w, textvariable=v, width=38, font=MONO_S)
                    entry.pack(side="left")
                    ttk.Button(w, text="…", width=2, style="Tool.TButton",
                               command=lambda v=v: self.pick_font(v)).pack(side="left", padx=2)
                else:
                    w = entry = ttk.Entry(g, textvariable=v, width=width, font=MONO if kind != "str" else UI)
                w.grid(row=r, column=2, sticky="w", padx=6)
                hint = config.KEY_NOTES.get(f"{sec}.{key}", "")
                if proj_scope:
                    hint = f"全域：{fmt(kind, gval) if gval is not None else '—'}"
                ttk.Label(g, text=hint, style="Muted.TLabel", wraplength=380).grid(row=r, column=3, sticky="w", padx=6)
                v.trace_add("write", lambda *a, v=v, sec=sec, key=key, kind=kind, e=entry:
                            self.set_setting(target, sec, key, kind, v.get(), e, proj_scope))

    def set_setting(self, target, sec, key, kind, raw, entry, proj_scope):
        if proj_scope and not raw.strip():
            target.get(sec, {}).pop(key, None)
            if sec in target and not target[sec]:
                del target[sec]
            entry.configure(style="TEntry" if not isinstance(entry, ttk.Combobox) else "TCombobox")
            self.mark("project")
            self.after_setting(sec)
            return
        try:
            val = parse(kind, raw)
            if kind == "json" and key == "guest_x" and not (
                    isinstance(val, list) and val and all(isinstance(r, list) and r for r in val)):
                raise ValueError
        except ValueError:
            if isinstance(entry, ttk.Entry) and not isinstance(entry, ttk.Combobox):
                entry.configure(style="Bad.TEntry")
            return
        if isinstance(entry, ttk.Entry) and not isinstance(entry, ttk.Combobox):
            entry.configure(style="TEntry")
        target.setdefault(sec, {})[key] = val
        self.mark("project" if proj_scope else "global")
        self.after_setting(sec)

    def after_setting(self, sec):
        if sec == "layout":
            self.refresh_guests()
        if sec == "timing":
            self.update_status()

    def pick_font(self, var):
        p = filedialog.askopenfilename(parent=self.root, title="選擇字型", initialdir="C:/Windows/Fonts",
                                       filetypes=[("字型", "*.ttf *.ttc *.otf")])
        if p:
            var.set(Path(p).as_posix())

    # ============================================================ 06 OUTPUT
    def build_output_tab(self):
        tab = ttk.Frame(self.nb, padding=(0, 10, 0, 0))
        self.nb.add(tab, text=" 06  輸出 ")
        left = ttk.Frame(tab)
        left.pack(side="left", fill="both", expand=True)
        section(left, "01", "BUILD", "產生語音 → 預覽 → 輸出影片").pack(fill="x", pady=(0, 8))
        bar = ttk.Frame(left)
        bar.pack(fill="x")
        ttk.Button(bar, text="產生語音", command=self.run_tts).pack(side="left")
        ttk.Label(bar, text="  預覽時間點", style="Muted.TLabel").pack(side="left", padx=(16, 4))
        self.v_times = tk.StringVar(value="5 30")
        ttk.Entry(bar, textvariable=self.v_times, width=16, font=MONO).pack(side="left")
        ttk.Button(bar, text="預覽", command=self.run_preview).pack(side="left", padx=6)
        ttk.Button(bar, text="輸出影片", style="Accent.TButton", command=self.run_render).pack(side="left", padx=(10, 0))
        ttk.Button(bar, text="■ 停止", command=self.stop_task).pack(side="left", padx=6)
        ttk.Label(left, text="預覽時間點：秒數，或 #句號（例：5 30 #12）。沒有語音的句子會以靜音估算長度，方便先排版。",
                  style="Muted.TLabel").pack(anchor="w", pady=4)
        bar2 = ttk.Frame(left)
        bar2.pack(fill="x", pady=(4, 0))
        ttk.Button(bar2, text="播放成品", command=lambda: self.open_file("presentation.mp4")).pack(side="left")
        ttk.Button(bar2, text="清理用不到的語音", command=self.clean_audio).pack(side="left", padx=6)
        ttk.Button(bar2, text="刪除預覽圖", command=self.clean_previews).pack(side="left")
        p = ttk.Frame(left)
        p.pack(fill="x", pady=(12, 4))
        self.v_task = tk.StringVar(value="IDLE")
        ttk.Label(p, textvariable=self.v_task, font=MONO_B).pack(side="left")
        self.pb = ttk.Progressbar(p, mode="determinate", maximum=100)
        self.pb.pack(side="left", fill="x", expand=True, padx=10)
        section(left, "02", "LOG", "").pack(fill="x", pady=(8, 6))
        self.log = text_widget(left, 20, MONO)
        self.log.configure(state="disabled", bg="#FBFBF9")
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("err", foreground=BAD)
        self.log.tag_configure("cmd", foreground=ACCENT)

        right = ttk.Frame(tab)
        right.pack(side="left", fill="y", padx=(16, 0))
        section(right, "03", "PREVIEW", "點圖開啟原尺寸").pack(fill="x", pady=(0, 8))
        self.lb_out_prev = tk.Label(right, bg=GRID, width=760, height=428, text="尚無預覽", fg=MUTED, font=MONO_S,
                                    image=self.blank, compound="center", highlightthickness=1, highlightbackground=LINE)
        self.lb_out_prev.pack()
        self.lb_out_prev.bind("<Button-1>", lambda e: self.last_preview and os.startfile(self.last_preview))

    def rel(self):
        return self.proj.relative_to(ROOT).as_posix()

    def open_file(self, name):
        p = self.proj / name
        if p.exists():
            os.startfile(p)
        else:
            self.flash_msg(f"找不到 {name}")

    def log_write(self, s, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", s + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def check_ready(self):
        _, _, err = self.current_guests()
        if err:
            messagebox.showerror("無法執行", err, parent=self.root)
            return False
        return True

    def run_tts(self):
        if self.check_ready():
            self.run_task("語音", ["gen_tts.py", self.rel()], on_done=lambda: (self.refresh_lines(self.li), self.update_status()))

    def run_preview(self):
        times = self.v_times.get().split()
        if times and self.check_ready():
            self.run_task("預覽", ["render.py", self.rel(), "preview", *times])

    def run_render(self):
        if not self.check_ready():
            return
        missing = sum(not self.audio_ok(ln) for *_, ln in self.all_lines())
        if missing:
            if not messagebox.askyesno("缺少語音", f"還有 {missing} 句沒有語音，先產生語音再輸出影片？", parent=self.root):
                return
            self.run_task("語音", ["gen_tts.py", self.rel()], on_done=self.run_render)
            return
        self.run_task("輸出", ["render.py", self.rel()], on_done=lambda: self.log_write(f"完成：{self.proj / 'presentation.mp4'}", "cmd"))

    def run_task(self, label, args, on_done=None, switch=True):
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("工作進行中", "請等目前的工作結束，或按「停止」。", parent=self.root)
            return
        self.save_all()
        if switch:
            self.nb.select(5)
        self.log_write(f"$ python {' '.join(args)}", "cmd")
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-u", *args], cwd=ROOT, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        self.task_label, self.task_done, self.task_total, self.task_count = label, on_done, 0, 0
        self.v_task.set(f"RUN  {label}")
        self.pb.configure(value=0)
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def _reader(self, proc):
        for line in proc.stdout:
            self.q.put(line.rstrip("\n"))
        proc.wait()
        self.q.put(None)

    def poll_task(self):
        try:
            while True:
                line = self.q.get_nowait()
                if line is None:
                    self.task_finished()
                    continue
                self.handle_line(line)
        except queue.Empty:
            pass
        self.root.after(80, self.poll_task)

    def handle_line(self, line):
        bad = bool(re.search(r"Error|Traceback|錯誤|缺少|retry", line))
        self.log_write(line, "err" if bad else None)
        if line.startswith("PREVIEW "):
            self.show_preview(Path(line[8:].strip()))
        elif m := re.match(r"需要產生 (\d+)", line):
            self.task_total = int(m.group(1))
        elif line.startswith("ok ") and self.task_total:
            self.task_count += 1
            self.pb.configure(value=self.task_count / self.task_total * 100)
            self.v_task.set(f"RUN  {self.task_label}  {self.task_count}/{self.task_total}")
        elif m := re.match(r"(\d+)s / (\d+)s", line):
            a, b = int(m.group(1)), int(m.group(2))
            self.pb.configure(value=a / max(1, b) * 100)
            self.v_task.set(f"RUN  {self.task_label}  {a // 60:02d}:{a % 60:02d} / {b // 60:02d}:{b % 60:02d}")

    def task_finished(self):
        code = self.proc.returncode if self.proc else -1
        self.v_task.set(f"DONE  {self.task_label}" if code == 0 else f"FAIL  {self.task_label}  (exit {code})")
        if code == 0:
            self.pb.configure(value=100)
        else:
            self.log_write(f"結束代碼 {code}", "err")
            self.flash_msg(f"{self.task_label}失敗，詳見 06 輸出")
        done, self.task_done = self.task_done, None
        self.proc = None
        if code == 0 and done:
            done()

    def stop_task(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.task_done = None
            self.log_write("已停止", "err")

    def clean_audio(self):
        chars = self.chars()
        keep = {project.audio_key(chars[ln["who"]], ln["text"]) for *_, ln in self.all_lines() if ln["who"] in chars}
        d = self.proj / "audio"
        junk = [p for p in d.glob("*") if p.suffix in (".wav", ".mp3") and p.stem not in keep] if d.exists() else []
        if not junk:
            self.flash_msg("沒有用不到的語音")
            return
        if messagebox.askyesno("清理語音", f"刪除 {len(junk)} 個目前劇本用不到的語音檔？", parent=self.root):
            for p in junk:
                p.unlink()
            self.log_write(f"已刪除 {len(junk)} 個語音檔")

    def clean_previews(self):
        n = 0
        for p in self.proj.glob("preview_*.png"):
            p.unlink(); n += 1
        self.show_preview(None)
        self.flash_msg(f"已刪除 {n} 張預覽圖")


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    Studio(root)
    root.mainloop()


if __name__ == "__main__":
    main()
