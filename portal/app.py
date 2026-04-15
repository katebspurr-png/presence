import subprocess
from flask import Flask, render_template, request, redirect


def create_app():
    app = Flask(__name__)

    @app.route("/", methods=["GET"])
    def index():
        return render_template("index.html")

    @app.route("/save", methods=["POST"])
    def save():
        ssid = request.form.get("ssid", "").strip()
        password = request.form.get("password", "").strip()
        if not ssid:
            return render_template("index.html", error="WiFi network name is required.")
        _write_wifi_credentials(ssid, password)
        subprocess.Popen(["sudo", "shutdown", "-r", "+0"])
        return render_template("index.html", saved=True)

    # Captive portal detection endpoints (iOS, Android, Windows)
    for path in ["/generate_204", "/hotspot-detect.html",
                 "/ncsi.txt", "/connecttest.txt", "/redirect"]:
        app.add_url_rule(path, path, lambda: redirect("/"))

    return app


def _write_wifi_credentials(ssid: str, password: str) -> None:
    """Save WiFi credentials using nmcli (NetworkManager, Trixie+)."""
    subprocess.run(
        ["sudo", "nmcli", "device", "wifi", "connect", ssid,
         "password", password],
        check=True,
    )
