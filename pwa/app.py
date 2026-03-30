import json
import os
import sqlite3
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template, request

VALID_PERSONAS = frozenset({
    "focused_writer", "distracted_multitasker", "steady", "power_user", "custom"
})


def create_app(config_path=None, command_url=None):
    if config_path is None:
        config_path = os.environ.get("PRESENCE_CONFIG", "config.json")
    config_path = Path(config_path)
    if command_url is None:
        command_url = os.environ.get("PRESENCE_COMMAND_URL", "http://127.0.0.1:7777")

    app = Flask(__name__)

    def _read_config():
        with open(config_path) as f:
            return json.load(f)

    def _write_config(cfg):
        tmp = config_path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, config_path)

    def _proxy(path, method="GET"):
        try:
            if method == "GET":
                with urlopen(f"{command_url}{path}", timeout=5) as r:
                    return json.loads(r.read()), r.status
            else:
                req = Request(f"{command_url}{path}", data=b"", method=method)
                with urlopen(req, timeout=5) as r:
                    return json.loads(r.read()), r.status
        except URLError:
            return None, None

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/ping")
    def ping():
        return jsonify({"ok": True})

    @app.route("/api/status")
    def status():
        data, code = _proxy("/status")
        if data is None:
            return jsonify({"error": "engine offline"}), 503
        return jsonify(data), code

    @app.route("/api/start", methods=["POST"])
    def start():
        data, code = _proxy("/start", method="POST")
        if data is None:
            return jsonify({"error": "engine offline"}), 503
        return jsonify(data), code

    @app.route("/api/stop", methods=["POST"])
    def stop():
        data, code = _proxy("/stop", method="POST")
        if data is None:
            return jsonify({"error": "engine offline"}), 503
        return jsonify(data), code

    @app.route("/api/pause", methods=["POST"])
    def pause():
        data, code = _proxy("/pause", method="POST")
        if data is None:
            return jsonify({"error": "engine offline"}), 503
        return jsonify(data), code

    return app
