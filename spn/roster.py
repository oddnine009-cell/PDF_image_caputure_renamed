"""花名册读取。支持 CSV（表头含「姓名」列）与纯文本（每行一个姓名）。"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from .text import normalize

NAME_HEADERS = ("姓名", "名字", "学生姓名", "name", "student")


@dataclass(frozen=True)
class Student:
    name: str            # 归一化后的姓名
    raw_name: str        # 原始写法（用于命名）
    sid: str = ""
    klass: str = ""


def _read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def load_roster(path: Path | str) -> list[Student]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"找不到名单文件：{p}")
    text = _read_text(p)
    if p.suffix.lower() == ".csv":
        return _parse_csv(text)
    return _parse_lines(text)


def _parse_csv(text: str) -> list[Student]:
    rows = list(csv.reader(io.StringIO(text)))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return []
    header = [c.strip() for c in rows[0]]
    name_idx = next((i for i, h in enumerate(header) if any(k in h for k in NAME_HEADERS)), None)
    data = rows[1:] if name_idx is not None else rows
    if name_idx is None:
        name_idx = 0
    sid_idx = next((i for i, h in enumerate(header) if "学号" in h or h.lower() == "id"), None)
    cls_idx = next((i for i, h in enumerate(header) if "班" in h), None)

    out: list[Student] = []
    for row in data:
        if len(row) <= name_idx:
            continue
        raw = row[name_idx].strip()
        norm = normalize(raw)
        if not norm:
            continue
        out.append(Student(
            name=norm,
            raw_name=raw,
            sid=row[sid_idx].strip() if sid_idx is not None and len(row) > sid_idx else "",
            klass=row[cls_idx].strip() if cls_idx is not None and len(row) > cls_idx else "",
        ))
    return out


def _parse_lines(text: str) -> list[Student]:
    out: list[Student] = []
    for line in text.splitlines():
        raw = line.strip().lstrip("\ufeff")
        if not raw or raw.startswith("#"):
            continue
        norm = normalize(raw)
        if norm:
            out.append(Student(name=norm, raw_name=raw))
    return out


def dedupe_roster(students: list[Student]) -> list[Student]:
    seen: set[str] = set()
    out: list[Student] = []
    for s in students:
        if s.name in seen:
            continue
        seen.add(s.name)
        out.append(s)
    return out
