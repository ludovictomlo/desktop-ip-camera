# TP-Link Tapo C220 — Camera Viewer & Loop Recorder

A Python desktop application that connects to your **TP-Link Tapo C220** camera
via RTSP, shows a live feed, detects motion, and records video clips — automatically
deleting the oldest recordings when your configured storage limit is reached
(loop recording).

---

## Features

- **Live View** — real-time camera feed in a desktop window
- **Motion Detection** — OpenCV-based background subtraction with configurable
  sensitivity, minimum area, and cooldown
- **Automatic Recording** — records video when motion is detected, with
  configurable pre- and post-record buffers
- **Loop Recording** — when the recordings folder exceeds the configured max size,
  the oldest files are automatically deleted
- **Manual Recording** — record on demand with a single click
- **Snapshots** — save a still image from the live feed
- **Settings Persistence** — all settings saved to `config.json`
- **Dark Theme UI** — clean, modern Catppuccin-inspired dark theme

---

## Prerequisites

- **Python 3.10+**
- **TP-Link Tapo C220** camera on the same network as your PC
- Camera credentials (your **Tapo account** email and password, or the camera
  account you set in the Tapo app)

> **How to find your camera's IP:** Open the Tapo app → tap your camera →
> Settings (gear icon) → scroll down to see the IP address. Alternatively, check
> your router's DHCP client list.

---

## Installation

```bash
# Clone and enter the project
cd tplink-camera-app

# Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

---

## Quick Start

```bash
python main.py
```

1. Enter your camera's **IP address**, **username**, and **password** in the
   Settings tab.
2. Select the stream quality:
   - `/stream1` — high quality (1080p/2K depending on model)
   - `/stream2` — lower quality, less bandwidth
3. Click **Connect**.
4. The live feed appears. Motion detection is **on** by default — recordings will
   start automatically when motion is detected.

---

## Configuration

All settings are stored in `config.json` (created on first run). You can edit it
directly or use the in-app Settings panel.

| Setting | Default | Description |
|---|---|---|
| `camera.ip` | `192.168.1.100` | Camera IP address |
| `camera.username` | `admin` | Tapo account / camera username |
| `camera.password` | (empty) | Tapo account / camera password |
| `camera.rtsp_port` | `554` | RTSP port |
| `camera.stream_path` | `/stream1` | Stream quality path |
| `recording.output_folder` | `recordings` | Where recordings are saved |
| `recording.max_storage_mb` | `5000` | Max folder size in MB (loop limit) |
| `recording.segment_duration_seconds` | `60` | Max length of each clip |
| `recording.pre_record_seconds` | `5` | Seconds kept before motion started |
| `recording.post_record_seconds` | `10` | Seconds recorded after motion ends |
| `recording.fps` | `15` | Recording frame rate |
| `detection.sensitivity` | `25` | Motion threshold (lower = more sensitive) |
| `detection.min_area` | `500` | Min pixel area to count as motion |
| `detection.cooldown_seconds` | `3` | Pause before "motion ended" fires |

---

## How Loop Recording Works

1. Motion is detected → recording starts (including the pre-buffer).
2. Motion ends → recording continues for `post_record_seconds`, then stops.
3. Each clip is saved as `motion_YYYYMMDD_HHMMSS.mp4`.
4. A background thread checks the folder every 30 seconds.
5. If total size > `max_storage_mb`, the **oldest** recordings are deleted until
   the folder is back under the limit.

This gives you the same behavior as the Tapo app's loop recording feature, but
the files live on your PC.

---

## Project Structure

```
tplink-camera-app/
├── main.py                 # Entry point
├── config.json             # Runtime config (auto-created)
├── config_default.json     # Default config reference
├── requirements.txt
├── README.md
├── .gitignore
└── app/
    ├── __init__.py
    ├── camera.py           # RTSP stream reader
    ├── config.py           # Config load/save
    ├── detection.py        # Motion detection (OpenCV)
    ├── gui.py              # PyQt6 GUI
    ├── recorder.py         # Video recording manager
    └── storage.py          # Storage monitor & loop cleanup
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Can't connect | Verify IP, credentials, and that the camera is online. Try the RTSP URL in VLC: `rtsp://user:pass@ip:554/stream1` |
| Laggy feed | Use `/stream2` for lower resolution, or reduce the UI update rate |
| No recordings created | Make sure detection is ON and the recordings folder is writable |
| High CPU usage | Lower the stream resolution (`/stream2`) and recording FPS |

---

## License

MIT
