"""命名计划：scan 阶段的产物，apply 阶段消费。JSON 便于人工审阅和版本管理。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

PLAN_VERSION = 1


@dataclass
class PlanEntry:
    src: str
    name: str = ""
    raw_name: str = ""
    status: str = "fail"          # ok | review | fail
    score: float = 0.0
    margin: float = 0.0
    matched: str = ""
    reason: str = ""
    dst: str = ""
    candidates: list[dict] = field(default_factory=list)
    error: str = ""
    crop: str = ""                # base64 图片，仅报告用
    crop_mime: str = "image/png"
    vision_text: str = ""         # 视觉模型读出来的原文（没有则为空）

    def as_dict(self, with_crop: bool = True) -> dict:
        d = asdict(self)
        if not with_crop:
            d.pop("crop", None)
        d["score"] = round(self.score, 4)
        d["margin"] = round(self.margin, 4)
        return d


def save_plan(entries: list[PlanEntry], path: Path, meta: dict, with_crop: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": PLAN_VERSION,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "meta": meta,
        "entries": [e.as_dict(with_crop=with_crop) for e in entries],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_plan(path: Path | str) -> tuple[list[PlanEntry], dict]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):                      # 兼容裸数组
        return [PlanEntry(**e) for e in data], {}
    entries = []
    for e in data.get("entries", []):
        known = {f for f in PlanEntry.__dataclass_fields__}
        entries.append(PlanEntry(**{k: v for k, v in e.items() if k in known}))
    return entries, data.get("meta", {})


def review_rows(entries: list[PlanEntry]) -> list[list[str]]:
    rows = [["src", "name", "status", "score", "candidates"]]
    for e in entries:
        cands = " / ".join(f"{c['name']}({c['score']:.2f})" for c in e.candidates)
        rows.append([e.src, e.name, e.status, f"{e.score:.3f}", cands])
    return rows
