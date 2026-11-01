"""
Online Tunnel Runner for the Multi-User AI Recruitment Platform.
Starts the Flask server on 127.0.0.1:5000 and connects a free, secure Cloudflare HTTPS tunnel
so Işıl (in Prague) and Lindsey (in Malta) can access their personal AI recruiters immediately.
"""

import os
import re
import subprocess
import sys
import time

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from job_assistant.engine.db import init_db

CLOUDFLARED_PATH = os.path.join(os.path.dirname(__file__), "data", "cloudflared.exe")
TUNNEL_URL_FILE = os.path.join(os.path.dirname(__file__), "data", "public_tunnel_url.txt")
FLASK_LOG_FILE = os.path.join(os.path.dirname(__file__), "data", "flask_server.log")
CF_LOG_FILE = os.path.join(os.path.dirname(__file__), "data", "cloudflared.log")


def main():
    init_db()
    print("=" * 70)
    print("STARTING MULTI-USER AI RECRUITMENT PLATFORM (ONLINE MODE)")
    print("=" * 70)

    # 1. Start Flask process with output going to log file
    print("1. Launching local application server on http://127.0.0.1:5000...")
    flask_log = open(FLASK_LOG_FILE, "a", encoding="utf-8")
    flask_cmd = [
        sys.executable,
        "-c",
        "import sys, os; sys.path.insert(0, r'" + WORKSPACE_ROOT + "'); from job_assistant.dashboard.app import run_dashboard; run_dashboard(host='127.0.0.1', port=5000)"
    ]
    flask_proc = subprocess.Popen(flask_cmd, stdout=flask_log, stderr=subprocess.STDOUT, text=True)
    time.sleep(2)

    # 2. Start Cloudflared tunnel
    print("2. Launching secure Cloudflare HTTPS tunnel...")
    if not os.path.isfile(CLOUDFLARED_PATH):
        print(f"Error: cloudflared binary not found at {CLOUDFLARED_PATH}")
        sys.exit(1)

    cf_log = open(CF_LOG_FILE, "w", encoding="utf-8")
    cf_cmd = [
        CLOUDFLARED_PATH,
        "tunnel",
        "--url",
        "http://127.0.0.1:5000",
        "--no-autoupdate"
    ]
    cf_proc = subprocess.Popen(cf_cmd, stdout=cf_log, stderr=subprocess.STDOUT, text=True)

    public_url = None
    start_time = time.time()

    # Read cf_log file to extract the trycloudflare.com URL
    while time.time() - start_time < 35:
        time.sleep(0.5)
        try:
            with open(CF_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", content)
                if m:
                    public_url = m.group(0)
                    break
        except Exception:
            pass

    if public_url:
        with open(TUNNEL_URL_FILE, "w", encoding="utf-8") as f:
            f.write(public_url.strip())

        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        desktop_note = os.path.join(desktop_dir, "SEND_TO_ISIL_AND_LINDSEY.txt")
        desktop_url_file = os.path.join(desktop_dir, "Open Job Platform Online.url")

        note_content = (
            "LIVE LINK FOR ISIL & LINDSEY:\n"
            f"{public_url}\n\n"
            "LOGINS:\n"
            "Isil: username: isil | password: Recruit-Isil-QvD5yg-6loM\n"
            "Lindsey: username: lindsey | password: Recruit-Lindsey-3BqvlR4Y38E\n"
            "Justin: username: justin | password: Recruit-Justin-t77j8ou_i9I\n"
        )
        try:
            with open(desktop_note, "w", encoding="utf-8") as f:
                f.write(note_content)
            with open(desktop_url_file, "w", encoding="utf-8") as f:
                f.write(f"[InternetShortcut]\nURL={public_url}\n")
        except Exception:
            pass

        print("\n" + "=" * 70)
        print("PLATFORM IS LIVE ONLINE!")
        print("=" * 70)
        print(f"PUBLIC URL: {public_url}")
        print("Send this link to Isil and Lindsey so they can log in right now!")
        print("=" * 70 + "\n")
    else:
        print("\nWarning: Could not automatically detect tunnel URL yet. Check cloudflared.log.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down online tunnel and server...")
        cf_proc.terminate()
        flask_proc.terminate()
        cf_log.close()
        flask_log.close()


if __name__ == "__main__":
    main()
