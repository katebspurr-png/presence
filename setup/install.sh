#!/bin/bash
# One-shot install script. Run from /home/pi/presence after cloning the repo.
# Sets up dependencies, virtualenv, and enables all systemd services.
set -e

echo "==> Installing system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3-pip python3-venv hostapd dnsmasq

echo "==> Creating virtualenv and installing Python deps..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "==> Enabling dwc2 USB gadget overlay..."
if ! grep -q "dtoverlay=dwc2" /boot/firmware/config.txt; then
    echo "dtoverlay=dwc2" | sudo tee -a /boot/firmware/config.txt
fi
if ! grep -q "^dwc2$" /etc/modules; then
    echo "dwc2" | sudo tee -a /etc/modules
fi
if ! grep -q "^libcomposite$" /etc/modules; then
    echo "libcomposite" | sudo tee -a /etc/modules
fi

echo "==> Making setup scripts executable..."
chmod +x setup/enable-gadget.sh setup/firstboot.sh

echo "==> Installing systemd services..."
sudo cp presence-gadget.service    /etc/systemd/system/
sudo cp presence-firstboot.service /etc/systemd/system/
sudo cp presence.service           /etc/systemd/system/
sudo cp presence-pwa.service       /etc/systemd/system/
sudo systemctl daemon-reload

echo "==> Disabling hostapd/dnsmasq auto-start (managed by firstboot.sh)..."
sudo systemctl disable hostapd dnsmasq

echo "==> Enabling presence services..."
sudo systemctl enable presence-gadget presence-firstboot presence presence-pwa

echo ""
echo "Done. Reboot to activate:"
echo "  sudo reboot"
echo ""
echo "After reboot, verify with:"
echo "  ls /dev/hidg*"
echo "  sudo systemctl status presence presence-pwa"
