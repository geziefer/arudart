# Raspberry Pi Deployment Guide

## Prerequisites

- Raspberry Pi 4 (4GB+ RAM recommended)
- Raspberry Pi OS (64-bit recommended for better OpenCV performance)
- 3 OV9732 USB cameras connected
- LED ring mounted on board
- Network connection (same WLAN as the tablet running the Flutter app)

## 1. System Setup

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv v4l-utils git
```

## 2. Camera Permissions

```bash
sudo usermod -aG video $USER
# Log out and back in for the group change to take effect
```

Verify cameras are detected:
```bash
v4l2-ctl --list-devices
```
You should see three video devices (e.g., `/dev/video0`, `/dev/video2`, `/dev/video4`).

## 3. Clone and Install

```bash
cd ~
git clone <your-repo-url> arudart
cd arudart
python3 -m venv venv
source venv/bin/activate
pip install opencv-python-headless numpy hypothesis fastapi uvicorn httpx
```

Use `opencv-python-headless` (not `opencv-python`) since the Pi runs headless without a display.

## 4. Camera Control (v4l2)

On Linux, camera control uses `v4l2-ctl` instead of macOS `uvc-util`. The code auto-detects the platform.

Check available camera controls:
```bash
v4l2-ctl -d /dev/video0 --list-ctrls
```

The `config.toml` camera settings may need retuning for the Pi. The exposure/contrast/gamma values use different scales on v4l2 vs uvc-util. Start with the defaults and adjust based on the camera preview:

```bash
# Test with dev-mode to see camera output (requires monitor or X forwarding)
python main.py --dev-mode
```

## 5. Initial Calibration

Calibration must be done once on the Pi since camera positions differ from the Mac setup. You need a monitor connected (or SSH X forwarding) for the initial calibration:

```bash
# Run manual calibration (interactive, needs display)
python main.py --calibrate --dev-mode

# Verify calibration accuracy
python main.py --verify-calibration --dev-mode
```

Calibration files are saved to `calibration/homography_cam*.json`. These persist across restarts.

## 6. Running Headless (Production)

```bash
# Default mode: state machine + API server on port 8000
python main.py

# With image saving for debugging
python main.py --save-images

# Custom API port
python main.py --api-port 9000
```

The application runs headless with no display. All interaction happens via the SSE API on port 8000.

## 7. Auto-Start on Boot

Create a systemd service:

```bash
sudo nano /etc/systemd/system/arudart.service
```

```ini
[Unit]
Description=ARU-DART Scoring System
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/arudart
Environment=PYTHONPATH=/home/pi/arudart
ExecStart=/home/pi/arudart/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable arudart
sudo systemctl start arudart

# Check status
sudo systemctl status arudart

# View logs
journalctl -u arudart -f
```

## 8. Connecting the Flutter App

The Flutter app connects to the Pi's SSE endpoint:
```
http://<pi-ip>:8000/api/events
```

Find the Pi's IP:
```bash
hostname -I
```

Test with the SSE client script from another machine:
```bash
PYTHONPATH=. python scripts/sse_client.py --host <pi-ip>
```

## 9. USB Bandwidth Considerations

Three USB cameras at 800x600 MJPG 25fps is significant bandwidth. On the Pi 4:

- Use the USB 3.0 ports (blue) for cameras
- Spread cameras across different USB controllers if possible
- If you get frame drops, reduce resolution to 640x480 in `config.toml`:
  ```toml
  [camera_settings]
  width = 640
  height = 480
  ```
- MJPG format is essential (uncompressed YUV would exceed USB bandwidth)

## 10. Performance Notes

- Pi 4 quad-core ARM Cortex-A72 at 1.5GHz
- OpenCV operations run ~2-3x slower than on a modern Mac
- Detection pipeline: ~100-200ms per throw (vs ~50-100ms on Mac)
- The 0.5s settling time and 2s cooldown provide ample processing headroom
- Memory usage: ~200-300MB with 3 camera streams
- CPU usage: ~30-50% during active detection, ~5% idle

## 11. Troubleshooting

**Cameras not detected:**
```bash
lsusb  # Check USB devices
v4l2-ctl --list-devices  # Check video devices
```

**Permission denied on /dev/video*:**
```bash
sudo usermod -aG video $USER
# Then log out and back in
```

**Camera settings not applying:**
```bash
# Check if camera supports manual exposure
v4l2-ctl -d /dev/video0 --list-ctrls | grep exposure
# Try setting manually
v4l2-ctl -d /dev/video0 --set-ctrl=exposure_auto=1
v4l2-ctl -d /dev/video0 --set-ctrl=exposure_absolute=370
```

**API not reachable from tablet:**
```bash
# Check if port 8000 is listening
ss -tlnp | grep 8000
# Check firewall
sudo ufw status
sudo ufw allow 8000
```

**High CPU / slow detection:**
- Reduce camera resolution to 640x480
- Increase diff_threshold in config.toml (reduces noise processing)
- Ensure the Pi has adequate cooling (throttling reduces performance)
