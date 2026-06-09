"""meshd — mesh execution server.

production-grade http server for running mesh programs.
stdlib only, python 3.12.

usage:
    python meshd.py                    # start on port 8080
    python meshd.py --port 9090        # custom port
    python meshd.py --key mykey        # require api key
    python meshd.py --timeout 60       # execution timeout
"""

import json
import os
import signal
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from mesh import run, check, ToolRegistry, Executor, lex, Parser


# ── rate limiter ──────────────────────────────────────────────────────────────

class TokenBucket:
    def __init__(self, rate: float = 1.0, burst: int = 60):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last = time.time()

    def consume(self) -> bool:
        now = time.time()
        elapsed = now - self.last
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

class RateLimiter:
    def __init__(self, rate: float = 1.0, burst: int = 60):
        self.buckets: dict[str, TokenBucket] = {}
        self.rate = rate
        self.burst = burst
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        with self._lock:
            if key not in self.buckets:
                self.buckets[key] = TokenBucket(self.rate, self.burst)
            return self.buckets[key].consume()


# ── server state ──────────────────────────────────────────────────────────────

class ServerState:
    def __init__(self):
        self.start_time = time.time()
        self.exec_count = 0
        self.total_duration = 0.0
        self._lock = threading.Lock()

    def record(self, duration: float):
        with self._lock:
            self.exec_count += 1
            self.total_duration += duration

    def status(self) -> dict:
        uptime = time.time() - self.start_time
        avg = (self.total_duration / self.exec_count) if self.exec_count > 0 else 0
        return {
            "uptime_s": round(uptime, 1),
            "exec_count": self.exec_count,
            "avg_duration_ms": round(avg * 1000, 2),
            "version": "meshd/0.3",
        }


# ── request handler ───────────────────────────────────────────────────────────

class MeshHandler(BaseHTTPRequestHandler):
    """HTTP handler for mesh execution."""

    # class-level state (set by main)
    api_key: str = ""
    timeout: int = 120
    rate_limiter: RateLimiter = RateLimiter(rate=1.0, burst=60)
    server_state: ServerState = ServerState()
    registry: ToolRegistry = ToolRegistry()

    def log_message(self, format, *args):
        # quiet: don't log every request to stderr
        pass

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, data: dict):
        """Send a server-sent event."""
        payload = "data: " + json.dumps(data, default=str) + "\n\n"
        self.wfile.write(payload.encode("utf-8"))
        self.wfile.flush()

    def _check_auth(self) -> bool:
        if not self.api_key:
            return True
        key = self.headers.get("X-API-Key", "")
        if key != self.api_key:
            self._send_json({"error": "unauthorized"}, 401)
            return False
        return True

    def _check_rate_limit(self) -> bool:
        ip = self.client_address[0]
        if not self.rate_limiter.is_allowed(ip):
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", "1")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "rate limited"}).encode())
            return False
        return True

    # ── GET ──

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/health":
            self._send_json({"status": "ok", "version": "0.3.0"})
            return

        if path == "/status":
            self._send_json(self.server_state.status())
            return

        if path == "/tools":
            tools = []
            for name in sorted(self.registry.list_tools()):
                meta = self.registry.get_meta(name)
                tools.append({
                    "name": name,
                    "description": meta.description if meta else "",
                    "category": meta.category if meta else "core",
                    "input_type": meta.input_type if meta else "any",
                    "output_type": meta.output_type if meta else "any",
                })
            self._send_json({"tools": tools, "count": len(tools)})
            return

        self._send_json({"error": "not found"}, 404)

    # ── POST ──

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path not in ("/run", "/exec"):
            self._send_json({"error": "not found"}, 404)
            return

        if not self._check_rate_limit():
            return

        if not self._check_auth():
            return

        # read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        # parse input
        if path == "/exec":
            source = body.decode("utf-8")
            input_data = None
        else:
            try:
                req = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_json({"error": "invalid json body"}, 400)
                return
            source = req.get("source", "")
            input_data = req.get("input")

        if not source:
            self._send_json({"error": "source is required"}, 400)
            return

        # check syntax first
        errs = check(source)
        if errs:
            self._send_json({"error": "syntax error", "details": errs}, 400)
            return

        # streaming mode?
        if params.get("stream", [False])[0] in ("1", "true", "yes"):
            self._execute_streaming(source, input_data)
            return

        # normal execution
        start = time.time()
        try:
            result = run(source, input_data=input_data, registry=self.registry, timeout=self.timeout)
            duration = time.time() - start
            self.server_state.record(duration)
            self._send_json({"ok": True, "result": result, "duration_ms": round(duration * 1000, 2)})
        except TimeoutError:
            self._send_json({"error": f"execution timed out after {self.timeout}s"}, 408)
        except Exception as e:
            self._send_json({"error": str(e), "trace": traceback.format_exc()}, 500)

    def _execute_streaming(self, source: str, input_data):
        """Execute with server-sent events streaming."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        start = time.time()
        try:
            tokens = lex(source)
            parser = Parser(tokens)
            ast = parser.parse()
            executor = Executor(registry=self.registry)

            data = input_data
            step_num = 0
            for stmt in ast:
                tool_calls = executor._collect_tools(stmt)
                for tc in tool_calls:
                    step_num += 1
                    step_start = time.time()
                    self._send_sse({
                        "event": "step_start",
                        "step": step_num,
                        "tool": tc.name,
                        "data": data,
                    })

                data = executor._exec_node(stmt, data)

                if tool_calls:
                    self._send_sse({
                        "event": "step_end",
                        "step": step_num,
                        "output": data,
                        "duration_ms": round((time.time() - step_start) * 1000, 2),
                    })

            duration = time.time() - start
            self.server_state.record(duration)
            self._send_sse({
                "event": "done",
                "result": data,
                "duration_ms": round(duration * 1000, 2),
            })

        except Exception as e:
            self._send_sse({"event": "error", "message": str(e)})


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description="mesh execution server")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--key", default="", help="api key (env MESH_API_KEY)")
    p.add_argument("--timeout", type=int, default=120, help="max execution seconds")
    p.add_argument("--rate", type=float, default=1.0, help="requests per second per ip")
    p.add_argument("--burst", type=int, default=60, help="max burst per ip")
    args = p.parse_args()

    api_key = args.key or os.environ.get("MESH_API_KEY", "")

    MeshHandler.api_key = api_key
    MeshHandler.timeout = args.timeout
    MeshHandler.rate_limiter = RateLimiter(rate=args.rate, burst=args.burst)
    MeshHandler.server_state = ServerState()
    MeshHandler.registry = ToolRegistry()

    server = HTTPServer((args.host, args.port), MeshHandler)
    print(f"meshd listening on {args.host}:{args.port}")
    if api_key:
        print(f"  api key: required (set via --key or MESH_API_KEY)")
    else:
        print(f"  api key: none (set --key or MESH_API_KEY for protection)")
    print(f"  timeout: {args.timeout}s")
    print(f"  rate limit: {args.rate}/s per ip, burst {args.burst}")
    print(f"  endpoints: GET /health GET /status GET /tools POST /run POST /exec")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()


import traceback  # needed for error handling in streaming
