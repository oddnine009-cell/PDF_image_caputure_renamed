"""命令行入口：spn scan / apply / rollback。"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from . import __version__
from .apply import apply_plan, rollback
from .config import Config, Region
from .pipeline import scan, summarize
from .plan import review_rows, save_plan
from .report import build_report
from .roster import dedupe_roster, load_roster
from .similarity import has_pinyin

STATUS_TAG = {"ok": "OK  ", "review": "复核", "fail": "失败"}


def _print_progress(i: int, total: int, e) -> None:
    tag = STATUS_TAG.get(e.status, e.status)
    name = "-" if e.status == "fail" else (e.name or "-")[:12]
    print(f"[{i:>4}/{total}] {tag} {name:<12} {Path(e.src).name}", flush=True)


def cmd_scan(args) -> int:
    cfg = Config.load(args.config)
    if args.out:
        cfg.outdir = Path(args.out)
    if args.pattern:
        cfg.pattern = args.pattern
    if args.mode:
        cfg.mode = args.mode
    if args.dpi:
        cfg.dpi = args.dpi
    if args.ocr:
        cfg.ocr = args.ocr
    if args.vision:
        cfg.vision = args.vision
    if args.region:
        nums = [float(x) for x in args.region.replace(" ", "").split(",")]
        if len(nums) != 4:
            print("--region 需要 4 个数字：x0,y0,x1,y1", file=sys.stderr)
            return 2
        cfg.region = Region(x0=nums[0], y0=nums[1], x1=nums[2], y1=nums[3])
    cfg.validate()

    students = dedupe_roster(load_roster(args.roster))
    if not students:
        print(f"名单为空：{args.roster}", file=sys.stderr)
        return 2

    print(f"名单 {len(students)} 人 · 模式 {cfg.mode} · OCR {cfg.ocr} · 输出 {cfg.outdir}")
    if not has_pinyin():
        print("提示：未安装 pypinyin，拼音兜底未启用（pip install pypinyin 可提升近音容错）")
    if cfg.vision != "off":
        from .vision import api_key

        if api_key(cfg.vision_key):
            print(f"视觉复核：{cfg.vision}（{cfg.vision_model}）")
        else:
            print("视觉复核已开启，但没有 DEEPSEEK_API_KEY，将自动跳过")

    entries = scan(args.inputs, students, cfg, limit=args.limit, on_progress=_print_progress)
    if not entries:
        print("没有找到 PDF", file=sys.stderr)
        return 1

    out = cfg.outdir
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "pattern": cfg.pattern,
        "mode": cfg.mode,
        "outdir": str(out),
        "roster": str(Path(args.roster)),
        "roster_count": len(students),
        "ocr": cfg.ocr,
        "dpi": cfg.dpi,
    }
    plan_file = save_plan(entries, out / "plan.json", meta)
    report_file = build_report(entries, out / "report.html", meta)
    with (out / "review.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(review_rows(entries))

    s = summarize(entries)
    print()
    print(f"完成：共 {s['total']} 份 · 直接可用 {s['ok']} · 待复核 {s['review']} · 失败 {s['fail']}")
    print(f"计划   {plan_file}")
    print(f"复核表 {report_file}")
    print(f"CSV    {out / 'review.csv'}")
    print()
    print("下一步：打开复核表确认 → spn apply", plan_file, "--include-review --yes")
    return 0 if s["ok"] or s["review"] else 1


def cmd_apply(args) -> int:
    stats = apply_plan(
        args.plan,
        include_review=args.include_review,
        perform=args.yes,
        corrections=args.corrections,
    )
    for a in stats["actions"]:
        if a.get("status") == "failed":
            print(f"失败  {a['src']}  {a.get('reason','')}", file=sys.stderr)
        else:
            src = Path(a["src"]).name
            dst = Path(a["dst"]).name
            print(f"{a['action']:<6} {src}  ->  {dst}")
    mode = "已执行" if args.yes else "预览（加 --yes 才真正执行）"
    verb = "成功" if args.yes else "将执行"
    print(f"\n{mode}：{verb} {stats['done']} · 跳过 {stats['skipped']} · 失败 {stats['failed']}")
    if args.yes and stats["done"]:
        print(f"回滚记录：{Path(args.plan).parent / 'manifest.jsonl'}")
    return 0 if stats["failed"] == 0 else 1


def cmd_rollback(args) -> int:
    stats = rollback(args.manifest, perform=args.yes)
    for a in stats["actions"]:
        print(a)
    print(f"{'已回滚' if args.yes else '预览（加 --yes 才真正执行）'}："
          f"{stats['reverted']} · 跳过 {stats['skipped']} · 失败 {stats['failed']}")
    return 0 if stats["failed"] == 0 else 1


def cmd_serve(args) -> int:
    from .web import serve

    serve(host=args.host, port=args.port, open_browser=not args.no_open, demo=args.demo)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="spn",
        description="按手写姓名自动命名学生作业 PDF（三态判定 + 人工复核 + 可回滚）",
    )
    p.add_argument("--version", action="version", version=f"spn {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="批量识别，生成命名计划与复核表")
    s.add_argument("inputs", nargs="+", help="PDF 文件或目录")
    s.add_argument("--roster", required=True, help="花名册 CSV/TXT")
    s.add_argument("--out", help="输出目录（默认 out）")
    s.add_argument("--pattern", help="命名模板，如 '{name}' 或 '{name}_{stem}'")
    s.add_argument("--mode", choices=["copy", "rename"], help="copy 复制到 out / rename 原地改名")
    s.add_argument("--dpi", type=int, help="渲染 DPI，默认 300")
    s.add_argument("--region", help="姓名区域 x0,y0,x1,y1（0~1，从左上角算）")
    s.add_argument("--ocr", choices=["auto", "textlayer", "json", "winocr", "baidu", "paddle"])
    s.add_argument("--vision", choices=["off", "auto", "always"],
                   help="疑难件交给 DeepSeek 视觉模型再读一遍（需 DEEPSEEK_API_KEY）")
    s.add_argument("--limit", type=int, help="只处理前 N 个（调试用）")
    s.add_argument("--config", help="TOML 配置文件")
    s.set_defaults(func=cmd_scan)

    a = sub.add_parser("apply", help="执行命名计划")
    a.add_argument("plan", help="scan 生成的 plan.json")
    a.add_argument("--include-review", action="store_true", help="把 review 状态的也按最佳猜测执行")
    a.add_argument("--corrections", help="复核后导出的 corrections.csv（src,name）")
    a.add_argument("--yes", action="store_true", help="真正执行；缺省只预览")
    a.set_defaults(func=cmd_apply)

    r = sub.add_parser("rollback", help="按 manifest 逆向还原")
    r.add_argument("manifest", help="manifest.jsonl")
    r.add_argument("--yes", action="store_true", help="真正执行；缺省只预览")
    r.set_defaults(func=cmd_rollback)

    srv = sub.add_parser("serve", help="启动本地网页应用（上传 → 识别 → 复核 → 下载）")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8765)
    srv.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    srv.add_argument("--demo", action="store_true", help="开放仓库自带样例（页面会出现「载入示例」）")
    srv.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"错误：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
