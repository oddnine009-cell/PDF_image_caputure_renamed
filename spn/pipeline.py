"""主流水线：一个 PDF -> 文本 -> 匹配 -> 命名计划。"""

from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path

from .config import Config
from .match import match_names
from .naming import build_target
from .plan import PlanEntry
from .roster import Student
from .sources import (
    BackendError,
    has_pymupdf,
    ocr_image,
    ocr_json,
    page_text,
    render_page,
)


def collect_files(inputs: list[str | Path], recursive: bool = True) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for raw in inputs:
        p = Path(raw).expanduser()
        if p.is_dir():
            it = p.rglob("*.pdf") if recursive else p.glob("*.pdf")
            for f in sorted(it):
                if f.is_file() and str(f.resolve()).lower() not in seen:
                    seen.add(str(f.resolve()).lower())
                    out.append(f.resolve())
        elif p.is_file():
            if str(p.resolve()).lower() not in seen:
                seen.add(str(p.resolve()).lower())
                out.append(p.resolve())
        else:
            raise FileNotFoundError(f"输入不存在：{p}")
    return out


def _sidecar_exists(path: Path) -> bool:
    return path.with_suffix(".ocr.json").exists()


def _winocr_lines(path: Path, cfg: Config, want_preview: bool) -> tuple[list[str], bytes | None]:
    """多档宽度各识别一遍再合并。

    Windows OCR 对同一页在不同渲染宽度下会给出不同结果（张三/茅四这种），
    单档命中率在 50%~90% 之间抖；跑两档取并集，匹配阶段取最好的那个窗口，
    稳定得多，代价只是多一次 0.5 秒的识别。
    """
    from .winocr import recognize_pdf

    widths = tuple(getattr(cfg, "ocr_widths", (1200, 1400))) or (1200,)
    region = cfg.region.as_tuple() if cfg.region else None
    lines: list[str] = []
    preview: bytes | None = None
    for width in widths:
        part, prev = recognize_pdf(
            path, 0, width=int(width), region=region,
            preview=want_preview and preview is None,
        )
        lines += part
        if preview is None:
            preview = prev
    return lines, preview


def collect_lines(path: Path, cfg: Config) -> tuple[list[str], str, bytes | None]:
    """返回 (文本行, 来源说明, 预览图)。auto 按「最便宜且够用」的顺序尝试。"""
    lines: list[str] = []
    used: list[str] = []
    preview: bytes | None = None

    if cfg.ocr == "json":
        r = ocr_json(path)
        return [ln for ln in r.lines if ln.strip()], "json", None

    # 1) 文字层最便宜：印刷体表单（有些导出工具会把姓名以文本写入）
    if cfg.use_text_layer and has_pymupdf():
        try:
            t = page_text(path, 0)
        except Exception:
            t = ""
        if t.strip():
            lines += [ln for ln in t.splitlines() if ln.strip()]
            used.append("textlayer")

    # 2) 需要图像识别
    if cfg.ocr in ("baidu", "paddle"):
        png = render_page(path, 0, cfg.dpi, cfg.region)
        r = ocr_image(png, cfg.ocr)
        lines += [ln for ln in r.lines if ln.strip()]
        used.append(r.backend)
    elif cfg.ocr == "winocr":
        part, preview = _winocr_lines(path, cfg, cfg.keep_crop)
        lines += part
        used.append("winocr")
    elif cfg.ocr == "auto" and not lines:
        if _sidecar_exists(path):
            r = ocr_json(path)
            lines += [ln for ln in r.lines if ln.strip()]
            used.append("json")
        else:
            from .winocr import available as winocr_available

            if not winocr_available():
                raise BackendError(
                    "auto 找不到可用文字来源：装 PyMuPDF 读文字层 / 提供同名 .ocr.json / "
                    "用 --ocr winocr（Windows 自带）、baidu 或 paddle 指定识别后端"
                )
            part, preview = _winocr_lines(path, cfg, cfg.keep_crop)
            lines += part
            used.append("winocr")

    return lines, "+".join(dict.fromkeys(used)) or "none", preview


_STATUS_RANK = {"ok": 2, "review": 1, "fail": 0}


def _should_vision(cfg: Config, result) -> bool:
    if cfg.vision == "always":
        return True
    if cfg.vision == "auto":
        return result.status != "ok"
    return False


def _vision_image(path: Path, cfg: Config, preview: bytes | None) -> bytes | None:
    """优先重新渲染一张高分辨率的姓名区图；没有 region 就退回缩略图。"""
    if cfg.region:
        try:
            from .winocr import region_image

            img = region_image(path, cfg.region.as_tuple())
            if img:
                return img
        except Exception:
            pass
    return preview


def _maybe_vision(path, cfg, mcfg, lines, students, result, preview):
    """让视觉模型再读一遍——但结论仍由花名册匹配决定。

    返回 (结果, 附加说明, 模型读到的原文)。
    """
    if not _should_vision(cfg, result):
        return result, "", ""

    from . import vision

    if not vision.api_key(cfg.vision_key):
        return result, "；视觉复核已开启但未配置 DEEPSEEK_API_KEY", ""

    img = _vision_image(path, cfg, preview)
    if not img:
        return result, "", ""

    try:
        guess = vision.read_name(
            img,
            key=cfg.vision_key,
            model=cfg.vision_model,
            base_url=cfg.vision_base_url,
            detail=cfg.vision_detail,
            timeout=cfg.vision_timeout,
        )
    except vision.VisionError as exc:
        return result, f"；视觉模型不可用（{exc}）", ""

    if not guess:
        return result, "；视觉模型也没看清", ""

    alt = match_names(lines + [guess], students, mcfg)
    old_key = (_STATUS_RANK.get(result.status, 0),
               result.best.score if result.best else 0.0)
    new_key = (_STATUS_RANK.get(alt.status, 0), alt.best.score if alt.best else 0.0)
    if new_key > old_key:
        return alt, f"；视觉模型读作「{guess}」，采纳", guess
    return result, f"；视觉模型读作「{guess}」，未改变结论", guess


def _crop_thumb(preview: bytes | None, path: Path, cfg: Config) -> tuple[str, str]:
    """返回 (base64, mime)。优先用识别时顺手渲染的预览图。"""
    if preview:
        return base64.b64encode(preview).decode("ascii"), "image/jpeg"
    if not has_pymupdf():
        return "", "image/png"
    try:
        png = render_page(path, 0, 110, cfg.region)
        return base64.b64encode(png).decode("ascii"), "image/png"
    except Exception:
        return "", "image/png"


def process_file(
    path: Path,
    students: list[Student],
    cfg: Config,
    taken: set[str],
) -> PlanEntry:
    entry = PlanEntry(src=str(path))
    try:
        lines, source, preview = collect_lines(path, cfg)
        entry.reason = f"来源:{source}"
    except Exception as exc:
        entry.status = "fail"
        entry.error = f"{type(exc).__name__}: {exc}"
        entry.reason = "读取失败"
        return entry

    if cfg.keep_crop:
        entry.crop, entry.crop_mime = _crop_thumb(preview, path, cfg)

    if not lines:
        entry.status = "fail"
        entry.error = "OCR/文字层没有返回任何文字"
        return entry

    # 框了区域时，页面里只剩姓名这一小块，噪声很低：一个字没认对也该给人工看一眼，
    # 所以用更宽松的复核阈值；整页识别时不能这么放，否则正文里的字会刷出一堆假候选。
    if cfg.region:
        mcfg = replace(cfg, review_threshold=cfg.review_threshold_roi)
    else:
        mcfg = cfg

    result = match_names(lines, students, mcfg)
    result, vision_note, vision_text = _maybe_vision(
        path, cfg, mcfg, lines, students, result, preview
    )
    entry.vision_text = vision_text
    entry.status = result.status
    entry.margin = result.margin
    entry.reason = f"{entry.reason}；{result.reason}{vision_note}"
    entry.candidates = [c.as_dict() for c in result.candidates]
    if result.best:
        entry.name = result.best.name
        entry.raw_name = result.best.raw_name
        entry.score = result.best.score
        entry.matched = result.best.matched
        # 只有 ok / review 才占文件名；fail 的"最佳猜测"不参与命名，
        # 否则会把没认出来的文件也套上错误姓名、还挤占重名序号。
        if result.status in ("ok", "review"):
            entry.dst = str(build_target(
                path, entry.raw_name, cfg.pattern, cfg.mode, cfg.outdir, taken
            ))
    return entry


def scan(
    inputs: list[str | Path],
    students: list[Student],
    cfg: Config,
    limit: int | None = None,
    on_progress=None,
) -> list[PlanEntry]:
    files = collect_files(inputs)
    if limit:
        files = files[:limit]
    taken: set[str] = set()
    entries: list[PlanEntry] = []
    for i, f in enumerate(files, 1):
        e = process_file(f, students, cfg, taken)
        entries.append(e)
        if on_progress:
            on_progress(i, len(files), e)
    return entries


def summarize(entries: list[PlanEntry]) -> dict:
    counts = {"ok": 0, "review": 0, "fail": 0}
    for e in entries:
        counts[e.status] = counts.get(e.status, 0) + 1
    return {"total": len(entries), **counts}
