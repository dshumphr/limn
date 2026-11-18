# Flashing the limn draw button (Atom VoiceS3R)

One-time setup on the MacBook. After this the device runs standalone on any
5V USB-C charger — no computer needed.

## 1. Install Arduino IDE + boards

1. Install [Arduino IDE 2.x](https://www.arduino.cc/en/software).
2. **File → Preferences → Additional boards manager URLs**, add:
   ```
   https://static-cdn.m5stack.com/resource/arduino/package_m5stack_index.json
   ```
3. **Tools → Board → Boards Manager**: install **M5Stack** (>= 3.2.2).
4. **Tools → Manage Libraries**: install **M5Unified** (>= 0.2.8).

## 2. Configure the sketch

Open `firmware/draw_button/draw_button.ino` and set:

| Define | Value |
|---|---|
| `WIFI_SSID` / `WIFI_PASS` | your 2.4 GHz Wi-Fi (ESP32-S3 is 2.4 GHz only) |
| `SERVER_URL` | `http://10.0.0.180:8000/upload` (archdesk; keep the trailing `/upload`) |

## 3. Select board + port

- **Tools → Board → M5Stack → M5AtomS3R** (the VoiceS3R uses the AtomS3R core).
- Plug the device into the MacBook with a **data** USB-C cable.
- **Tools → Port**: pick `/dev/cu.usbmodem*`.

If the port never appears or upload fails:

1. Hold the side button until the green LED lights, release.
2. When the LED goes dark the device is in download mode — retry the upload.

## 4. Upload and verify

Click **Upload**. On success the device plays two ascending beeps once it
joins Wi-Fi (≤ 20 s). That chime = ready.

Behavior reference:

| Sound | Meaning |
|---|---|
| two ascending beeps | booted, Wi-Fi up, ready |
| short high blip | recording (hold button, speak) |
| short mid blip | recording sent |
| ascending triad | accepted; picture will appear on the TV |
| two low buzzes | error (Wi-Fi drop, server down, < 0.5 s press) |

## 5. Standalone

Unplug from the MacBook, plug into any USB-C phone charger / power bank.
There is no battery — it needs constant 5V, ~0.5 A max. It auto-reconnects
to Wi-Fi after drops and re-announces readiness with the boot chime.

## Wi-Fi note

The ESP32-S3 connects only to **2.4 GHz**. If your router merges bands under
one SSID, that's fine; if it splits 2.4/5 GHz, use the 2.4 GHz SSID.
