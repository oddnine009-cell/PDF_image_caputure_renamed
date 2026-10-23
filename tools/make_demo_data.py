"""生成演示数据。

真实项目里这些 .pdf 是扫描件，需要真 OCR；这里为了不依赖任何识别服务，
给每个 PDF 配一份同名 .ocr.json（模拟「OCR 已经跑完」的结果），
用 --ocr json 就能跑通全链路，看到匹配/复核/失败的分类效果。

    python tools/make_demo_data.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"

ROSTER = [
    ("2023001", "张三", "高一(3)班"),
    ("2023002", "李四", "高一(3)班"),
    ("2023003", "王五", "高一(3)班"),
    ("2023004", "赵六", "高一(3)班"),
    ("2023005", "陈静", "高一(3)班"),
    ("2023006", "刘洋", "高一(3)班"),
    ("2023007", "周杰", "高一(3)班"),
    ("2023008", "吴敏", "高一(3)班"),
    ("2023009", "孙悦", "高一(3)班"),
    ("2023010", "孙月", "高一(3)班"),
    ("2023011", "欧阳修", "高一(3)班"),
]

# 文件名 -> 模拟的 OCR 行
CASES: list[tuple[str, list[str]]] = [
    ("01_扫描件.pdf", ["姓名：张三"]),
    ("02_扫描件.pdf", ["李四", "高一(3)班"]),
    ("03_扫描件.pdf", ["王 五"]),
    ("04_扫描件.pdf", ["赵六  学号 2023004"]),
    ("05_扫描件.pdf", ["姓名:陈静"]),
    ("06_扫描件.pdf", ["刘洋 作业 第3周"]),
    ("07_扫描件.pdf", ["周杰"]),
    ("08_扫描件.pdf", ["姓名：吴敏", "班级：高一(3)班"]),
    ("09_扫描件.pdf", ["欧阳修"]),
    ("10_扫描件.pdf", ["欧阳休"]),          # 三字名错一字 -> 应进复核
    ("11_扫描件.pdf", ["张二"]),            # 错得太远 -> 应判失败
    ("12_扫描件.pdf", ["第一章 绪论 1.1 集合"]),  # 根本不是姓名
    ("13_扫描件.pdf", ["姓名：张三"]),      # 与 01 重名 -> 应自动加 (2)
]


def main() -> None:
    inc = DEMO / "incoming"
    inc.mkdir(parents=True, exist_ok=True)

    with (DEMO / "roster.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["学号", "姓名", "班级"])
        w.writerows(ROSTER)

    for name, lines in CASES:
        pdf = inc / name
        pdf.write_bytes(b"%PDF-1.4\n% demo placeholder, OCR comes from sidecar json\n")
        pdf.with_suffix(".ocr.json").write_text(
            json.dumps({"lines": lines}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"已生成 {len(CASES)} 份演示数据：{inc}")
    print(f"名单：{DEMO / 'roster.csv'}（{len(ROSTER)} 人）")


if __name__ == "__main__":
    main()
