#!/usr/bin/env python3
"""Minimal fake OpenAI-compatible server for offline llmtap testing.

Endpoints:
- GET  /v1/models
- POST /v1/chat/completions (stream and non-stream)

Usage: python scripts/fake_server.py [port]
Set env FAKE_TTFT_MS and FAKE_ITL_MS to shape latency.
"""

from __future__ import annotations

import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WORDS = ("The sea was calm and the sky was blue . A small boat moved "
         "slowly over the water . The wind was soft and warm . ").split() * 4

TTFT_MS = float(os.environ.get("FAKE_TTFT_MS", "80"))
ITL_MS = float(os.environ.get("FAKE_ITL_MS", "12"))
MODEL_IDS = ["fake-7b", "fake-72b"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep the console quiet
        pass

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list",
                             "data": [{"id": m, "object": "model"}
                                      for m in MODEL_IDS]})
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": {"message": "not found"}})
            return
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.headers.get("Authorization", "").endswith("fail"):
            self._json(401, {"error": {"message": "bad key"}})
            return
        model = body.get("model", MODEL_IDS[0])
        words = WORDS
        prompt_tokens = max(1, len(str(body.get("messages", ""))) // 4)
        if body.get("stream"):
            self._stream(model, words, prompt_tokens)
        else:
            time.sleep(TTFT_MS / 1000 + ITL_MS * len(words) / 1000)
            self._json(200, {
                "id": "chatcmpl-fake", "object": "chat.completion",
                "model": model,
                "choices": [{
                    "index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant",
                                "content": " ".join(words)},
                }],
                "usage": {"prompt_tokens": prompt_tokens,
                          "completion_tokens": len(words),
                          "total_tokens": prompt_tokens + len(words)},
            })

    def _stream(self, model: str, words: list[str], prompt_tokens: int) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(obj: dict) -> None:
            self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n")
            self.wfile.flush()

        time.sleep(TTFT_MS / 1000)
        emit({"id": "x", "model": model,
              "choices": [{"index": 0, "delta": {"role": "assistant"}}]})
        for w in words:
            emit({"id": "x", "model": model,
                  "choices": [{"index": 0, "delta": {"content": w + " "}}]})
            time.sleep(random.uniform(0.5, 1.5) * ITL_MS / 1000)
        emit({"id": "x", "model": model,
              "choices": [{"index": 0, "delta": {},
                           "finish_reason": "stop"}]})
        emit({"id": "x", "model": model, "choices": [],
              "usage": {"prompt_tokens": prompt_tokens,
                        "completion_tokens": len(words),
                        "total_tokens": prompt_tokens + len(words)}})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


if __name__ == "__main__":
    port = int(os.environ.get("FAKE_PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"fake openai server on http://127.0.0.1:{port}/v1 "
          f"(ttft {TTFT_MS} ms, itl ~{ITL_MS} ms)")
    server.serve_forever()
