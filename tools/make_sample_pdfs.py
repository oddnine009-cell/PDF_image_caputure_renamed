"""生成一批"扫描件"样本 PDF（用 Windows 自带字体绘制 + 纯 Python 打包成 PDF）。

用来验证真实链路：PDF -> WinRT 渲染 -> WinRT OCR -> 名单匹配 -> 重命名。
注意：这些样本是打印字体模拟的手写，只能证明管线通，不能代表真实手写识别率。

    python tools/make_sample_pdfs.py --count 8
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from spn.pdfwrite import image_pdf  # noqa: E402

RENDER_PS1 = ROOT / "tools" / "render_page.ps1"
POWERSHELL = "powershell.exe"

STUDENTS = [
    ("2023001", "张三", "高一(3)班"),
    ("2023002", "李四", "高一(3)班"),
    ("2023003", "王五", "高一(3)班"),
    ("2023004", "赵六", "高一(3)班"),
    ("2023005", "陈静", "高一(3)班"),
    ("2023006", "刘洋", "高一(3)班"),
    ("2023007", "周杰", "高一(3)班"),
    ("2023008", "吴敏", "高一(3)班"),
    ("2023009", "欧阳修", "高一(3)班"),
    ("2023010", "孙悦", "高一(3)班"),
]

BODY = [
    "1. 计算 3x + 5 = 20，求 x 的值。",
    "2. 化简 (a + b) 的平方，并说明公式含义。",
    "3. 证明：三角形内角和等于 180 度。",
    "4. 已知直角三角形两直角边为 3 和 4，求斜边。",
]


def run_powershell(args: list[str], log: Path) -> int:
    """跑 PowerShell。输出重定向到文件而不是管道——某些受限环境不允许建管道。"""
    cmd = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", *args]
    with log.open("wb") as fh:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT)
    return proc.returncode


def render_jpeg(name: str, klass: str, workdir: Path) -> Path:
    txt = workdir / "page.txt"
    txt.write_text(
        "\n".join([name, klass, "数学作业 第 3 周", "姓名：", *BODY]),
        encoding="utf-8",
    )
    out = workdir / "page.jpg"
    log = workdir / "render.log"
    code = run_powershell(
        ["-File", str(RENDER_PS1), "-TextFile", str(txt), "-Out", str(out), "-Font", "KaiTi"],
        log,
    )
    if code != 0 or not out.exists():
        detail = log.read_text(encoding="utf-8", errors="replace")[:500] if log.exists() else ""
        raise RuntimeError(f"渲染失败（exit {code}）：{detail}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "samples"))
    ap.add_argument("--count", type=int, default=len(STUDENTS))
    args = ap.parse_args()

    out_dir = Path(args.out)
    inc = out_dir / "incoming"
    inc.mkdir(parents=True, exist_ok=True)

    with (out_dir / "roster.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["学号", "姓名", "班级"])
        w.writerows(STUDENTS)

    for i, (sid, name, klass) in enumerate(STUDENTS[: args.count], 1):
        work = out_dir / ".work"
        work.mkdir(parents=True, exist_ok=True)
        jpg = render_jpeg(name, klass, work).read_bytes()
        pdf = image_pdf(jpg, dpi=150.0)
        target = inc / f"scan_{i:03d}.pdf"
        target.write_bytes(pdf)
        print(f"{target.name}  {len(pdf) / 1024:.0f} KB  <- {name}")

    print(f"\n样本目录：{inc}")
    print(f"名单：{out_dir / 'roster.csv'}")


if __name__ == "__main__":
    main()
