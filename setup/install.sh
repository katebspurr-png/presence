#!/bin/bash
# Run from /home/pi/presence after cloning the repo.
# Sets up the virtualenv, installs deps, and enables all systemd services.
set -e

echo "Installing system dependencies..."
sudo apt update && sudo apt install -y python3-pip python3-venv hostapd dnsmasq

echo "Creating virtualenv and installing Python deps..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "Installing systemd services..."
sudo cp presence-gadget.service    /etc/systemd/system/
sudo cp presence-firstboot.service /etc/systemd/system/
sudo cp presence.service           /etc/systemd/system/
sudo cp presence-pwa.service       /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl disable hostapd dnsmasq  # managed manually in firstboot.sh
sudo systemctl enable presence-gadget presence-firstboot presence presence-pwa

echo "Enabling USB gadget overlay..."
if ! grep -q "dtoverlay=dwc2" /boot/firmware/config.txt; then
    echo "dtoverlay=dwc2" | sudo tee -a /boot/firmware/config.txt
fi
if ! grep -q "^dwc2" /etc/modules; then
    echo "dwc2" | sudo tee -a /etc/modules
fi
if ! grep -q "^libcomposite" /etc/modules; then
    echo "libcomposite" | sudo tee -a /etc/modules
fi

chmod +x setup/enable-gadget.sh setup/firstboot.sh

echo "Installing udev rule for HID device permissions..."
echo 'SUBSYSTEM=="hidraw", KERNEL=="hidg*", MODE="0666"' | sudo tee /etc/udev/rules.d/99-hidg.conf
sudo udevadm control --reload-rules

echo ""
echo "Done. Reboot to activate:"
echo "  sudo reboot"
