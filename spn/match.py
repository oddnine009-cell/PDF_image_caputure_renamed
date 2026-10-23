"""名单约束匹配：把「可能是姓名的字串」收敛到「花名册里的某个人」。

这是整个工具准确率的关键。开放集 OCR 认名字错误率高；闭集匹配下，
即使 OCR 只认出 70%，只要还像，就能被吸附到正确的那一个，
并且能给出可解释的置信度 + 备选，供人工复核。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .roster import Student
from .similarity import char_similarity, pinyin_similarity
from .text import build_candidates


@dataclass
class MatchCandidate:
    name: str
    raw_name: str
    score: float
    matched: str
    source_line: str
    char_sim: float
    pinyin_sim: float | None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "score": round(self.score, 4),
            "matched": self.matched,
            "line": self.source_line,
            "char": round(self.char_sim, 4),
            "pinyin": None if self.pinyin_sim is None else round(self.pinyin_sim, 4),
        }


@dataclass
class MatchResult:
    status: str                      # ok | review | fail
    best: MatchCandidate | None
    candidates: list[MatchCandidate]
    margin: float
    reason: str

    @property
    def name(self) -> str:
        return self.best.name if self.best else ""


def match_names(
    lines: list[str],
    students: list[Student],
    cfg: Config,
) -> MatchResult:
    windows = build_candidates(
        lines, cfg.name_min_len, cfg.name_max_len, cfg.context_bonus
    )
    if not windows:
        return MatchResult("fail", None, [], 0.0, "没有可用文本")
    if not students:
        return MatchResult("fail", None, [], 0.0, "名单为空")

    best_by_name: dict[str, MatchCandidate] = {}
    for st in students:
        L = len(st.name)
        if L < cfg.name_min_len or L > cfg.name_max_len:
            continue
        local: MatchCandidate | None = None
        for c in windows:
            if len(c.text) != L:
                continue
            cs = char_similarity(c.text, st.name)
            if cs < 0.30:          # 快速剪枝，避免昂贵的拼音比较
                continue
            ps = pinyin_similarity(c.text, st.name)
            score = cs if ps is None else 0.65 * cs + 0.35 * ps
            score = min(1.0, score + c.bonus)   # 出现在「姓名：」等上下文里加成
            if local is None or score > local.score:
                local = MatchCandidate(
                    name=st.name, raw_name=st.raw_name, score=score,
                    matched=c.text, source_line=c.line, char_sim=cs, pinyin_sim=ps,
                )
        if local:
            best_by_name[st.name] = local

    if not best_by_name:
        return MatchResult("fail", None, [], 0.0, "没有达到最低相似度的候选")

    ranked = sorted(best_by_name.values(), key=lambda x: x.score, reverse=True)
    top = ranked[: max(1, cfg.top_k)]
    best = ranked[0]
    second = ranked[1].score if len(ranked) > 1 else 0.0
    margin = best.score - second

    if best.score < cfg.review_threshold:
        return MatchResult(
            "fail", best, top, margin,
            f"最高相似度 {best.score:.2f} 低于复核阈值 {cfg.review_threshold:.2f}",
        )
    if best.score >= cfg.ok_threshold and margin >= cfg.min_margin:
        tail = f"领先次选 {margin:.2f}" if len(ranked) > 1 else "无其他候选"
        return MatchResult(
            "ok", best, top, margin,
            f"匹配 {best.name}（{best.score:.2f}），{tail}",
        )
    why = []
    if best.score < cfg.ok_threshold:
        why.append(f"置信度 {best.score:.2f} < {cfg.ok_threshold:.2f}")
    if margin < cfg.min_margin:
        why.append(f"与次选 {ranked[1].name} 仅差 {margin:.2f}")
    return MatchResult("review", best, top, margin, "；".join(why))


def match_text(text: str, students: list[Student], cfg: Config) -> MatchResult:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return match_names(lines, students, cfg)
