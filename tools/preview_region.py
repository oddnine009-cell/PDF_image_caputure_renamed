"""在页面上画出姓名区域的红框，用来肉眼校准 --region 坐标。

需要 PyMuPDF（pip install pymupdf）。只修改内存中的页面，不会写回原 PDF。

    python tools/preview_region.py 作业.pdf --region 0.10,0.04,0.62,0.13
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="预览姓名区域框选位置")
    ap.add_argument("pdf")
    ap.add_argument("--region", default="0.10,0.04,0.62,0.13", help="x0,y0,x1,y1（0~1）")
    ap.add_argument("--page", type=int, default=1, help="第几页，从 1 开始")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("-o", "--out", default="region_preview.png")
    args = ap.parse_args()

    try:
        import fitz
    except Exception:
        print("需要 PyMuPDF：pip install pymupdf", file=sys.stderr)
        return 1

    nums = [float(x) for x in args.region.replace(" ", "").split(",")]
    if len(nums) != 4:
        print("--region 需要 4 个数字：x0,y0,x1,y1", file=sys.stderr)
        return 1

    with fitz.open(args.pdf) as doc:
        page = doc.load_page(max(0, args.page - 1))
        r = page.rect
        box = fitz.Rect(
            r.x0 + nums[0] * r.width, r.y0 + nums[1] * r.height,
            r.x0 + nums[2] * r.width, r.y0 + nums[3] * r.height,
        )
        page.draw_rect(box, color=(1, 0, 0), width=2)
        page.get_pixmap(dpi=args.dpi).save(args.out)

    print(f"已导出 {args.out}（红框 = 会被送去识别的区域）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
