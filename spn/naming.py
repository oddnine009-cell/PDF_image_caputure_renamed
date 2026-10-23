"""文件命名：模板、非法字符清洗、重名冲突处理。"""

from __future__ import annotations

import re
from pathlib import Path

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize(part: str, max_len: int = 100) -> str:
    s = _INVALID.sub("", part or "").strip()
    s = s.strip(". ")                      # Windows 不允许结尾的点和空格
    s = re.sub(r"\s+", " ", s)
    if len(s) > max_len:
        s = s[:max_len].rstrip(". ")
    if s.upper() in _RESERVED:
        s = f"_{s}"
    return s or "未命名"


def render(entry_name: str, pattern: str, stem: str, **extra: str) -> str:
    """pattern 支持 {name} {stem}，其余键透传。渲染失败时退回 {name}。"""
    values = {"name": entry_name, "stem": stem, **extra}
    try:
        out = pattern.format_map(values)
    except (KeyError, IndexError, ValueError):
        out = entry_name
    return sanitize(out)


def unique_path(path: Path, taken: set[str] | None = None) -> Path:
    """已存在或已被本次计划占用时，追加 (2)(3)…"""
    if taken is None:
        taken = set()
    key = str(path).lower()
    if not path.exists() and key not in taken:
        taken.add(key)
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    base = stem
    n = 2
    while True:
        cand = parent / f"{base} ({n}){suffix}"
        ck = str(cand).lower()
        if not cand.exists() and ck not in taken:
            taken.add(ck)
            return cand
        n += 1


def build_target(
    src: Path,
    name: str,
    pattern: str,
    mode: str,
    outdir: Path | None,
    taken: set[str] | None = None,
) -> Path:
    stem = render(name, pattern, src.stem)
    if mode == "copy":
        base_dir = outdir or Path("out")
        base_dir.mkdir(parents=True, exist_ok=True)
        target = base_dir / f"{stem}.pdf"
    else:
        target = src.with_name(f"{stem}.pdf")
    if target == src:
        return src
    return unique_path(target, taken)
