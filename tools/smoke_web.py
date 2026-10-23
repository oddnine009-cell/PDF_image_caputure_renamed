"""网页应用的端到端自检：起服务 → 建会话 → 上传 PDF → 生成 zip → 校验内容。

    python tools/smoke_web.py            # 用 samples/incoming 里的样本
    python tools/smoke_web.py --pdf a.pdf --roster names.txt
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import threading
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from spn.web import Handler, ThreadingHTTPServer  # noqa: E402


def build_multipart_files(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> tuple[bytes, str]:
    boundary = "----spn" + uuid.uuid4().hex
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n"
                     f"{value}\r\n".encode("utf-8"))
    for key, (filename, data) in files.items():
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"; "
                      f"filename=\"{filename}\"\r\nContent-Type: application/pdf\r\n\r\n").encode())
        parts.append(data)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", default=str(ROOT / "samples" / "incoming"))
    ap.add_argument("--roster", default=str(ROOT / "samples" / "roster.csv"))
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--base", default="", help="直接对已运行的服务做自检，例如 http://127.0.0.1:8765")
    ap.add_argument("--vision", default="off", choices=["off", "auto", "always"],
                    help="开启视觉兜底（服务端需配 DEEPSEEK_API_KEY）")
    args = ap.parse_args()

    roster_lines = []
    for line in Path(args.roster).read_text(encoding="utf-8-sig").splitlines()[1:]:
        if line.strip():
            roster_lines.append(line.split(",")[1])

    pdfs = sorted(Path(args.pdf_dir).glob("*.pdf"))[: args.limit]
    if not pdfs:
        print("没有样本 PDF，先跑 tools/make_sample_pdfs.py", file=sys.stderr)
        return 1

    httpd = None
    if args.base:
        base = args.base.rstrip("/")
    else:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def post_json(path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            base + path, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        roster = "\n".join(roster_lines)

        # 1) 建会话 → 逐个上传（每份都会返回缩略图）
        sid = post_json("/api/session", {"roster": roster, "ocr": "auto",
                                         "vision": args.vision})["session"]
        print("session:", sid)

        staged = []
        for pdf in pdfs:
            body, ctype = build_multipart_files(
                {"session": sid}, {"file": (pdf.name, pdf.read_bytes())}
            )
            req = urllib.request.Request(base + "/api/upload", data=body,
                                         headers={"Content-Type": ctype}, method="POST")
            with urllib.request.urlopen(req, timeout=180) as resp:
                item = json.loads(resp.read().decode("utf-8"))
            staged.append(item)
            print(f"  upload {pdf.name:<16} {item['pages']}页 "
                  f"{item['size']//1024}KB thumb={'yes' if item['thumb'] else 'no'}")

        # 2) 预览首份 → 自动定位姓名区域
        prev = post_json("/api/preview", {"session": sid, "fid": staged[0]["fid"]})
        region = prev.get("region")
        region_str = ",".join(f"{v:.3f}" for v in region) if region else ""
        print("preview: region =", region, "| 前几行:", " / ".join(prev.get("lines", [])[:3]))

        # 3) 删一个再补一个，验证增删不会丢文件
        post_json("/api/delete", {"session": sid, "fid": staged[-1]["fid"]})
        body, ctype = build_multipart_files(
            {"session": sid}, {"file": (pdfs[-1].name, pdfs[-1].read_bytes())}
        )
        req = urllib.request.Request(base + "/api/upload", data=body,
                                     headers={"Content-Type": ctype}, method="POST")
        with urllib.request.urlopen(req, timeout=180) as resp:
            again = json.loads(resp.read().decode("utf-8"))
        print(f"  删除+重加 {again['name']} ok")

        # 4) 应用配置并识别
        post_json("/api/config", {"session": sid, "roster": roster,
                                  "region": region_str, "ocr": "auto",
                                  "vision": args.vision})
        rows = post_json("/api/scan", {"session": sid})["rows"]
        for row in rows:
            ai = f" AI={row['vision']}" if row.get("vision") else ""
            print(f"  {row['file']:<16} {row['status']:<7} {row['name'] or '-':<6} "
                  f"{row['score']:.2f} thumb={'yes' if row['thumb'] else 'no'}{ai}")

        # 5) 打包下载
        corrections = {str(r["id"]): r["name"] or "测试同学" for r in rows if r["status"] != "ok"}
        result = post_json("/api/apply", {"session": sid, "corrections": corrections})
        print("apply:", result)

        with urllib.request.urlopen(base + result["url"], timeout=60) as resp:
            blob = resp.read()
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = zf.namelist()
        print("zip 内容:", names)

        assert len(rows) == len(pdfs), f"识别结果 {len(rows)} != 上传 {len(pdfs)}"
        assert len(names) == len(rows), f"zip 内文件数 {len(names)} != 结果数 {len(rows)}"
        assert result["count"] == len(rows)
        print("\nOK：上传(缩略图/增删) → 框选 → 识别 → 生成 → 下载 全链路通过")
        return 0
    finally:
        if httpd:
            httpd.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
