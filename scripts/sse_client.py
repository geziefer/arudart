#!/usr/bin/env python3
"""SSE client UI simulating the Flutter app.

Uses OpenCV window for display (same as main app).
Press q or ESC to quit.

Usage:
    PYTHONPATH=. venv/bin/python scripts/sse_client.py
"""
import argparse
import json
import threading
import time
import cv2
import numpy as np
import httpx

dart_lines = ["", "", ""]
total_text = ""
status_text = "Connecting..."
lock = threading.Lock()


def set_dart(n, label, pts):
    global dart_lines, total_text
    with lock:
        if 1 <= n <= 3:
            dart_lines[n - 1] = "Dart %d:  %s  (%d)" % (n, label, pts)
        total_text = ""


def set_total(t):
    global total_text
    with lock:
        total_text = "= %d" % t


def clear_round():
    global dart_lines, total_text, status_text
    with lock:
        dart_lines = ["", "", ""]
        total_text = ""
        status_text = "Waiting for darts..."


def set_status(t):
    global status_text
    with lock:
        status_text = t


def render():
    img = np.zeros((480, 800, 3), dtype=np.uint8)
    with lock:
        darts = list(dart_lines)
        total = total_text
        info = status_text
    y = 80
    for line in darts:
        if line:
            cv2.putText(img, line, (30, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
        y += 70
    cv2.line(img, (30, y), (770, y), (80, 80, 80), 2)
    y += 40
    if total:
        cv2.putText(img, total, (30, y + 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0, 255, 0), 5)
    cv2.putText(img, info, (30, 460),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (128, 128, 128), 1)
    return img


def listen(host, port):
    url = "http://%s:%d/api/events" % (host, port)
    while True:
        try:
            set_status("Connecting to %s:%d..." % (host, port))
            with httpx.stream("GET", url, timeout=None) as r:
                r.raise_for_status()
                set_status("Connected. Waiting for darts...")
                etype, dbuf = None, ""
                for line in r.iter_lines():
                    if line.startswith("event:"):
                        etype = line[6:].strip()
                    elif line.startswith("data:"):
                        dbuf = line[5:].strip()
                    elif line == "" and etype and dbuf:
                        handle(etype, dbuf)
                        etype, dbuf = None, ""
        except Exception as e:
            set_status("Connection lost. Retrying...")
            time.sleep(2)


def handle(etype, raw):
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return
    if etype == "dart_scored":
        set_dart(d.get("dart_number", 0), d.get("label", "?"), d.get("points", 0))
    elif etype == "round_complete":
        set_total(d.get("total", 0))
    elif etype == "darts_removed":
        clear_round()


def main():
    p = argparse.ArgumentParser(description="ARU-DART Score Display")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    cv2.namedWindow("ARU-DART Scores", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("ARU-DART Scores", 800, 480)
    threading.Thread(target=listen, args=(a.host, a.port), daemon=True).start()
    while True:
        img = render()
        cv2.imshow("ARU-DART Scores", img)
        key = cv2.waitKey(50) & 0xFF
        if key == ord("q") or key == 27:
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
