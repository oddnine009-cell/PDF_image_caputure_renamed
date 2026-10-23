"""假的视觉接口，用于在没有 API Key / 没有外网时跑通链路。

它长得和 DeepSeek 的 /chat/completions 一样，只是永远返回同一个名字。

    python tools/mock_vision.py --port 8799 --name 吴敏
    # 另开一个终端：
    set DEEPSEEK_API_KEY=test
    set DEEPSEEK_BASE_URL=http://127.0.0.1:8799
    python -m spn serve
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    name = "吴敏"
    calls = 0

    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        try:
            req = json.loads(body or b"{}")
            model = req.get("model", "?")
            n_img = sum(1 for m in req.get("messages", [])
                        for c in (m.get("content") or [])
                        if isinstance(c, dict) and c.get("type") == "image_url")
        except Exception:
            model, n_img = "?", 0
        type(self).calls += 1
        print(f"[mock] call #{type(self).calls} model={model} images={n_img} -> {type(self).name}",
              flush=True)

        payload = json.dumps({
            "id": "mock-1",
            "object": "chat.completion",
            "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": type(self).name}}],
            "usage": {"prompt_tokens": 800, "completion_tokens": 4, "total_tokens": 804},
        }, ensure_ascii=False).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--name", default="吴敏")
    args = ap.parse_args()
    Handler.name = args.name
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"mock vision listening on http://127.0.0.1:{args.port}  -> {args.name}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
