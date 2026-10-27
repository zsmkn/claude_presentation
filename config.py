"""Settings: config.toml (global) merged with projects/<name>/config.toml (this report)."""
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(proj):
    with open(ROOT / "config.toml", "rb") as f:
        cfg = tomllib.load(f)
    local = Path(proj) / "config.toml"
    if local.exists():
        with open(local, "rb") as f:
            cfg = _merge(cfg, tomllib.load(f))
    for c in cfg["characters"].values():
        c["color"] = tuple(c["color"])
    return cfg


def cast(cfg, scenes):
    """-> (host, guests). Guests default to everyone else who has lines or is listed in a scene's guests."""
    chars, show = cfg["characters"], cfg["show"]
    host = show.get("host", "C")
    used = {ln[0] for sc in scenes for ln in sc["lines"]} | {g for sc in scenes for g in sc.get("guests", "")}
    guests = list(show.get("guests") or [c for c in chars if c in used and c != host])
    unknown = [c for c in [host, *guests, *used] if c not in chars]
    if unknown:
        sys.exit(f"設定錯誤：角色代號 {sorted(set(unknown))} 不在 config.toml 的 [characters] 裡")
    if host in guests:
        sys.exit(f"設定錯誤：{host} 不能同時是主持人和配角")
    offstage = sorted(used - {host} - set(guests))
    if offstage:
        sys.exit(f"設定錯誤：劇本裡有 {offstage} 的台詞（或寫在場景 guests），但不在本次的 host / guests 名單")
    return host, guests
