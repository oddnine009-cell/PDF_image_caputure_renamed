"""配置加载。使用标准库 tomllib（Python 3.11+），不引入 yaml 依赖。"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Region:
    """姓名所在区域，坐标为页面归一化比例（0~1），左下原点与 UI 无关。"""

    page: int = 1
    x0: float = 0.06
    y0: float = 0.03
    x1: float = 0.94
    y1: float = 0.20

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


@dataclass
class Config:
    # 输入
    roster: Path | None = None
    input_dir: Path | None = None
    # 输出
    pattern: str = "{name}"
    mode: str = "copy"            # copy | rename
    outdir: Path = Path("out")
    # 识别
    dpi: int = 300
    max_pages: int = 1
    ocr: str = "auto"             # auto | textlayer | json | winocr | baidu | paddle
    region: Region | None = None  # 只裁姓名区识别（强烈推荐）
    use_text_layer: bool = True
    keep_crop: bool = True
    # Windows OCR 换个渲染宽度结果就变，跑两档再合并比单档稳得多
    ocr_widths: tuple[int, ...] = (1200, 1400)
    # 匹配
    ok_threshold: float = 0.80
    review_threshold: float = 0.58
    # 框了姓名区域时只用看那一小块，噪声低，一个字的偏差也该交人工看一眼
    review_threshold_roi: float = 0.48
    min_margin: float = 0.08
    name_min_len: int = 2
    name_max_len: int = 4
    context_bonus: float = 0.05
    top_k: int = 3
    # 视觉兜底（DeepSeek deepseek-flash）：只对没认准的件，把姓名区域图再读一遍
    vision: str = "off"                       # off | auto | always
    vision_model: str = "deepseek-flash"
    vision_base_url: str = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    vision_detail: str = "high"
    vision_timeout: float = 45.0
    vision_key: str | None = None             # 优先用环境变量 DEEPSEEK_API_KEY

    @classmethod
    def load(cls, path: Path | str | None) -> "Config":
        cfg = cls()
        if not path:
            return cfg
        p = Path(path)
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        return cfg._merge(data)

    def _merge(self, data: dict[str, Any]) -> "Config":
        def pv(v):
            return Path(v).expanduser() if isinstance(v, str) and ("/" in v or "\\" in v) else v

        top = {"roster", "input_dir", "pattern", "mode", "outdir", "dpi", "max_pages",
               "ocr", "use_text_layer", "keep_crop"}
        for key in top:
            if key in data:
                setattr(self, key, pv(data[key]))

        if "region" in data and data["region"]:
            r = data["region"]
            self.region = Region(
                page=int(r.get("page", 1)),
                x0=float(r.get("x0", 0.06)),
                y0=float(r.get("y0", 0.03)),
                x1=float(r.get("x1", 0.94)),
                y1=float(r.get("y1", 0.20)),
            )

        m = data.get("match", {})
        for key in ("ok_threshold", "review_threshold", "review_threshold_roi",
                    "min_margin", "name_min_len", "name_max_len", "context_bonus",
                    "top_k", "ocr_widths"):
            if key in m:
                setattr(self, key, type(getattr(self, key))(m[key]))

        v = data.get("vision", {})
        if isinstance(v, dict):
            if "mode" in v:
                self.vision = str(v["mode"])
            if "model" in v:
                self.vision_model = str(v["model"])
            if "base_url" in v:
                self.vision_base_url = str(v["base_url"])
            if "detail" in v:
                self.vision_detail = str(v["detail"])
            if "timeout" in v:
                self.vision_timeout = float(v["timeout"])

        if isinstance(self.outdir, str):
            self.outdir = Path(self.outdir)
        if isinstance(self.roster, str):
            self.roster = Path(self.roster)
        if isinstance(self.input_dir, str):
            self.input_dir = Path(self.input_dir)
        return self

    def validate(self) -> None:
        if self.mode not in ("copy", "rename"):
            raise ValueError(f"mode 只能是 copy 或 rename，收到 {self.mode!r}")
        if self.review_threshold > self.ok_threshold:
            raise ValueError("review_threshold 不能大于 ok_threshold")
        if self.region and not (0 <= self.region.x0 < self.region.x1 <= 1):
            raise ValueError("region.x0/x1 必须在 0~1 且 x0<x1")
