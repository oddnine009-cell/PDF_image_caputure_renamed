"""文本归一化与候选窗生成。

关键点：不做整页语义理解，而是把 OCR 行切成 2~4 字滑动窗，
让「姓名：张三」「学生 张三 高一(3)班」这类混杂行也能长出干净的候选。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_KEEP = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")
_CONTEXT = re.compile(r"(姓名|名字|学生|签名|签字|班级|学号|年级|同学|姓名[:：]?)")


def normalize(text: str) -> str:
    """NFKC + 只保留汉字/字母/数字。去空格标点是为了让竖排、空格分隔都不影响窗口切分。"""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    return "".join(_KEEP.findall(t))


@dataclass(frozen=True)
class Candidate:
    text: str
    line: str
    bonus: float = 0.0

    def __repr__(self) -> str:  # 调试友好
        return f"Candidate({self.text!r}, line={self.line!r})"


def context_bonus(line: str, base: float) -> float:
    return base if _CONTEXT.search(line or "") else 0.0


def build_candidates(
    lines: list[str],
    min_len: int = 2,
    max_len: int = 4,
    ctx_bonus: float = 0.05,
) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[str] = set()
    for raw in lines:
        norm = normalize(raw)
        if len(norm) < min_len:
            continue
        bonus = context_bonus(raw, ctx_bonus)
        for L in range(min_len, max_len + 1):
            if len(norm) < L:
                break
            for i in range(len(norm) - L + 1):
                sub = norm[i:i + L]
                key = f"{sub}|{bonus}"
                if key in seen:
                    continue
                seen.add(key)
                out.append(Candidate(sub, raw, bonus))
    return out
