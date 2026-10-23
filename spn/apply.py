"""执行命名计划，并记录可回滚的 manifest。

安全约定：
* 默认不执行（perform=False，只打印计划）；
* copy 模式不动原文件，rename 模式才是原地改名；
* 每步写 manifest.jsonl，rollback 可逆向还原。
"""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path

from .naming import build_target, unique_path
from .plan import PlanEntry, load_plan


def manifest_path(plan_file: Path) -> Path:
    return plan_file.parent / "manifest.jsonl"


def load_corrections(path: Path | str) -> dict[str, str]:
    p = Path(path)
    out: dict[str, str] = {}
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            src = (row.get("src") or "").strip()
            name = (row.get("name") or "").strip()
            if src and name:
                out[src] = name
    return out


def apply_plan(
    plan_file: Path | str,
    include_review: bool = False,
    perform: bool = False,
    corrections: Path | str | None = None,
) -> dict:
    plan_file = Path(plan_file)
    entries, meta = load_plan(plan_file)
    fixes = load_corrections(corrections) if corrections else {}

    pattern = meta.get("pattern") or "{name}"
    mode = meta.get("mode") or "copy"
    outdir = Path(meta.get("outdir") or plan_file.parent)

    stats = {"total": len(entries), "done": 0, "skipped": 0, "failed": 0, "actions": []}
    taken: set[str] = set()

    mf = manifest_path(plan_file)
    fh = mf.open("a", encoding="utf-8") if perform else None
    try:
        for e in entries:
            src = Path(e.src)
            name = fixes.get(e.src, e.name)

            if not name:
                stats["skipped"] += 1
                continue
            # fail 说明「没认出来」，绝不自动套用它的第一猜测；只有在 corrections 里
            # 由人工明确给出姓名时才执行。
            if e.src not in fixes:
                if e.status == "fail":
                    stats["skipped"] += 1
                    continue
                if e.status == "review" and not include_review:
                    stats["skipped"] += 1
                    continue
            if not src.exists():
                stats["failed"] += 1
                stats["actions"].append({"src": str(src), "status": "failed", "reason": "源文件不存在"})
                continue

            if e.src in fixes or not e.dst:
                dst = build_target(src, name, pattern, mode, outdir, taken)
            else:
                dst = Path(e.dst)
                if dst.exists():
                    dst = unique_path(dst, taken)

            if dst == src:
                stats["skipped"] += 1
                continue
            taken.add(str(dst).lower())   # 后续条目的重名判断要算上这一条

            action = {"src": str(src), "dst": str(dst), "action": mode}
            if perform:
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if mode == "copy":
                        shutil.copy2(src, dst)
                    else:
                        src.replace(dst)
                except Exception as exc:
                    stats["failed"] += 1
                    action["status"] = "failed"
                    action["reason"] = f"{type(exc).__name__}: {exc}"
                    stats["actions"].append(action)
                    continue
                record = {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "action": mode,
                    "src": str(src),
                    "dst": str(dst),
                }
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()
            stats["done"] += 1
            action["status"] = "done"
            stats["actions"].append(action)
    finally:
        if fh:
            fh.close()
    return stats


def rollback(manifest_file: Path | str, perform: bool = False) -> dict:
    p = Path(manifest_file)
    if not p.exists():
        raise FileNotFoundError(f"找不到 manifest：{p}")
    records = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    stats = {"total": len(records), "reverted": 0, "skipped": 0, "failed": 0, "actions": []}
    for rec in reversed(records):
        src, dst, action = Path(rec["src"]), Path(rec["dst"]), rec["action"]
        try:
            if action == "rename":
                if dst.exists() and not src.exists():
                    if perform:
                        src.parent.mkdir(parents=True, exist_ok=True)
                        dst.replace(src)
                    stats["reverted"] += 1
                    stats["actions"].append({"from": str(dst), "to": str(src)})
                else:
                    stats["skipped"] += 1
            else:  # copy
                if dst.exists():
                    if perform:
                        dst.unlink()
                    stats["reverted"] += 1
                    stats["actions"].append({"removed": str(dst)})
                else:
                    stats["skipped"] += 1
        except Exception as exc:
            stats["failed"] += 1
            stats["actions"].append({"dst": str(dst), "error": str(exc)})
    return stats
