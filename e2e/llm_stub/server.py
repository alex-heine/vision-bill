"""Deterministic OpenAI-compatible LLM stub for the e2e test stack.

Stdlib only. Serves ground-truth Receipt JSON keyed by sha256 of the
uploaded image bytes, so the app's real OpenAI provider, retry loop and
persistence all run for real. Fixtures load from /data (mounted
tests/e2e/data, opt-in local pairs) and /fixtures (mounted
e2e/llm_stub/fixtures, committed deterministic pairs; on hash collision
/fixtures wins).

Control API (e2e-only): POST /__mode  {"mode": "ok"|"down"|"repair_first"|"broken"}
                        GET  /__requests
                        GET  /__fixtures/<name>[.json]
"""

import base64
import hashlib
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA_DIR = Path("/data")
FIXTURES_DIR = Path("/fixtures")
MODES = ("ok", "down", "repair_first", "broken")
MODELS = [
    {
        "id": "e2e-vision",
        "object": "model",
        "owned_by": "e2e",
        "architecture": {"input_modalities": ["image", "text"], "output_modalities": ["text"]},
    }
]
GENERIC_RECEIPT = {
    "confidence": 99,
    "merchant_name": "E2E Generic Store",
    "date": "2026-01-01",
    "line_items": [
        {
            "description": "Generic Item",
            "quantity": 1.0,
            "unit_price": "5.00",
            "total_price": "5.00",
        }
    ],
    "subtotal": "5.00",
    "tax_total": "0",
    "total": "5.00",
    "payment_method": "cash",
}
IMAGE_EXTS = (".png", ".jpg", ".jpeg")

# `broken` tracks which image digests already got their one broken response in
# the current repair_first mode (cleared on every mode change) so the "first
# call is broken" rule is per-mode, not polluted by earlier tests' requests.
state = {"mode": "ok", "broken": set()}
requests_log: list[dict] = []


def load_fixture_map(directory: Path) -> dict[str, str]:
    """sha256(image bytes) -> raw ground-truth JSON text, for every valid pair in directory."""
    mapping: dict[str, str] = {}
    if not directory.is_dir():
        return mapping
    for image in sorted(directory.iterdir()):
        if image.suffix.lower() not in IMAGE_EXTS:
            continue
        ground_truth = image.with_suffix(".json")
        if not ground_truth.is_file():
            continue
        try:
            payload = json.loads(ground_truth.read_text(encoding="utf-8"))
            assert isinstance(payload, dict)
        except (json.JSONDecodeError, AssertionError):
            print(f"llm-stub: skipping {ground_truth.name} (not a valid JSON object)", flush=True)
            continue
        mapping[hashlib.sha256(image.read_bytes()).hexdigest()] = ground_truth.read_text(
            encoding="utf-8"
        )
    print(f"llm-stub: loaded {len(mapping)} fixture pair(s) from {directory}", flush=True)
    return mapping


# Committed /fixtures pairs win over opt-in /data pairs on hash collision,
# keeping the e2e contract deterministic in CI.
FIXTURES = {**load_fixture_map(DATA_DIR), **load_fixture_map(FIXTURES_DIR)}


def _extract_image_hash(body: dict) -> str | None:
    for message in body.get("messages", []):
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url", "")
                if url.startswith("data:"):
                    b64 = url.split(",", 1)[1]
                    return hashlib.sha256(base64.b64decode(b64)).hexdigest()
    return None


def _content_for(body: dict) -> str:
    if state["mode"] == "broken":
        requests_log.append({"image_sha256": None, "served": "broken"})
        return '{"merchant_name": "broken", oops'
    digest = _extract_image_hash(body)
    if state["mode"] == "repair_first" and digest is not None and digest not in state["broken"]:
        state["broken"].add(digest)
        requests_log.append({"image_sha256": digest, "served": "broken"})
        return '{"merchant_name": "broken", oops'
    if digest is not None and digest in FIXTURES:
        requests_log.append({"image_sha256": digest, "served": "fixture"})
        return FIXTURES[digest]
    requests_log.append({"image_sha256": digest, "served": "generic"})
    return json.dumps(GENERIC_RECEIPT)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _raw(self, status: int, content_type: str, data: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_fixture(self, name: str) -> None:
        """Serve a committed fixture: /__fixtures/<n> -> png, /__fixtures/<n>.json -> truth."""
        if not re.fullmatch(r"[a-z0-9]+(\.json)?", name):
            self._send(400, {"error": "bad fixture name"})
            return
        is_json = name.endswith(".json")
        base = name.removesuffix(".json")
        image = FIXTURES_DIR / f"{base}.png"
        truth = FIXTURES_DIR / f"{base}.json"
        if is_json and truth.is_file():
            self._raw(200, "application/json", truth.read_bytes())
        elif not is_json and image.is_file():
            self._raw(200, "image/png", image.read_bytes())
        else:
            self._send(404, {"error": f"no fixture {base!r}"})

    def do_GET(self) -> None:
        if state["mode"] == "down":
            self._send(503, {"error": "stub is in down mode"})
            return
        if self.path == "/v1/models":
            self._send(200, {"object": "list", "data": MODELS})
        elif self.path == "/__requests":
            self._send(200, {"requests": requests_log})
        elif self.path.startswith("/__fixtures/"):
            self._send_fixture(self.path[len("/__fixtures/") :])
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/__mode":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            mode = body.get("mode", "ok")
            if mode not in MODES:
                self._send(400, {"error": f"unknown mode {mode!r}"})
                return
            state["mode"] = mode
            state["broken"] = set()  # reset per-mode broken-once tracking
            self._send(200, {"mode": mode})
            return
        if state["mode"] == "down":
            self._send(503, {"error": "stub is in down mode"})
            return
        if self.path == "/v1/chat/completions":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            self._send(
                200,
                {
                    "id": "e2e-stub",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": "e2e-vision",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": _content_for(body)},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                },
            )
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"llm-stub: {self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9123), Handler).serve_forever()
