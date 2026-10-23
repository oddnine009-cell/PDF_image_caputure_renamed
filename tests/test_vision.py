"""视觉兜底的测试：用本地假接口验证客户端、提示词收敛和管线合并逻辑。

真实接口无法在这里访问（沙箱没网），但请求/响应形状与官方文档一致：
POST /chat/completions → choices[0].message.content
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from spn import vision                                      # noqa: E402
from spn.config import Config                               # noqa: E402
from spn.pipeline import process_file                        # noqa: E402
from spn.roster import Student                              # noqa: E402


class _FakeAPI(BaseHTTPRequestHandler):
    reply = "吴敏"
    seen: list[dict] = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).seen.append({"body": body, "auth": self.headers.get("Authorization")})
        payload = json.dumps({
            "choices": [{"message": {"role": "assistant", "content": type(self).reply}}]
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class VisionTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAPI)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()


class TestClean(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(vision._clean("吴敏"), "吴敏")

    def test_with_noise(self):
        self.assertEqual(vision._clean("图中姓名是：李四。"), "李四")
        self.assertEqual(vision._clean("「欧阳修」"), "欧阳修")

    def test_unclear(self):
        for text in ("?", "？", "看不清", "无法识别", "", "不确定"):
            self.assertEqual(vision._clean(text), "", text)

    def test_no_cjk(self):
        self.assertEqual(vision._clean("No name visible"), "")


class TestClient(VisionTestBase):
    def test_read_name(self):
        _FakeAPI.reply = "吴敏"
        name = vision.read_name(b"\xff\xd8\xff fake jpeg", key="k-test",
                                base_url=self.base, model="deepseek-flash")
        self.assertEqual(name, "吴敏")
        req = _FakeAPI.seen[-1]
        self.assertEqual(req["auth"], "Bearer k-test")
        body = req["body"]
        self.assertEqual(body["model"], "deepseek-flash")
        self.assertEqual(body["thinking"], {"type": "disabled"})
        content = body["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_unclear_reply(self):
        _FakeAPI.reply = "?"
        self.assertEqual(vision.read_name(b"x", key="k", base_url=self.base), "")

    def test_missing_key(self):
        with mock.patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
            with self.assertRaises(vision.VisionError):
                vision.read_name(b"x", key=None)


class TestPipelineMerge(VisionTestBase):
    def setUp(self):
        self.tmp = ROOT / ".tmp" / f"vision_{id(self)}"
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.pdf = self.tmp / "scan.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 fake")
        # 本地 OCR 只认出「张二」→ 应该 fail，等视觉兜底来救
        self.pdf.with_suffix(".ocr.json").write_text(
            json.dumps({"lines": ["张二"]}, ensure_ascii=False), encoding="utf-8"
        )
        self.students = [Student(name=n, raw_name=n)
                         for n in ("张三", "李四", "吴敏", "王五")]

    def _cfg(self, vision_mode="auto"):
        cfg = Config()
        cfg.ocr = "json"
        cfg.vision = vision_mode
        cfg.vision_key = "k-test"
        cfg.vision_base_url = self.base
        return cfg

    def test_vision_rescues_failure(self):
        _FakeAPI.reply = "吴敏"
        with mock.patch("spn.pipeline._vision_image", return_value=b"crop"):
            entry = process_file(self.pdf, self.students, self._cfg(), set())
        self.assertEqual(entry.vision_text, "吴敏")
        self.assertEqual(entry.name, "吴敏")
        self.assertIn("采纳", entry.reason)

    def test_vision_off_keeps_failure(self):
        with mock.patch("spn.pipeline._vision_image", return_value=b"crop"):
            entry = process_file(self.pdf, self.students, self._cfg("off"), set())
        self.assertEqual(entry.status, "fail")
        self.assertEqual(entry.vision_text, "")

    def test_vision_unreachable_is_harmless(self):
        cfg = self._cfg()
        cfg.vision_base_url = "http://127.0.0.1:1"   # 连不上
        cfg.vision_timeout = 2
        with mock.patch("spn.pipeline._vision_image", return_value=b"crop"):
            entry = process_file(self.pdf, self.students, cfg, set())
        self.assertEqual(entry.status, "fail")
        self.assertIn("视觉模型不可用", entry.reason)

    def test_vision_no_image_skipped(self):
        with mock.patch("spn.pipeline._vision_image", return_value=None):
            entry = process_file(self.pdf, self.students, self._cfg(), set())
        self.assertEqual(entry.status, "fail")
        self.assertEqual(entry.vision_text, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
