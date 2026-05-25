# Robot Bluetooth Controller

Offline control path:

```text
Android phone app
  -> Bluetooth Classic SPP
  -> Raspberry Pi camara.py
  -> Arduino USB serial F/S
  -> L298N motor driver
```

## Raspberry Pi setup

Install Bluetooth and camera dependencies:

```bash
cd /path/to/emba_hw/hw/camera
chmod +x install.sh
./install.sh
```

Pair the phone:

```bash
bluetoothctl
power on
agent on
default-agent
discoverable on
pairable on
```

Start the Pi server:

```bash
cd /path/to/emba_hw/hw
sudo python3 camera/camara.py --arduino-port /dev/ttyACM0
```

The server advertises the standard Bluetooth SPP UUID
`00001101-0000-1000-8000-00805F9B34FB` on RFCOMM channel 1. The install script
starts BlueZ with SDP compatibility mode so Android can connect by UUID; the app
also has a channel 1 fallback for older Raspberry Pi Bluetooth stacks.

## Android app

Open `mobile/android` in Android Studio, build, and install on the phone.

1. Pair the phone with the Raspberry Pi in Android Bluetooth settings.
2. Open the app.
3. Tap `Refresh paired devices`.
4. Tap the Raspberry Pi device.
5. Use `Forward`, `Stop`, and `Photo`.

The selected device MAC is saved. If Bluetooth disconnects, the app keeps trying
to reconnect.
