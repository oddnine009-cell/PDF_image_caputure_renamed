"""PDF 读取与 OCR 适配层。

设计成"可插拔"：核心匹配逻辑不关心文字从哪来。
已实现：textlayer（PDF 文字层）、json（离线/自建 OCR 的产物）、baidu（手写体接口）、paddle（本地模型）。
"""

from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import Region


class BackendError(RuntimeError):
    pass


# --------------------------------------------------------------------------- PDF

def has_pymupdf() -> bool:
    try:
        import fitz  # noqa: F401
        return True
    except Exception:
        return False


def _fitz():
    try:
        import fitz  # type: ignore
        return fitz
    except Exception as exc:  # pragma: no cover
        raise BackendError("需要 PyMuPDF：pip install pymupdf") from exc


def page_text(path: Path, index: int) -> str:
    fitz = _fitz()
    with fitz.open(path) as doc:
        if index >= doc.page_count:
            return ""
        return doc.load_page(index).get_text("text") or ""


def page_count(path: Path) -> int:
    fitz = _fitz()
    with fitz.open(path) as doc:
        return doc.page_count


def render_page(
    path: Path,
    index: int = 0,
    dpi: int = 300,
    region: Region | None = None,
) -> bytes:
    """渲染整页或姓名区域为 PNG。region 的 y0 从页面顶部算起（符合看图直觉）。"""
    fitz = _fitz()
    with fitz.open(path) as doc:
        if index >= doc.page_count:
            raise BackendError(f"页码越界：{index} / {doc.page_count}")
        page = doc.load_page(index)
        clip = None
        if region:
            r = page.rect
            clip = fitz.Rect(
                r.x0 + region.x0 * r.width,
                r.y0 + region.y0 * r.height,
                r.x0 + region.x1 * r.width,
                r.y0 + region.y1 * r.height,
            )
        pix = page.get_pixmap(dpi=dpi, clip=clip)
        return pix.tobytes("png")


def page_size(path: Path, index: int = 0) -> tuple[float, float]:
    fitz = _fitz()
    with fitz.open(path) as doc:
        r = doc.load_page(index).rect
        return (r.width, r.height)


# --------------------------------------------------------------------------- OCR

@dataclass
class OcrResult:
    lines: list[str]
    backend: str


def _sidecar(path: Path) -> Path:
    return path.with_suffix(".ocr.json")


def ocr_json(path: Path) -> OcrResult:
    """读取同名 .ocr.json：{"lines": [...]} 或 {"text": "..."}。"""
    side = _sidecar(path)
    if not side.exists():
        raise BackendError(f"未找到 OCR 旁车文件：{side.name}")
    data = json.loads(side.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return OcrResult([str(x) for x in data], "json")
    if "words_result" in data:                      # 百度原始响应
        return OcrResult([w.get("words", "") for w in data["words_result"]], "json")
    if "lines" in data:
        return OcrResult([str(x) for x in data["lines"]], "json")
    if "text" in data:
        return OcrResult([ln for ln in str(data["text"]).splitlines() if ln.strip()], "json")
    raise BackendError(f"无法解析 {side.name} 的结构")


_BAIDU_TOKEN: dict[str, str] = {}


def _baidu_token() -> str:
    if "t" in _BAIDU_TOKEN:
        return _BAIDU_TOKEN["t"]
    ak = os.environ.get("BAIDU_OCR_AK")
    sk = os.environ.get("BAIDU_OCR_SK")
    if not ak or not sk:
        raise BackendError("缺少环境变量 BAIDU_OCR_AK / BAIDU_OCR_SK")
    url = (
        "https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials"
        f"&client_id={urllib.parse.quote(ak)}&client_secret={urllib.parse.quote(sk)}"
    )
    req = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    token = data.get("access_token")
    if not token:
        raise BackendError(f"获取百度 access_token 失败：{data}")
    _BAIDU_TOKEN["t"] = token
    return token


def ocr_baidu(png: bytes) -> OcrResult:
    """百度「手写文字识别」接口。个人免费额度适合小批量。"""
    token = _baidu_token()
    body = urllib.parse.urlencode({
        "image": base64.b64encode(png).decode("ascii"),
        "detect_direction": "false",
    }).encode("utf-8")
    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/handwriting?access_token={token}"
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error_code" in data:
        raise BackendError(f"百度 OCR 错误 {data['error_code']}: {data.get('error_msg')}")
    return OcrResult([w.get("words", "") for w in data.get("words_result", [])], "baidu")


def ocr_paddle(png: bytes) -> OcrResult:
    """本地 PaddleOCR。首次运行会下载模型，完全离线可用（需先 pip install）。"""
    try:
        import numpy as np
        from PIL import Image
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise BackendError("PaddleOCR 未安装：pip install paddleocr paddlepaddle pillow") from exc

    import io
    global _PADDLE_ENGINE
    try:
        engine = _PADDLE_ENGINE
    except NameError:
        engine = _PADDLE_ENGINE = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

    img = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
    raw = engine.ocr(img, cls=True)
    lines: list[str] = []
    for page in raw or []:
        for item in page or []:
            try:
                lines.append(item[1][0])
            except (IndexError, TypeError):
                continue
    return OcrResult(lines, "paddle")


def ocr_image(png: bytes, backend: str) -> OcrResult:
    if backend == "baidu":
        return ocr_baidu(png)
    if backend == "paddle":
        return ocr_paddle(png)
    raise BackendError(f"未知 OCR 后端：{backend}")
