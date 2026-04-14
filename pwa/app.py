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
        try:
            cfg = _read_config()
            data["configured_persona"] = cfg.get("persona", "")
        except Exception:
            pass
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

    @app.route("/api/persona", methods=["POST"])
    def set_persona():
        body = request.get_json(force=True, silent=True) or {}
        name = body.get("persona", "")
        if name not in VALID_PERSONAS:
            return jsonify({"error": "unknown persona"}), 400
        try:
            cfg = _read_config()
            cfg["persona"] = name
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        return jsonify({"persona": name})

    @app.route("/api/activity_log")
    def activity_log():
        try:
            cfg = _read_config()
            db_path = cfg.get("logging", {}).get("db_path", "")
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT ts, activity, persona, duration_s FROM activity_log "
                    "ORDER BY id DESC LIMIT 8"
                ).fetchall()
            return jsonify([
                {"ts": r[0], "activity": r[1], "persona": r[2], "duration_s": r[3]}
                for r in rows
            ])
        except Exception:
            return jsonify([])

    @app.route("/api/dead_zones", methods=["POST"])
    def add_dead_zone():
        body = request.get_json(force=True, silent=True) or {}
        try:
            cfg = _read_config()
            cfg.setdefault("dead_zones", []).append({
                "start": body["start"],
                "end": body["end"],
                "days": body["days"],
            })
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        return jsonify({"dead_zones": cfg["dead_zones"]})

    @app.route("/api/dead_zones/<int:index>", methods=["PUT"])
    def update_dead_zone(index):
        body = request.get_json(force=True, silent=True) or {}
        try:
            cfg = _read_config()
            zones = cfg.get("dead_zones", [])
            if index >= len(zones):
                return jsonify({"error": "index out of range"}), 404
            zones[index] = {
                "start": body["start"],
                "end": body["end"],
                "days": body["days"],
            }
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        return jsonify({"dead_zones": zones})

    @app.route("/api/dead_zones/<int:index>", methods=["DELETE"])
    def delete_dead_zone(index):
        try:
            cfg = _read_config()
            zones = cfg.get("dead_zones", [])
            if index >= len(zones):
                return jsonify({"error": "index out of range"}), 404
            zones.pop(index)
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        return jsonify({"dead_zones": zones})

    return app
