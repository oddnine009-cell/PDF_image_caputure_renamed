"""字/拼音相似度。核心零依赖；装了 pypinyin 会自动启用拼音通道。"""

from __future__ import annotations

from functools import lru_cache

# 手写/扫描 PDF 里最常见的形近混淆组（同一组内两两视为"像"，替换代价 0.45）。
# 这是名单约束匹配的补充手段，可按自己学生姓名的用字继续扩充。
CONFUSABLE_GROUPS = [
    "己已巳", "未末", "土士", "千干", "日曰", "人入", "大太", "力刀", "九丸",
    "木本术", "王玉", "田由甲", "白自", "目日", "贝见", "戌戍", "拨拔", "侯候",
    "微徽", "晴睛", "健建", "佳住", "天夫", "子孑", "王汪", "晓晓",
]

CONFUSABLE: dict[tuple[str, str], float] = {}
for _g in CONFUSABLE_GROUPS:
    for _i, _a in enumerate(_g):
        for _b in _g[_i + 1:]:
            CONFUSABLE[(_a, _b)] = 0.45
            CONFUSABLE[(_b, _a)] = 0.45

SUB_COST_CONFUSABLE = 0.45
SUB_COST_DEFAULT = 1.0

try:  # 可选加速器
    from rapidfuzz.distance import Levenshtein as _RFLevenshtein  # type: ignore
except Exception:  # pragma: no cover
    _RFLevenshtein = None

try:
    from pypinyin import lazy_pinyin  # type: ignore
except Exception:  # pragma: no cover
    lazy_pinyin = None


def sub_cost(a: str, b: str) -> float:
    if a == b:
        return 0.0
    return CONFUSABLE.get((a, b), SUB_COST_DEFAULT)


def levenshtein(a: str, b: str, cost=None) -> float:
    """编辑距离。cost(ch_a, ch_b) 可自定义替换代价；不传则 0/1 标准距离。"""
    if a == b:
        return 0.0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return float(la or lb)

    if cost is None and _RFLevenshtein is not None:
        return float(_RFLevenshtein.distance(a, b))

    prev = [float(j) for j in range(lb + 1)]
    for i in range(1, la + 1):
        ai = a[i - 1]
        cur = [float(i)] + [0.0] * lb
        for j in range(1, lb + 1):
            c = cost(ai, b[j - 1]) if cost else (0.0 if ai == b[j - 1] else 1.0)
            cur[j] = min(prev[j] + 1.0, cur[j - 1] + 1.0, prev[j - 1] + c)
        prev = cur
    return prev[lb]


def char_similarity(a: str, b: str) -> float:
    """0~1，形近字替换算部分正确。"""
    if not a or not b:
        return 0.0
    d = levenshtein(a, b, sub_cost)
    return max(0.0, 1.0 - d / max(len(a), len(b)))


@lru_cache(maxsize=8192)
def _pinyin_of(text: str) -> str | None:
    if lazy_pinyin is None:
        return None
    try:
        return "".join(lazy_pinyin(text))
    except Exception:  # pragma: no cover
        return None


def pinyin_similarity(a: str, b: str) -> float | None:
    """同音/近音相似度；未安装 pypinyin 返回 None（调用方应退化为纯字形）。"""
    pa, pb = _pinyin_of(a), _pinyin_of(b)
    if pa is None or pb is None:
        return None
    if not pa or not pb:
        return 0.0
    return max(0.0, 1.0 - levenshtein(pa, pb) / max(len(pa), len(pb)))


def name_similarity(a: str, b: str) -> float:
    """综合相似度：字形 0.65 + 拼音 0.35；无拼音库时纯字形。"""
    cs = char_similarity(a, b)
    if cs <= 0.0:
        return 0.0
    ps = pinyin_similarity(a, b)
    if ps is None:
        return cs
    return 0.65 * cs + 0.35 * ps


def has_pinyin() -> bool:
    return lazy_pinyin is not None
