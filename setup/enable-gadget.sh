#!/bin/bash
# Sets up USB HID gadget (keyboard + mouse) via ConfigFS
# Must run before the presence engine starts.
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
