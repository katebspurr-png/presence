import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


def _make_handler(control, status_store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # suppress default access log
            logger.debug(f"http {fmt % args}")

        def _send_json(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/status":
                snapshot = status_store.snapshot()
                self._send_json(200, snapshot or {})
            else:
                self._send_json(404, {"error": "not found"})

        def do_POST(self):
            if self.path == "/start":
                control.stopped.clear()
                control.paused.clear()
                control.running.set()
                self._send_json(200, {"status": "started"})
            elif self.path == "/stop":
                control.running.clear()
                control.stopped.set()
                self._send_json(200, {"status": "stopped"})
            elif self.path == "/pause":
                if control.paused.is_set():
                    control.paused.clear()
                    self._send_json(200, {"status": "resumed"})
                else:
                    control.paused.set()
                    self._send_json(200, {"status": "paused"})
            else:
                self._send_json(404, {"error": "not found"})

    return Handler


class CommandServer(threading.Thread):
    """Minimal HTTP server on localhost for start/stop/pause/status commands."""

    def __init__(self, host: str, port: int, control, status_store) -> None:
        super().__init__(daemon=True, name="command-server")
        handler = _make_handler(control, status_store)

        class ReusableHTTPServer(HTTPServer):
            allow_reuse_address = True

        self._server = ReusableHTTPServer((host, port), handler)

    def run(self) -> None:
        logger.info(f"command_server_listening host={self._server.server_address[0]} port={self._server.server_address[1]}")
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
