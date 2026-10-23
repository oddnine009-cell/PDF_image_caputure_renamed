"""本地网页应用：上传（带缩略图管理）→ 框选姓名区 → 识别 → 复核改名 → 下载。

只用标准库，不依赖任何云服务（识别走 Windows 自带 OCR，或你配置的其它后端）。

    python -m spn serve
    python -m spn serve --port 9000
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import threading
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse

from .config import Config, Region
from .naming import sanitize, unique_path
from .pipeline import process_file
from .roster import Student, dedupe_roster
from .text import normalize
from .web_page import PAGE

WORK_ROOT = Path.cwd() / "webrun"
MAX_UPLOAD = 60 * 1024 * 1024

_SESSIONS: dict[str, "Session"] = {}
_LOCK = threading.Lock()

DEMO_DIR: Path | None = None          # --demo 时指向仓库自带样例目录
REPO_ROOT = Path(__file__).resolve().parent.parent


def _demo_roster() -> list[str]:
    csv_path = (DEMO_DIR.parent / "roster.csv") if DEMO_DIR else None
    if not csv_path or not csv_path.exists():
        return []
    lines = csv_path.read_text(encoding="utf-8-sig").splitlines()
    names = []
    for line in lines[1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2 and parts[1]:
            names.append(parts[1])
    return names


def parse_names(roster_raw: str) -> list[Student]:
    out = []
    for raw in (roster_raw or "").splitlines():
        name = normalize(raw)
        if name:
            out.append(Student(name=name, raw_name=raw.strip()))
    return dedupe_roster(out)


def parse_region(text: str | None) -> Region | None:
    if not text:
        return None
    try:
        nums = [float(x) for x in text.replace(" ", "").split(",")]
    except ValueError:
        return None
    if len(nums) != 4:
        return None
    if not (0 <= nums[0] < nums[2] <= 1 and 0 <= nums[1] < nums[3] <= 1):
        return None
    return Region(x0=nums[0], y0=nums[1], x1=nums[2], y1=nums[3])


class Session:
    def __init__(self, roster_raw: str = "", region: str | None = None, ocr: str = "auto",
                 vision: str = "off", vision_key: str | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.dir = WORK_ROOT / self.id
        (self.dir / "in").mkdir(parents=True, exist_ok=True)
        self.files: list[dict] = []
        self.entries = []
        self.created = time.time()
        self.configure(roster_raw, region, ocr, vision, vision_key)

    # ------------------------------------------------------------ 配置
    def configure(self, roster_raw: str, region: str | None, ocr: str,
                  vision: str = "off", vision_key: str | None = None) -> None:
        self.students = parse_names(roster_raw)
        cfg = Config()
        cfg.ocr = ocr or "auto"
        cfg.mode = "copy"
        cfg.pattern = "{name}"
        cfg.outdir = self.dir / "renamed"
        cfg.keep_crop = True
        cfg.region = parse_region(region)
        cfg.vision = vision if vision in ("off", "auto", "always") else "off"
        cfg.vision_key = (vision_key or "").strip() or None
        self.cfg = cfg

    # ------------------------------------------------------------ 文件管理
    def add_file(self, filename: str, data: bytes) -> dict:
        safe = sanitize(Path(filename).name, 120)
        if not safe.lower().endswith(".pdf"):
            safe += ".pdf"
        fid = uuid.uuid4().hex[:8]
        target = self.dir / "in" / f"{fid}_{safe}"
        target.write_bytes(data)

        thumb, pages = None, 1
        try:
            from .winocr import available, render_thumb

            if available():
                thumb, pages = render_thumb(target)
        except Exception:
            pass

        item = {
            "fid": fid,
            "name": filename,
            "size": len(data),
            "pages": pages,
            "thumb": base64.b64encode(thumb).decode("ascii") if thumb else "",
            "path": str(target),
        }
        self.files.append(item)
        return self._public(item)

    def _public(self, item: dict) -> dict:
        return {k: item[k] for k in ("fid", "name", "size", "pages", "thumb")}

    def remove_file(self, fid: str) -> bool:
        for i, item in enumerate(self.files):
            if item["fid"] == fid:
                try:
                    Path(item["path"]).unlink()
                except OSError:
                    pass
                self.files.pop(i)
                return True
        return False

    def list_files(self) -> list[dict]:
        return [self._public(f) for f in self.files]

    # ------------------------------------------------------------ 识别
    def scan_all(self) -> list[dict]:
        self.entries = []
        rows = []
        for i, item in enumerate(self.files):
            entry = process_file(Path(item["path"]), self.students, self.cfg, set())
            self.entries.append(entry)
            rows.append({
                "id": i,
                "fid": item["fid"],
                "file": item["name"],
                "status": entry.status,
                "name": entry.name if entry.status != "fail" else "",
                "guess": entry.name,
                "score": round(entry.score, 3),
                "margin": round(entry.margin, 3),
                "matched": entry.matched,
                "reason": entry.error or entry.reason,
                "candidates": entry.candidates,
                "vision": entry.vision_text,
                "thumb": item["thumb"],
                "thumb_mime": "image/jpeg",
            })
        return rows

    def preview(self, fid: str) -> dict:
        from .winocr import analyze_page, available, guess_region

        if not available():
            raise RuntimeError("当前平台没有可用的预览渲染（需要 Windows）")
        item = next((f for f in self.files if f["fid"] == fid), None)
        if item is None:
            raise RuntimeError("找不到这个文件，可能已被删除")
        analysis, jpeg = analyze_page(Path(item["path"]), 0, width=1500)
        region = guess_region(analysis, [s.name for s in self.students])
        return {
            "image": base64.b64encode(jpeg or b"").decode("ascii"),
            "region": region,
            "lines": [ln["text"] for ln in analysis.get("lines", [])][:6],
        }

    # ------------------------------------------------------------ 输出
    def build_zip(self, corrections: dict[str, str]) -> tuple[Path, int]:
        out = self.dir / "renamed"
        if out.exists():
            shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)

        taken: set[str] = set()
        count = 0
        for i, entry in enumerate(self.entries):
            name = (corrections.get(str(i)) or (entry.name if entry.status != "fail" else "")).strip()
            name = sanitize(name, 60)
            if not name or name == "未命名":
                continue
            src = Path(entry.src)
            if not src.exists():
                continue
            target = unique_path(out / f"{name}.pdf", taken)
            shutil.copy2(src, target)
            count += 1

        zip_path = self.dir / "renamed.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(out.glob("*.pdf")):
                zf.write(f, arcname=f.name)
        return zip_path, count


def _parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    m = re.search(r'boundary="?([^";]+)"?', content_type or "")
    if not m:
        raise ValueError("缺少 multipart boundary")
    boundary = b"--" + m.group(1).encode("utf-8")
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}

    for chunk in body.split(boundary):
        if chunk in (b"", b"--", b"--\r\n", b"\r\n"):
            continue
        chunk = chunk.lstrip(b"\r\n")
        if chunk.startswith(b"--"):
            continue
        if b"\r\n\r\n" not in chunk:
            continue
        head, data = chunk.split(b"\r\n\r\n", 1)
        if data.endswith(b"\r\n"):
            data = data[:-2]
        headers = head.decode("utf-8", "replace")
        nm = re.search(r'name="([^"]*)"', headers)
        if not nm:
            continue
        key = nm.group(1)
        fm = re.search(r'filename="([^"]*)"', headers)
        if fm:
            files[key] = (fm.group(1), data)
        else:
            fields[key] = data.decode("utf-8", "replace")
    return fields, files


class Handler(BaseHTTPRequestHandler):
    server_version = "spn-web/0.3"

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj: dict, code: int = 200) -> None:
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            raise ValueError("上传内容过大")
        return self.rfile.read(length) if length else b""

    def _session(self, sid: str) -> "Session":
        with _LOCK:
            sess = _SESSIONS.get(sid)
        if not sess:
            raise ValueError("session 已失效，请刷新页面")
        return sess

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            data = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith("/api/zip/"):
            sid = path.rsplit("/", 1)[-1]
            zpath = WORK_ROOT / sid / "renamed.zip"
            if not zpath.exists():
                self._json({"error": "还没有生成结果"}, 404)
                return
            data = zpath.read_bytes()
            name = f"命名结果_{time.strftime('%m%d_%H%M')}.zip"
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(data)))
            self.send_header(
                "Content-Disposition",
                f"attachment; filename=renamed.zip; filename*=UTF-8''{quote(name)}",
            )
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/demo":
            self._demo_list()
            return
        if path.startswith("/api/demo/"):
            self._demo_file(path.rsplit("/", 1)[-1])
            return
        self._json({"error": "not found"}, 404)

    def _demo_list(self) -> None:
        if DEMO_DIR is None or not DEMO_DIR.is_dir():
            self._json({"error": "演示模式未开启"}, 404)
            return
        files = [
            {"name": f.name, "url": "/api/demo/" + quote(f.name)}
            for f in sorted(DEMO_DIR.glob("*.pdf"))
        ]
        self._json({"files": files, "roster": _demo_roster()})

    def _demo_file(self, name: str) -> None:
        from urllib.parse import unquote

        if DEMO_DIR is None:
            self._json({"error": "演示模式未开启"}, 404)
            return
        safe = Path(unquote(name)).name
        target = DEMO_DIR / safe
        if not target.is_file() or target.suffix.lower() != ".pdf":
            self._json({"error": "not found"}, 404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/session":
                self._create_session()
            elif path == "/api/upload":
                self._upload()
            elif path == "/api/delete":
                self._delete()
            elif path == "/api/config":
                self._config()
            elif path == "/api/scan":
                self._scan()
            elif path == "/api/preview":
                self._preview()
            elif path == "/api/apply":
                self._apply()
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    # ------------------------------------------------------------ handlers
    def _create_session(self) -> None:
        data = json.loads(self._body() or b"{}")
        sess = Session(
            roster_raw=data.get("roster", ""),
            region=data.get("region") or None,
            ocr=data.get("ocr") or "auto",
            vision=data.get("vision") or "off",
            vision_key=data.get("vision_key"),
        )
        with _LOCK:
            _SESSIONS[sess.id] = sess
        self._json({
            "session": sess.id,
            "roster_count": len(sess.students),
            "vision": sess.cfg.vision,
            "vision_ready": bool(sess.cfg.vision_key or os.environ.get("DEEPSEEK_API_KEY")),
        })

    def _upload(self) -> None:
        fields, files = _parse_multipart(self.headers.get("Content-Type", ""), self._body())
        sess = self._session(fields.get("session", ""))
        if "file" not in files:
            self._json({"error": "没有收到文件"}, 400)
            return
        filename, data = files["file"]
        self._json(sess.add_file(filename, data))

    def _delete(self) -> None:
        data = json.loads(self._body() or b"{}")
        sess = self._session(data.get("session", ""))
        ok = sess.remove_file(data.get("fid", ""))
        self._json({"ok": ok, "files": sess.list_files()})

    def _config(self) -> None:
        data = json.loads(self._body() or b"{}")
        sess = self._session(data.get("session", ""))
        sess.configure(
            roster_raw=data.get("roster", ""),
            region=data.get("region") or None,
            ocr=data.get("ocr") or "auto",
            vision=data.get("vision") or "off",
            vision_key=data.get("vision_key"),
        )
        self._json({
            "roster_count": len(sess.students),
            "region": sess.cfg.region.as_tuple() if sess.cfg.region else None,
            "vision": sess.cfg.vision,
        })

    def _preview(self) -> None:
        data = json.loads(self._body() or b"{}")
        sess = self._session(data.get("session", ""))
        self._json(sess.preview(data.get("fid", "")))

    def _scan(self) -> None:
        data = json.loads(self._body() or b"{}")
        sess = self._session(data.get("session", ""))
        if not sess.files:
            self._json({"error": "还没有上传文件"}, 400)
            return
        if not sess.students:
            self._json({"error": "名单是空的"}, 400)
            return
        self._json({"rows": sess.scan_all()})

    def _apply(self) -> None:
        data = json.loads(self._body() or b"{}")
        sess = self._session(data.get("session", ""))
        zip_path, count = sess.build_zip(data.get("corrections") or {})
        self._json({"count": count, "url": f"/api/zip/{sess.id}", "size": zip_path.stat().st_size})


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    demo: bool = False,
) -> None:
    global DEMO_DIR

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    if demo:
        DEMO_DIR = REPO_ROOT / "samples" / "incoming"
        if not DEMO_DIR.is_dir():
            print(f"演示目录不存在：{DEMO_DIR}（先跑 tools/make_sample_pdfs.py）")
            DEMO_DIR = None

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{httpd.server_address[1]}/"
    print(f"服务已启动：{url}")
    if DEMO_DIR:
        print(f"演示模式：{DEMO_DIR}")
    print("按 Ctrl+C 停止")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
