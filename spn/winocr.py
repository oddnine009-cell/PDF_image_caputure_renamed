"""Windows 自带能力：PDF 渲染 + 中文 OCR，完全离线、零第三方依赖。

用的是系统组件：
* ``Windows.Data.Pdf``   —— 把 PDF 页渲染成位图
* ``Windows.Media.Ocr``  —— 中文识别（需系统装有 zh-Hans 语言包）

实测：工整的楷体/打印体识别很稳，连笔手写明显弱于云端专门接口。
所以它适合"能装环境受限、但字迹还比较规矩"的场景；对策是尽量只裁姓名区域，
再靠花名册做闭集匹配把噪声收敛掉。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

from .text import normalize

ROOT = Path(__file__).resolve().parent.parent
# 脚本跟着包走，pip 安装后也能找到（pyproject 里声明了 package-data）
SCRIPT = Path(__file__).resolve().with_name("win_pdf_ocr.ps1")
POWERSHELL = "powershell.exe"
_TIMEOUT = 180


class WinOcrError(RuntimeError):
    pass


def available() -> bool:
    return sys.platform == "win32" and SCRIPT.exists()


def _workdir() -> Path:
    for base in (Path.cwd(), Path(os.environ.get("TEMP", "."))):
        d = base / ".spn_tmp"
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except OSError:
            continue
    raise WinOcrError("找不到可写的临时目录")


def _invoke(
    path: Path,
    page: int = 0,
    width: int = 1800,
    region: tuple[float, float, float, float] | None = None,
    preview: bool = False,
    render_only: bool = False,
    preview_width: int | None = None,
) -> tuple[dict, bytes | None]:
    if not available():
        raise WinOcrError("当前系统不支持：需要 Windows + Windows.Media.Ocr")

    work = _workdir()
    tag = uuid.uuid4().hex[:12]
    out_json = work / f"ocr_{tag}.json"
    prev_file = work / f"ocr_{tag}.jpg"
    log = work / f"ocr_{tag}.log"

    args = ["-File", str(SCRIPT), "-Pdf", str(path), "-OutJson", str(out_json),
            "-Page", str(page), "-Width", str(width)]
    if region:
        args += ["-Region", ",".join(f"{v:.4f}" for v in region)]
    if preview:
        args += ["-PreviewPng", str(prev_file)]
    if preview_width:
        args += ["-PreviewWidth", str(int(preview_width))]
    if render_only:
        args += ["-RenderOnly"]

    try:
        with log.open("wb") as fh:
            proc = subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", *args],
                stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
            )
        if not out_json.exists():
            detail = log.read_text(encoding="utf-8", errors="replace")[:400] if log.exists() else ""
            raise WinOcrError(f"识别进程没有产出结果（exit {proc.returncode}）：{detail}")
        data = json.loads(out_json.read_text(encoding="utf-8-sig"))
        if data.get("error"):
            raise WinOcrError(str(data["error"]))
        png = prev_file.read_bytes() if prev_file.exists() else None
        return data, png
    finally:
        for f in (out_json, prev_file, log):
            try:
                f.unlink()
            except OSError:
                pass


def recognize_pdf(
    path: Path,
    page: int = 0,
    width: int = 1800,
    region: tuple[float, float, float, float] | None = None,
    preview: bool = True,
) -> tuple[list[str], bytes | None]:
    """返回 (文本行, 预览图JPEG或None)。region 为归一化 x0,y0,x1,y1。"""
    data, jpeg = _invoke(path, page, width, region, preview=preview)
    lines = [str(x) for x in data.get("lines", []) if str(x).strip()]
    return lines, jpeg


def render_thumb(path: Path, width: int = 800, thumb_width: int = 420) -> tuple[bytes | None, int]:
    """只渲染第一页做缩略图，不跑 OCR。返回 (JPEG, 页数)。"""
    data, jpeg = _invoke(
        path, 0, width, preview=True, render_only=True, preview_width=thumb_width
    )
    return jpeg, int(data.get("pages") or 1)


def region_image(
    path: Path,
    region: tuple[float, float, float, float],
    width: int = 1600,
    out_width: int = 900,
) -> bytes | None:
    """把姓名区域单独渲染成一张足够清楚的 JPEG，专门给视觉模型用。

    420px 的缩略图对 OCR 够用，对多模态模型太糊（8cm 宽只有 52dpi），
    所以这里单独渲染一版 900px 的。
    """
    _, jpeg = _invoke(
        path, 0, width, region=region, preview=True,
        render_only=True, preview_width=out_width,
    )
    return jpeg


def analyze_page(path: Path, page: int = 0, width: int = 1500) -> tuple[dict, bytes | None]:
    """整页识别，返回带归一化坐标的行 + 页面预览图。

    用于在网页里"自动找姓名区域"：行框坐标换成 0~1，前端画框/后端裁剪都用它。
    """
    data, jpeg = _invoke(path, page, width, preview=True)
    w = float(data.get("width") or 0) or 1.0
    h = float(data.get("height") or 0) or 1.0
    texts = data.get("lines") or []
    boxes = data.get("boxes") or []
    lines = []
    for text, box in zip(texts, boxes):
        try:
            bx = float(box.get("x", 0)) / w
            by = float(box.get("y", 0)) / h
            bw = float(box.get("w", 0)) / w
            bh = float(box.get("h", 0)) / h
        except (TypeError, ValueError):
            continue
        lines.append({
            "text": text,
            "box": [round(bx, 4), round(by, 4), round(bx + bw, 4), round(by + bh, 4)],
        })
    return {"width": int(w), "height": int(h), "lines": lines}, jpeg


def _pad(box: list[float], pad: float = 0.006) -> list[float]:
    """把行框扩成"够一整批用"的区域。

    行框是紧贴这一份文件的姓名的：张三和欧阳修宽度差很多，照抄行框会把长名字裁掉。
    所以右边固定多留 30% 页宽，上下各放 0.6 个行高。
    """
    x0, y0, x1, y1 = box
    h = max(y1 - y0, 0.012)
    x0 = max(0.0, x0 - pad)
    y0 = max(0.0, y0 - h * 0.6)
    x1 = min(1.0, max(x1 + 0.30, x0 + 0.30))
    y1 = min(1.0, y1 + h * 0.6)
    return [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)]


def guess_region(analysis: dict, names: list[str]) -> list[float] | None:
    """从整页 OCR 结果里猜「姓名在哪一行」。

    优先找出现了名单姓名的行；否则找带「姓名/名字」的行。
    猜错了用户可以拖动调整，所以这里宁可框大一点。
    """
    lines = analysis.get("lines") or []
    if not lines:
        return None

    wanted = [normalize(n) for n in names if len(normalize(n)) >= 2]
    for ln in lines:
        text = normalize(ln.get("text", ""))
        if not text:
            continue
        for name in wanted:
            if name and name in text:
                return _pad(ln["box"])

    for ln in lines:
        if re.search(r"姓名|名字|学生姓名", ln.get("text", "")):
            return _pad(ln["box"])
    return None
