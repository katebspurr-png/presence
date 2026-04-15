#!/bin/bash
# Runs on every boot via systemd.
# If WiFi is connected, exits cleanly so normal services start.
# If not connected, enters AP mode and starts the setup portal.

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

# Start the setup portal on port 80
sudo /home/pi/presence/venv/bin/python /home/pi/presence/run_portal.py &

echo "$(date): AP mode active — SSID: Presence-Setup, portal at 192.168.42.1"

# Keep running so systemd doesn't mark us as failed
wait
