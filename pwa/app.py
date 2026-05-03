import json
import os
import sqlite3
import subprocess
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
            data["forced_activity"] = cfg.get("forced_activity")
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

    # ── Override ─────────────────────────────────────────────────────────────

    @app.route("/api/override", methods=["GET"])
    def override_get():
        try:
            cfg = _read_config()
            return jsonify(cfg.get("override", {"active": False, "expires_at": None}))
        except Exception:
            return jsonify({"error": "config error"}), 500

    @app.route("/api/override", methods=["POST"])
    def override_set():
        """Enable override. Body: {"duration_minutes": N} or {} for indefinite."""
        body = request.get_json(force=True, silent=True) or {}
        duration = body.get("duration_minutes")
        expires_at = None
        if duration is not None:
            try:
                duration = int(duration)
                if duration <= 0:
                    return jsonify({"error": "duration_minutes must be positive"}), 400
                from datetime import datetime, timedelta
                expires_at = (datetime.now() + timedelta(minutes=duration)).isoformat(timespec="seconds")
            except (ValueError, TypeError):
                return jsonify({"error": "invalid duration_minutes"}), 400
        try:
            cfg = _read_config()
            cfg["override"] = {"active": True, "expires_at": expires_at}
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        return jsonify(cfg["override"])

    @app.route("/api/override", methods=["DELETE"])
    def override_delete():
        try:
            cfg = _read_config()
            cfg["override"] = {"active": False, "expires_at": None}
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        return jsonify({"active": False, "expires_at": None})

    # ── Forced activity ──────────────────────────────────────────────────────

    @app.route("/api/activity", methods=["POST"])
    def activity_set():
        body = request.get_json(force=True, silent=True) or {}
        activity = body.get("activity", "")
        if activity not in ("typing", "mouse", "idle"):
            return jsonify({"error": "activity must be typing, mouse, or idle"}), 400
        try:
            cfg = _read_config()
            cfg["forced_activity"] = activity
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        return jsonify({"forced_activity": activity})

    @app.route("/api/activity", methods=["DELETE"])
    def activity_clear():
        try:
            cfg = _read_config()
            cfg.pop("forced_activity", None)
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        return jsonify({"forced_activity": None})

    # ── Bluetooth ────────────────────────────────────────────────────────────

    @app.route("/api/bluetooth", methods=["GET"])
    def bluetooth_get():
        try:
            cfg = _read_config()
            return jsonify({"hid_mode": cfg.get("hid_mode", "usb")})
        except Exception:
            return jsonify({"error": "config error"}), 500

    @app.route("/api/bluetooth", methods=["POST"])
    def bluetooth_set():
        body = request.get_json(force=True, silent=True) or {}
        mode = body.get("hid_mode", "")
        if mode not in ("usb", "bluetooth"):
            return jsonify({"error": "hid_mode must be 'usb' or 'bluetooth'"}), 400
        try:
            cfg = _read_config()
            cfg["hid_mode"] = mode
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        # Signal engine to reload config
        _proxy("/reload", method="POST")
        return jsonify({"hid_mode": mode})

    @app.route("/api/bluetooth/discover", methods=["POST"])
    def bluetooth_discover():
        """Make the Pi discoverable for BT pairing (runs bluetoothctl on the Pi)."""
        try:
            result = subprocess.run(
                ["bluetoothctl", "discoverable", "on"],
                timeout=5, capture_output=True, text=True,
            )
            return jsonify({"ok": result.returncode == 0, "output": result.stdout.strip()})
        except FileNotFoundError:
            return jsonify({"error": "bluetoothctl not found (not running on Pi?)"}), 500
        except subprocess.TimeoutExpired:
            return jsonify({"error": "bluetoothctl timed out"}), 500

    # ── Screen settings ──────────────────────────────────────────────────────

    @app.route("/api/settings", methods=["GET"])
    def settings_get():
        try:
            cfg = _read_config()
            return jsonify({
                "screen": cfg.get("screen", {"width": 1920, "height": 1080}),
                "hid_mode": cfg.get("hid_mode", "usb"),
            })
        except Exception:
            return jsonify({"error": "config error"}), 500

    @app.route("/api/settings", methods=["POST"])
    def settings_set():
        body = request.get_json(force=True, silent=True) or {}
        try:
            cfg = _read_config()
            if "screen" in body:
                w = int(body["screen"].get("width", 1920))
                h = int(body["screen"].get("height", 1080))
                if not (320 <= w <= 7680 and 240 <= h <= 4320):
                    return jsonify({"error": "screen dimensions out of range"}), 400
                cfg["screen"] = {"width": w, "height": h}
            _write_config(cfg)
        except (ValueError, TypeError):
            return jsonify({"error": "invalid dimensions"}), 400
        except Exception:
            return jsonify({"error": "config error"}), 500
        _proxy("/reload", method="POST")
        return jsonify({"screen": cfg["screen"]})

    return app
