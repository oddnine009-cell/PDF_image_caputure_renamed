"""DeepSeek 视觉兜底：把「认不出来」的姓名区域，再交给多模态模型读一遍。

设计原则（很重要）：**模型只负责认字，不负责决定是谁**。
它输出的文字会被当成一条额外的 OCR 结果，仍然走花名册闭集匹配。
所以模型再"自信"，也不能把张三写成李四——最多把一个 fail 抬成 review。

接口形状按官方文档（`POST /chat/completions`，OpenAI 兼容）：

    {"model": "deepseek-flash",
     "messages": [{"role": "user", "content": [
         {"type": "text", "text": "..."},
         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}]}],
     "thinking": {"type": "disabled"}, "temperature": 0, "max_tokens": 24}

注意：`deepseek-flash` 支持视觉，`deepseek-v4-pro` 不支持。
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from hashlib import sha1

DEFAULT_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"

PROMPT = (
    "这是一份学生作业「姓名」栏的局部截图，里面可能有一行手写姓名，也可能有打印的「姓名：」字样。"
    "请只输出手写的那个人名本身（2~4 个汉字），不要标点、不要引号、不要解释、不要输出打印字样。"
    "如果看不清或图里没有姓名，只输出一个问号。"
)

_CACHE: dict[str, str] = {}
_CACHE_MAX = 500

_CJK = re.compile(r"[\u4e00-\u9fff]{2,4}")
# 模型偶尔会附送一句"图中姓名是："，去掉这层壳再取名字
_LABEL = re.compile(r"(?:图中|图片|截图|图里|这里)?的?(?:姓名|名字|学生姓名)\s*[:：是为]?\s*")
_UNCLEAR = {"?", "？", "看不清", "看不清楚", "无法识别", "不确定", "没有", "无", "没有姓名", "未识别"}


class VisionError(RuntimeError):
    pass


def api_key(explicit: str | None = None) -> str | None:
    return (explicit or os.environ.get("DEEPSEEK_API_KEY") or "").strip() or None


def available(key: str | None = None) -> bool:
    return bool(api_key(key))


def _clean(text: str) -> str:
    """把模型输出收敛成「2~4 个汉字」，拿不到就返回空串。"""
    if not text:
        return ""
    t = text.strip().strip("。.,，、\"'“”「」『』")
    if not t or t in _UNCLEAR:
        return ""
    if "?" in t or "？" in t:
        return ""
    stripped = _LABEL.sub("", t)
    m = _CJK.search(stripped) or _CJK.search(t)
    if not m:
        return ""
    got = m.group(0)
    return "" if got in _UNCLEAR else got


def read_name(
    image: bytes,
    key: str | None = None,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE,
    detail: str = "high",
    timeout: float = 45.0,
) -> str:
    """让模型读图，返回它认为的姓名（可能为空串）。"""
    key = api_key(key)
    if not key:
        raise VisionError("未配置 DEEPSEEK_API_KEY")
    if not image:
        raise VisionError("没有可用的图片")

    digest = sha1(image).hexdigest() + "|" + model + "|" + base_url
    if digest in _CACHE:
        return _CACHE[digest]

    b64 = base64.b64encode(image).decode("ascii")
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": detail}},
            ],
        }],
        "thinking": {"type": "disabled"},   # 读个字而已，不需要思考链
        "temperature": 0,
        "max_tokens": 24,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise VisionError(f"HTTP {exc.code}: {body or exc.reason}") from exc
    except Exception as exc:
        raise VisionError(f"{type(exc).__name__}: {exc}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VisionError(f"响应格式异常：{str(data)[:200]}") from exc

    name = _clean(content or "")
    if len(_CACHE) < _CACHE_MAX:
        _CACHE[digest] = name
    return name
