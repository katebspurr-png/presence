# Pi Deployment & WiFi Onboarding Plan

**Goal:** Get Presence running on a Pi Zero 2W — code deployed, systemd services running on boot, USB HID gadget mode configured — and add a first-boot captive portal so non-technical users can configure WiFi without flashing an SD card or editing files.

**Two phases:**
1. **Deployment** — SSH in, clone repo, configure USB gadget mode, install deps, enable systemd services
2. **WiFi Onboarding** — on first boot (no WiFi configured), Pi creates a hotspot; user connects and visits a setup page to enter credentials; Pi saves them and reboots onto the real network

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `setup/enable-gadget.sh` | Configure USB gadget mode (HID keyboard + mouse) |
| Create | `setup/firstboot.sh` | Detect WiFi state; switch between AP mode and normal mode |
| Create | `setup/install.sh` | One-shot install script (deps, venv, systemd services) |
| Create | `setup/dnsmasq-ap.conf` | dnsmasq config for AP mode (DHCP + captive portal redirect) |
| Create | `setup/hostapd.conf` | hostapd config for AP hotspot |
| Create | `portal/app.py` | Flask setup portal (SSID/password form + save + reboot) |
| Create | `portal/templates/index.html` | Single-page setup UI |
| Create | `portal/__init__.py` | Package marker |
| Create | `run_portal.py` | Entrypoint for setup portal |
| Create | `presence-portal.service` | systemd unit for setup portal (AP mode only) |
| Create | `presence-firstboot.service` | systemd unit that runs firstboot.sh on every boot |
| Modify | `presence.service` | Add `After=presence-firstboot.service` |
| Modify | `presence-pwa.service` | Add `After=presence-firstboot.service` |
| Modify | `requirements.txt` | Add `netifaces>=0.11` for network interface detection |
| Modify | `docs/README.md` | Add deployment and onboarding sections |

---

## Phase 1: Pi Deployment

### Task 1: SSH in and prep the system

**On your Mac:**
```bash
ssh pi@<pi-ip>
```

**On the Pi:**
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3-pip python3-venv
```

### Task 2: Configure USB HID gadget mode

The Pi Zero 2W must present itself as a USB keyboard and mouse to the host computer. This requires configuring USB gadget mode via the `dwc2` overlay and `libcomposite`.

- [ ] **Step 1: Enable dwc2 overlay**

  Edit `/boot/firmware/config.txt` (Trixie uses `/boot/firmware/`, not `/boot/`):
  ```bash
  echo "dtoverlay=dwc2" | sudo tee -a /boot/firmware/config.txt
  ```

- [ ] **Step 2: Load dwc2 and libcomposite modules**

  ```bash
  echo "dwc2" | sudo tee -a /etc/modules
  echo "libcomposite" | sudo tee -a /etc/modules
  ```

- [ ] **Step 3: Create `setup/enable-gadget.sh`**

  This script creates the USB composite gadget device (keyboard + mouse) and must run before the engine starts.

  ```bash
  #!/bin/bash
  # Sets up USB HID gadget (keyboard + mouse) via ConfigFS
  set -e

  GADGET=/sys/kernel/config/usb_gadget/presence

  modprobe libcomposite

  mkdir -p $GADGET
  echo 0x1d6b > $GADGET/idVendor   # Linux Foundation
  echo 0x0104 > $GADGET/idProduct  # Multifunction Composite Gadget
  echo 0x0100 > $GADGET/bcdDevice
  echo 0x0200 > $GADGET/bcdUSB

  mkdir -p $GADGET/strings/0x409
  echo "Infinite Saturdays" > $GADGET/strings/0x409/manufacturer
  echo "Presence HID"       > $GADGET/strings/0x409/product
  echo "IS000001"           > $GADGET/strings/0x409/serialnumber

  # HID keyboard function
  mkdir -p $GADGET/functions/hid.keyboard
  echo 1    > $GADGET/functions/hid.keyboard/protocol   # keyboard
  echo 1    > $GADGET/functions/hid.keyboard/subclass
  echo 8    > $GADGET/functions/hid.keyboard/report_length
  printf '\x05\x01\x09\x06\xa1\x01\x05\x07\x19\xe0\x29\xe7\x15\x00\x25\x01\x75\x01\x95\x08\x81\x02\x95\x01\x75\x08\x81\x03\x95\x05\x75\x01\x05\x08\x19\x01\x29\x05\x91\x02\x95\x01\x75\x03\x91\x03\x95\x06\x75\x08\x15\x00\x25\x65\x05\x07\x19\x00\x29\x65\x81\x00\xc0' \
    > $GADGET/functions/hid.keyboard/report_desc

  # HID mouse function
  mkdir -p $GADGET/functions/hid.mouse
  echo 2    > $GADGET/functions/hid.mouse/protocol       # mouse
  echo 1    > $GADGET/functions/hid.mouse/subclass
  echo 4    > $GADGET/functions/hid.mouse/report_length
  printf '\x05\x01\x09\x02\xa1\x01\x09\x01\xa1\x00\x05\x09\x19\x01\x29\x03\x15\x00\x25\x01\x95\x03\x75\x01\x81\x02\x95\x01\x75\x05\x81\x03\x05\x01\x09\x30\x09\x31\x09\x38\x15\x81\x25\x7f\x75\x08\x95\x03\x81\x06\xc0\xc0' \
    > $GADGET/functions/hid.mouse/report_desc

  # Bind functions to configuration
  mkdir -p $GADGET/configs/c.1/strings/0x409
  echo "HID Config" > $GADGET/configs/c.1/strings/0x409/configuration
  echo 250          > $GADGET/configs/c.1/MaxPower

  ln -sf $GADGET/functions/hid.keyboard $GADGET/configs/c.1/
  ln -sf $GADGET/functions/hid.mouse    $GADGET/configs/c.1/

  # Bind to UDC (USB Device Controller)
  ls /sys/class/udc > $GADGET/UDC

  echo "USB HID gadget enabled: /dev/hidg0 (keyboard), /dev/hidg1 (mouse)"
  ```

  ```bash
  chmod +x setup/enable-gadget.sh
  ```

- [ ] **Step 4: Create a systemd unit for the gadget setup**

  Edit `presence.service` to run gadget setup before the engine:
  ```ini
  [Unit]
  Description=Presence Behavioral Engine
  After=network.target presence-gadget.service
  Requires=presence-gadget.service
  ```

  Create `presence-gadget.service`:
  ```ini
  [Unit]
  Description=Presence USB HID Gadget Setup
  After=local-fs.target

  [Service]
  Type=oneshot
  RemainAfterExit=yes
  ExecStart=/home/pi/presence/setup/enable-gadget.sh

  [Install]
  WantedBy=multi-user.target
  ```

- [ ] **Step 5: Reboot and verify `/dev/hidg0` and `/dev/hidg1` exist**
  ```bash
  sudo reboot
  # after reboot:
  ls /dev/hidg*
  ```

### Task 3: Clone repo and install dependencies

- [ ] **Step 1: Clone the repo**
  ```bash
  cd /home/pi
  git clone <your-repo-url> presence
  cd presence
  ```

- [ ] **Step 2: Create virtualenv and install deps**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```

- [ ] **Step 3: Set ANTHROPIC_API_KEY in presence.service**

  Edit `/home/pi/presence/presence.service`:
  ```
  Environment=ANTHROPIC_API_KEY=<your-key>
  ```

- [ ] **Step 4: Install and enable systemd services**
  ```bash
  sudo cp presence-gadget.service /etc/systemd/system/
  sudo cp presence.service /etc/systemd/system/
  sudo cp presence-pwa.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable presence-gadget presence presence-pwa
  sudo systemctl start presence-gadget presence presence-pwa
  ```

- [ ] **Step 5: Verify services are running**
  ```bash
  sudo systemctl status presence
  sudo systemctl status presence-pwa
  journalctl -u presence -f
  ```

  Expected: engine starts, logs activity selection, PWA accessible at `http://<pi-ip>:5000`.

- [ ] **Step 6: Commit any service file changes**

---

## Phase 2: WiFi Captive Portal Onboarding

**Flow:**
1. Pi boots → `presence-firstboot.service` runs `setup/firstboot.sh`
2. `firstboot.sh` checks if WiFi is connected
3. **If connected** → exits cleanly, engine + PWA start normally
4. **If not connected** → starts AP mode (hotspot named `Presence-Setup`), starts portal Flask app
5. User connects phone/laptop to `Presence-Setup` hotspot
6. Any HTTP request → redirected to `http://192.168.42.1` (portal)
7. User enters home WiFi SSID + password → submits
8. Pi saves credentials to `/etc/wpa_supplicant/wpa_supplicant.conf` (or NetworkManager for Trixie), stops AP, reboots
9. Pi reboots onto home WiFi → engine + PWA start normally

### Task 4: Install AP mode dependencies on Pi

```bash
sudo apt install -y hostapd dnsmasq
sudo systemctl disable hostapd dnsmasq  # only run in AP mode, not always
```

### Task 5: Create AP mode config files

- [ ] **Step 1: Create `setup/hostapd.conf`**
  ```
  interface=wlan0
  driver=nl80211
  ssid=Presence-Setup
  hw_mode=g
  channel=7
  wmm_enabled=0
  macaddr_acl=0
  auth_algs=1
  ignore_broadcast_ssid=0
  ```

- [ ] **Step 2: Create `setup/dnsmasq-ap.conf`**
  ```
  interface=wlan0
  dhcp-range=192.168.42.10,192.168.42.50,255.255.255.0,24h
  address=/#/192.168.42.1
  ```
  The `address=/#/192.168.42.1` line redirects all DNS lookups to the Pi — this is what creates the captive portal trigger on iOS/Android.

### Task 6: Create the setup portal Flask app

- [ ] **Step 1: Create `portal/__init__.py`** (empty)

- [ ] **Step 2: Create `portal/app.py`**

  ```python
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
              return render_template("index.html", error="SSID is required.")
          _write_wifi_credentials(ssid, password)
          # Reboot after a short delay so the response can be sent
          subprocess.Popen(["sudo", "shutdown", "-r", "+0"])
          return render_template("index.html", saved=True)

      # Captive portal detection endpoints (iOS, Android, Windows)
      for path in ["/generate_204", "/hotspot-detect.html",
                   "/ncsi.txt", "/connecttest.txt", "/redirect"]:
          app.add_url_rule(path, path, lambda: redirect("/"))

      return app

  def _write_wifi_credentials(ssid: str, password: str) -> None:
      """Write WiFi credentials using nmcli (NetworkManager, Trixie+)."""
      subprocess.run(
          ["sudo", "nmcli", "device", "wifi", "connect", ssid,
           "password", password],
          check=True
      )
  ```

- [ ] **Step 3: Create `portal/templates/index.html`**

  Minimal mobile-first setup page:
  ```html
  <!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Presence Setup</title>
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { font-family: -apple-system, sans-serif; background: #f5f5f5;
             display: flex; align-items: center; justify-content: center;
             min-height: 100vh; padding: 1rem; }
      .card { background: white; border-radius: 12px; padding: 2rem;
              width: 100%; max-width: 400px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
      h1 { font-size: 1.4rem; margin-bottom: 0.5rem; }
      p  { color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }
      label { display: block; font-size: 0.85rem; font-weight: 600;
              margin-bottom: 0.3rem; color: #333; }
      input { width: 100%; padding: 0.75rem; border: 1px solid #ddd;
              border-radius: 8px; font-size: 1rem; margin-bottom: 1rem; }
      button { width: 100%; padding: 0.85rem; background: #1a1a1a;
               color: white; border: none; border-radius: 8px;
               font-size: 1rem; font-weight: 600; cursor: pointer; }
      .error { color: #c00; font-size: 0.85rem; margin-bottom: 1rem; }
      .success { color: #080; font-size: 0.9rem; margin-top: 1rem; text-align: center; }
    </style>
  </head>
  <body>
    <div class="card">
      {% if saved %}
        <h1>Connected!</h1>
        <p class="success">WiFi credentials saved. Presence is rebooting and will join your network in about 60 seconds.</p>
      {% else %}
        <h1>Presence Setup</h1>
        <p>Connect Presence to your WiFi network.</p>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        <form method="POST" action="/save">
          <label for="ssid">WiFi Network Name</label>
          <input type="text" id="ssid" name="ssid" placeholder="MyNetwork" required>
          <label for="password">Password</label>
          <input type="password" id="password" name="password" placeholder="••••••••">
          <button type="submit">Connect</button>
        </form>
      {% endif %}
    </div>
  </body>
  </html>
  ```

- [ ] **Step 4: Create `run_portal.py`**
  ```python
  from portal.app import create_app

  if __name__ == "__main__":
      app = create_app()
      app.run(host="0.0.0.0", port=80)
  ```

### Task 7: Create firstboot.sh

- [ ] **Step 1: Create `setup/firstboot.sh`**

  ```bash
  #!/bin/bash
  # Checks WiFi state on boot. If not connected, enters AP/portal mode.
  # If connected, exits cleanly so normal services start.

  LOGFILE=/var/log/presence-firstboot.log
  exec >> $LOGFILE 2>&1
  echo "$(date): firstboot.sh starting"

  # Give NetworkManager a moment to connect
  sleep 10

  # Check if we have a routable WiFi connection
  if nmcli -t -f STATE general | grep -q "connected"; then
      echo "$(date): WiFi connected, exiting AP mode"
      exit 0
  fi

  echo "$(date): No WiFi connection — entering AP mode"

  # Configure static IP on wlan0 for AP mode
  sudo ip addr flush dev wlan0
  sudo ip addr add 192.168.42.1/24 dev wlan0
  sudo ip link set wlan0 up

  # Start hostapd (access point)
  sudo cp /home/pi/presence/setup/hostapd.conf /etc/hostapd/hostapd.conf
  sudo systemctl start hostapd

  # Start dnsmasq with AP config
  sudo cp /home/pi/presence/setup/dnsmasq-ap.conf /etc/dnsmasq.d/ap.conf
  sudo systemctl start dnsmasq

  # Start the setup portal (port 80 requires root or setcap)
  sudo /home/pi/presence/venv/bin/python /home/pi/presence/run_portal.py &

  echo "$(date): AP mode active — SSID: Presence-Setup, portal at 192.168.42.1"

  # Keep running so systemd doesn't restart us
  wait
  ```

  ```bash
  chmod +x setup/firstboot.sh
  ```

### Task 8: Create systemd service for firstboot

- [ ] **Step 1: Create `presence-firstboot.service`**

  ```ini
  [Unit]
  Description=Presence First Boot WiFi Check
  After=NetworkManager.service
  Before=presence.service presence-pwa.service

  [Service]
  Type=forking
  ExecStart=/home/pi/presence/setup/firstboot.sh
  RemainAfterExit=yes

  [Install]
  WantedBy=multi-user.target
  ```

- [ ] **Step 2: Install and enable**
  ```bash
  sudo cp presence-firstboot.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable presence-firstboot
  ```

- [ ] **Step 3: Update presence.service and presence-pwa.service**

  Add to both `[Unit]` sections:
  ```ini
  After=presence-firstboot.service
  ```

### Task 9: Test full onboarding flow

- [ ] **Step 1: Simulate no-WiFi state**
  ```bash
  sudo nmcli connection delete <your-wifi-connection>
  sudo reboot
  ```

- [ ] **Step 2: On your phone — connect to `Presence-Setup` hotspot**
  - Should get captive portal prompt automatically (iOS/Android)
  - Or open browser to any URL → should redirect to setup page

- [ ] **Step 3: Enter WiFi credentials and submit**
  - Should see "Connected!" confirmation
  - Pi reboots in ~60 seconds

- [ ] **Step 4: Verify Pi rejoins WiFi and services start**
  ```bash
  # After reboot, from your Mac:
  ssh pi@<pi-ip>
  sudo systemctl status presence presence-pwa
  ```

- [ ] **Step 5: Commit everything**
  ```bash
  git add setup/ portal/ presence-firstboot.service presence-gadget.service
  git add presence.service presence-pwa.service run_portal.py requirements.txt
  git commit -m "feat: USB HID gadget setup and WiFi captive portal onboarding"
  ```

---

## Verification

1. `ls /dev/hidg*` returns `/dev/hidg0` and `/dev/hidg1` after boot
2. `sudo systemctl status presence` shows `active (running)`
3. `sudo systemctl status presence-pwa` shows `active (running)`
4. PWA accessible at `http://<pi-ip>:5000` from phone on same network
5. With WiFi credentials removed, Pi creates `Presence-Setup` hotspot
6. Connecting to hotspot and visiting any URL shows the setup page
7. Entering valid credentials reboots Pi onto home WiFi

---

## Notes

- **Trixie uses NetworkManager**, not wpa_supplicant — `nmcli` is the right tool for saving credentials
- **Port 80 requires root** — `run_portal.py` runs as root via sudo in `firstboot.sh`, or use `setcap cap_net_bind_service` on the Python binary
- **hostapd + NetworkManager conflict** — NetworkManager must be told not to manage wlan0 during AP mode; `firstboot.sh` handles this by flushing the interface first
- **`sudo shutdown -r +0` in portal** — the `+0` means "now" but gives Flask time to send the response before the process dies
