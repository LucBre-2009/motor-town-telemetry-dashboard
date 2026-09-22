import socket
import struct
import threading
import time
import math
import json
import sys
import subprocess
import importlib.util
import tkinter as tk
from tkinter import messagebox

# Windows helpers for console detaching and multi-monitor fullscreen.
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes


def detach_console():
    """Close the setup console; minimize it if Windows refuses to detach."""
    if sys.platform != "win32":
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        hwnd = kernel32.GetConsoleWindow()
        if hwnd and kernel32.FreeConsole():
            return
        if hwnd:
            user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            return
    except Exception:
        pass
    try:
        print("\n" + "=" * 60)
        print("DO NOT CLOSE")
        print("THIS IS THE DASHBOARD BACKBONE")
        print("=" * 60)
    except Exception:
        pass


def get_current_monitor_bounds(root):
    """
    Return the monitor rectangle containing the Tk window.
    Uses only the Windows API, so no extra dependency is required.
    """
    if sys.platform != "win32":
        return None

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        hwnd = root.winfo_id()

        MonitorFromWindow = user32.MonitorFromWindow
        MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        MonitorFromWindow.restype = wintypes.HMONITOR

        GetMonitorInfoW = user32.GetMonitorInfoW
        GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
        GetMonitorInfoW.restype = wintypes.BOOL

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        MONITOR_DEFAULTTONEAREST = 2
        monitor = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)

        if not monitor:
            return None

        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)

        if not GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None

        r = info.rcMonitor
        return r.left, r.top, r.right, r.bottom
    except Exception:
        return None


def get_current_monitor_workarea(root):
    if sys.platform != "win32":
        return None
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        hwnd = root.winfo_id()
        monitor = user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)
        if not monitor:
            return None
        class RECT(ctypes.Structure):
            _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG)]
        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom
    except Exception:
        return None
    except Exception:
        return None


def move_window_to_monitor(root):
    """Move the window to the monitor it is currently on before fullscreen."""
    bounds = get_current_monitor_bounds(root)
    if not bounds:
        return None

    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top

    root.attributes("-fullscreen", False)
    root.geometry(f"{width}x{height}+{left}+{top}")
    root.update_idletasks()
    return bounds


APP_NAME = "Motor Town Telemetry"
HOST = "127.0.0.1"
PORT = 33330
PACKET_SIZE = 153
CONFIG_FILE = "motor_town_telemetry_config.json"

# Native-v1 offsets
OFFSETS = {
    "engine_rpm": 108,
    "engine_max_rpm": 112,
    "current_gear": 116,
    "max_forward_gear": 120,
    "speed_kmh": 124,
    "throttle": 128,
    "brake": 132,
    "clutch": 136,
    "steering": 140,
    "handbrake": 144,
    "flags": 145,
    "fuel_ratio": 149,
}

ACCENTS = {
    "Green": "#22c55e",
    "Red": "#ef4444",
    "Blue": "#3b82f6",
    "Purple": "#a855f7",
    "Orange": "#f97316",
}

# Background/appearance themes are independent from the accent color.
APPEARANCES = {
    "Standard": {
        "BG": "#070b12", "PANEL": "#0d1420", "PANEL2": "#111b29",
        "TEXT": "#f3f4f6", "MUTED": "#8b98aa",
    },
    "Dark": {
        "BG": "#050505", "PANEL": "#0b0b0b", "PANEL2": "#151515",
        "TEXT": "#f5f5f5", "MUTED": "#929292",
    },
    "Light": {
        "BG": "#eef2f7", "PANEL": "#ffffff", "PANEL2": "#e2e8f0",
        "TEXT": "#111827", "MUTED": "#64748b",
    },
    "Blue": {
        "BG": "#071426", "PANEL": "#0b1d35", "PANEL2": "#123054",
        "TEXT": "#eff6ff", "MUTED": "#91add0",
    },
    "Red": {
        "BG": "#210b0b", "PANEL": "#351010", "PANEL2": "#4b1717",
        "TEXT": "#fff1f1", "MUTED": "#d6a0a0",
    },
    "Green": {
        "BG": "#07190f", "PANEL": "#0b2617", "PANEL2": "#123b22",
        "TEXT": "#effff4", "MUTED": "#93b8a0",
    },
}

BG = APPEARANCES["Standard"]["BG"]
PANEL = APPEARANCES["Standard"]["PANEL"]
PANEL2 = APPEARANCES["Standard"]["PANEL2"]
TEXT = APPEARANCES["Standard"]["TEXT"]
MUTED = APPEARANCES["Standard"]["MUTED"]

def apply_appearance(name):
    global BG, PANEL, PANEL2, TEXT, MUTED
    palette = APPEARANCES.get(name, APPEARANCES["Standard"])
    BG = palette["BG"]
    PANEL = palette["PANEL"]
    PANEL2 = palette["PANEL2"]
    TEXT = palette["TEXT"]
    MUTED = palette["MUTED"]


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "setup_seen": False,
            "accent": "Green",
            "appearance": "Standard",
            "theme": "Green",
            "host": HOST,
            "port": PORT,
        }


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def ensure_dependencies():
    # V1 intentionally uses only Python standard-library modules.
    # This function is kept so future optional dependencies can use
    # the requested first-start installer flow.
    return True


def first_start_console():
    print("=" * 58)
    print("              MOTOR TOWN TELEMETRY")
    print("=" * 58)
    print()
    print("Welcome!")
    print()
    print("DEPENDENCIES")
    print("  This dashboard installs NOTHING.")
    print("  It uses Python's standard library only:")
    print("    - tkinter      (GUI)")
    print("    - socket       (UDP telemetry)")
    print("    - struct       (Native-v1 packet parsing)")
    print("    - threading    (background telemetry receiver)")
    print("    - json/time/math/os/sys/ctypes")
    print("  No pip packages are required.")
    print()
    print("PYTHON")
    print("  Recommended: Python 3.10 or newer (64-bit on Windows).")
    print("  tkinter must be included with the Python installation.")
    print()
    print("MOTOR TOWN TELEMETRY SETUP")
    print("  1. Start Motor Town.")
    print("  2. Press Escape to open the game menu.")
    print("  3. Go to: Options > Gameplay")
    print("  4. Find: Telemetry Data Output")
    print("  5. Turn Telemetry Data Output ON.")
    print("  6. Set IP:   127.0.0.1")
    print("     Port:     33330")
    print("  7. Enable/select Native-v1 if the game provides a protocol option.")
    print("  8. Start driving or move the vehicle so packets are sent.")
    print()
    print("Nothing is uploaded or sent to an external server.")
    print("The dashboard listens locally on UDP 127.0.0.1:33330.")
    print()
    input("Press Enter to open the dashboard...")


def read_float(packet, offset):
    return struct.unpack_from("<f", packet, offset)[0]


def read_int(packet, offset):
    return struct.unpack_from("<i", packet, offset)[0]


def read_uint(packet, offset):
    return struct.unpack_from("<I", packet, offset)[0]


def read_bool(packet, offset):
    return packet[offset] != 0


def quat_to_euler(x, y, z, w):
    # Returns yaw, pitch, roll in degrees.
    sinr_cosp = 2 * (w * x + y * z)
    cosr_cosp = 1 - 2 * (x * x + y * y)
    roll = math.degrees(math.atan2(sinr_cosp, cosr_cosp))

    sinp = 2 * (w * y - z * x)
    if abs(sinp) >= 1:
        pitch = math.degrees(math.copysign(math.pi / 2, sinp))
    else:
        pitch = math.degrees(math.asin(sinp))

    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = math.degrees(math.atan2(siny_cosp, cosy_cosp))
    return yaw, pitch, roll


def parse_packet(packet):
    if len(packet) != PACKET_SIZE:
        return None

    try:
        px, py, pz = struct.unpack_from("<3f", packet, 32)
        qx, qy, qz, qw = struct.unpack_from("<4f", packet, 44)
        wx, wy, wz = struct.unpack_from("<3f", packet, 60)
        lx, ly, lz = struct.unpack_from("<3f", packet, 72)
        ax, ay, az = struct.unpack_from("<3f", packet, 96)

        yaw, pitch, roll = quat_to_euler(qx, qy, qz, qw)

        flags = read_uint(packet, 145)

        return {
            "position": (px, py, pz),
            "rotation": (qx, qy, qz, qw),
            "velocity_world": (wx, wy, wz),
            "velocity_local": (lx, ly, lz),
            "acceleration": (ax, ay, az),
            "engine_rpm": read_float(packet, 108),
            "engine_max_rpm": read_float(packet, 112),
            "current_gear": read_int(packet, 116),
            "max_forward_gear": read_int(packet, 120),
            "speed_kmh": read_float(packet, 124),
            "throttle": read_float(packet, 128),
            "brake": read_float(packet, 132),
            "clutch": read_float(packet, 136),
            "steering": read_float(packet, 140),
            "handbrake": read_bool(packet, 144),
            "flags": flags,
            "fuel_ratio": read_float(packet, 149),
            "yaw": yaw,
            "pitch": pitch,
            "roll": roll,
            "timestamp": time.time(),
            "raw": packet,
        }
    except (struct.error, ValueError):
        return None


class TelemetryReceiver:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.running = False
        self.thread = None
        self.sock = None
        self.lock = threading.Lock()
        self.data = None
        self.packet_count = 0
        self.bad_packets = 0
        self.bytes_received = 0
        self.last_packet_time = 0.0
        self.rate = 0.0
        self._rate_count = 0
        self._rate_time = time.time()

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass

    def restart(self):
        self.stop()
        time.sleep(0.05)
        self.start()

    def _loop(self):
        while self.running:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.sock.bind((self.host, self.port))
                self.sock.settimeout(1.0)

                while self.running:
                    try:
                        packet, _ = self.sock.recvfrom(4096)
                    except socket.timeout:
                        continue

                    self.bytes_received += len(packet)
                    self._rate_count += 1

                    if len(packet) != PACKET_SIZE:
                        self.bad_packets += 1
                        continue

                    parsed = parse_packet(packet)
                    if parsed is None:
                        self.bad_packets += 1
                        continue

                    with self.lock:
                        self.data = parsed

                    self.packet_count += 1
                    self.last_packet_time = time.time()

                    now = time.time()
                    elapsed = now - self._rate_time
                    if elapsed >= 1.0:
                        self.rate = self._rate_count / elapsed
                        self._rate_count = 0
                        self._rate_time = now

            except OSError:
                if self.running:
                    time.sleep(1)
            finally:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None

    def snapshot(self):
        with self.lock:
            return dict(self.data) if self.data else None


class App:
    def __init__(self, root, receiver, cfg):
        self.root = root
        self.receiver = receiver
        self.cfg = cfg
        self.mode = "USER"
        self.accent_name = cfg.get("accent", cfg.get("theme", "Green"))
        self.appearance_name = cfg.get("appearance", "Standard")
        apply_appearance(self.appearance_name)
        self.accent = ACCENTS.get(self.accent_name, ACCENTS["Green"])
        self.fullscreen = False
        self._fullscreen_geometry = None
        self._fullscreen_overrideredirect = False
        self.page = "Overview"
        self.speed_unit = cfg.get("speed_unit", "km/h")
        self.history = []
        self.max_history = 180
        self.warning_shown = False
        self.g_history = []
        self.g_max = 2.0
        self.long_g_history = []
        self._display_speed = 0.0
        self._display_rpm = 0.0
        self._target_speed = 0.0
        self._target_rpm = 0.0
        self._target_lateral_g = 0.0
        self._target_longitudinal_g = 0.0
        self._display_lateral_g = 0.0
        self._display_longitudinal_g = 0.0
        self._animating_gauge = False
        self._animating_g = False
        self._self_check_active = False
        self._self_check_triggered_for_running = False
        self._startup_self_check_done = False
        self._self_check_actual_states = {}
        self._self_check_smoothing = 0.18
        self._engine_was_running = False
        self._self_check_actual_handbrake = False
        self._self_check_after_id = None
        self._win_fullscreen_style = None
        self._win_fullscreen_exstyle = None
        self._fullscreen_hwnd = None
        # Native-v1 does not expose a reverse-gear-count field. We learn the
        # available reverse range when negative gear values are observed.
        self._observed_reverse_gears = 1
        self._last_vehicle_signature = None
        self._last_vehicle_position = None
        self._last_vehicle_timestamp = None

        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
        self.root.minsize(1100, 700)
        self.root.state("normal")

        self.root.bind_all("<F11>", self.toggle_fullscreen)
        self.root.bind_all("<Escape>", self.leave_fullscreen)

        self.build()
        self._animating_gauge = True
        self.root.after(16, self.animate_gauges)
        self.update_ui()

    def toggle_fullscreen(self, event=None):
        if self.fullscreen:
            self.leave_fullscreen()
            return

        self.root.update_idletasks()
        self._fullscreen_geometry = self.root.geometry()
        bounds = get_current_monitor_bounds(self.root)

        if sys.platform == "win32" and bounds:
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                hwnd = wintypes.HWND(self.root.winfo_id())
                self._fullscreen_hwnd = hwnd

                # Make sure we are operating on the real top-level window.
                GetAncestor = user32.GetAncestor
                GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
                GetAncestor.restype = wintypes.HWND
                root_hwnd = GetAncestor(hwnd, 2)  # GA_ROOT
                if root_hwnd:
                    hwnd = root_hwnd
                    self._fullscreen_hwnd = hwnd

                GWL_STYLE = -16
                GWL_EXSTYLE = -20
                WS_CAPTION = 0x00C00000
                WS_THICKFRAME = 0x00040000
                WS_MINIMIZE = 0x00020000
                WS_MAXIMIZE = 0x00010000
                WS_SYSMENU = 0x00080000
                WS_EX_APPWINDOW = 0x00040000
                WS_EX_TOOLWINDOW = 0x00000080

                old_style = user32.GetWindowLongW(hwnd, GWL_STYLE)
                old_exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                self._win_fullscreen_style = old_style
                self._win_fullscreen_exstyle = old_exstyle

                # Borderless fullscreen, but keep APPWINDOW so Windows still
                # treats it as the dashboard application.
                new_style = old_style & ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZE | WS_MAXIMIZE | WS_SYSMENU)
                new_exstyle = (old_exstyle | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
                user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_exstyle)

                left, top, right, bottom = bounds
                width, height = right - left, bottom - top
                # Put the fullscreen window at the normal top of the Z-order,
                # not TOPMOST. This keeps fullscreen over the taskbar while
                # allowing other applications to come in front normally.
                HWND_TOP = wintypes.HWND(0)
                SWP_FRAMECHANGED = 0x0020
                SWP_SHOWWINDOW = 0x0040

                # Restore first so a previous maximized state cannot fight the
                # monitor coordinates, then apply the exact monitor rectangle.
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetWindowPos(
                    hwnd, HWND_TOP, left, top, width, height,
                    SWP_FRAMECHANGED | SWP_SHOWWINDOW
                )
                user32.ShowWindow(hwnd, 5)  # SW_SHOW
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)

                self.fullscreen = True
                self.root.focus_force()
                return
            except Exception:
                self._win_fullscreen_style = None
                self._win_fullscreen_exstyle = None
                self._fullscreen_hwnd = None
        # Fallback for non-Windows platforms.
        if bounds:
            left, top, right, bottom = bounds
            self.root.attributes("-fullscreen", False)
            self.root.geometry(f"{right-left}x{bottom-top}+{left}+{top}")
        else:
            self.root.attributes("-fullscreen", True)
        self.fullscreen = True

    def leave_fullscreen(self, event=None):
        if not self.fullscreen:
            return

        if sys.platform == "win32" and self._win_fullscreen_style is not None:
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                hwnd = self._fullscreen_hwnd or wintypes.HWND(self.root.winfo_id())
                GWL_STYLE = -16
                GWL_EXSTYLE = -20
                user32.SetWindowLongW(hwnd, GWL_STYLE, self._win_fullscreen_style)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, self._win_fullscreen_exstyle)
                HWND_NOTOPMOST = wintypes.HWND(-2)
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_FRAMECHANGED = 0x0020
                SWP_SHOWWINDOW = 0x0040
                user32.SetWindowPos(
                    hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED | SWP_SHOWWINDOW
                )
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            except Exception:
                pass
            finally:
                self._win_fullscreen_style = None
                self._win_fullscreen_exstyle = None
                self._fullscreen_hwnd = None
        self.root.attributes("-fullscreen", False)
        if self._fullscreen_geometry:
            self.root.geometry(self._fullscreen_geometry)
        self.root.state("zoomed")
        self.root.update_idletasks()
        self.fullscreen = False

    def clear(self):
        for child in self.root.winfo_children():
            child.destroy()

    def label(self, parent, text, size=12, color=TEXT, bold=False, **kwargs):
        return tk.Label(
            parent,
            text=text,
            bg=kwargs.pop("bg", parent.cget("bg")),
            fg=color,
            font=("Segoe UI", size, "bold" if bold else "normal"),
            **kwargs,
        )

    def button(self, parent, text, command, active=False, **kwargs):
        # Allow callers to override the default button padding without
        # passing the same Tkinter option twice.
        padx = kwargs.pop("padx", 14)
        pady = kwargs.pop("pady", 8)
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.accent if active else PANEL2,
            fg="#ffffff",
            activebackground=self.accent,
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=padx,
            pady=pady,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            **kwargs,
        )

    def build(self):
        self.clear()

        header = tk.Frame(self.root, bg=PANEL, height=70)
        header.pack(fill="x")
        header.pack_propagate(False)

        self.label(header, APP_NAME, 19, TEXT, True, bg=PANEL).pack(
            side="left", padx=24
        )

        self.status_label = self.label(
            header, "● WAITING", 10, MUTED, True, bg=PANEL
        )
        self.status_label.pack(side="left", padx=18)

        self.label(header, "BY LucBre", 8, MUTED, True, bg=PANEL).pack(
            side="left", padx=8
        )

        right = tk.Frame(header, bg=PANEL)
        right.pack(side="right", padx=20)

        self.user_mode_button = self.button(
            right, "USER", lambda: self.set_mode("USER"),
            active=self.mode == "USER"
        )
        self.user_mode_button.pack(side="left", padx=3)

        self.expert_mode_button = self.button(
            right, "EXPERT", lambda: self.set_mode("EXPERT"),
            active=self.mode == "EXPERT"
        )
        self.expert_mode_button.pack(side="left", padx=3)

        self.settings_button = self.button(right, "⚙  SETTINGS", self.settings, active=False, padx=16, pady=8)
        self.settings_button.pack(side="left", padx=(8, 0))

        self.close_button = self.button(
            right, "CLOSE DASHBOARD", self.close_dashboard, active=False, padx=16, pady=8
        )
        self.close_button.pack(side="left", padx=(8, 0))

        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True)

        if self.mode == "USER":
            self.build_user()
        else:
            self.build_expert()

        footer = tk.Frame(self.root, bg=PANEL, height=30)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self.footer_label = self.label(
            footer,
            f"Native-v1  •  UDP {self.receiver.host}:{self.receiver.port}  •  153 bytes",
            8, MUTED, bg=PANEL
        )
        self.footer_label.pack(side="left", padx=18)

        self.footer_right = self.label(footer, "", 9, MUTED, bg=PANEL)
        self.footer_right.pack(side="right", padx=18)

    def close_dashboard(self):
        try:
            self.receiver.stop()
        finally:
            self.root.destroy()

    def set_mode(self, mode):
        self.mode = mode
        self.build()
        self._animating_gauge = True
        self.root.after(16, self.animate_gauges)
        self.update_ui()

    def rounded_panel(self, parent, bg=PANEL, radius=16, inset=3):
        """Create a clean rounded panel using a canvas + inset child frame."""
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0)
        inner = tk.Frame(canvas, bg=bg)
        window_id = canvas.create_window(inset, inset, anchor="nw", window=inner)

        def redraw(event=None):
            w = max(2, canvas.winfo_width())
            h = max(2, canvas.winfo_height())
            r = min(radius, w / 2, h / 2)
            canvas.delete("panel_bg")
            # Rounded rectangle made from a center rectangle, side rectangles
            # and four quarter-circles. This keeps the corners visibly rounded
            # without requiring any external GUI library.
            canvas.create_rectangle(r, 0, w-r, h, fill=bg, outline="", tags="panel_bg")
            canvas.create_rectangle(0, r, w, h-r, fill=bg, outline="", tags="panel_bg")
            canvas.create_arc(0, 0, 2*r, 2*r, start=90, extent=90,
                              fill=bg, outline="", tags="panel_bg")
            canvas.create_arc(w-2*r, 0, w, 2*r, start=0, extent=90,
                              fill=bg, outline="", tags="panel_bg")
            canvas.create_arc(0, h-2*r, 2*r, h, start=180, extent=90,
                              fill=bg, outline="", tags="panel_bg")
            canvas.create_arc(w-2*r, h-2*r, w, h, start=270, extent=90,
                              fill=bg, outline="", tags="panel_bg")
            canvas.tag_lower("panel_bg")
            canvas.coords(window_id, inset, inset)
            canvas.itemconfigure(window_id,
                                  width=max(1, w-2*inset),
                                  height=max(1, h-2*inset))

        canvas.bind("<Configure>", redraw)
        return canvas, inner

    def build_user(self):
        content = tk.Frame(self.body, bg=BG)
        content.pack(fill="both", expand=True, padx=24, pady=6)

        # Large primary instruments.
        hero = tk.Frame(content, bg=BG, height=285)
        hero.pack(fill="x", pady=(0, 5))
        hero.pack_propagate(False)
        self.speed_gauge = self.make_gauge(hero, "", 0, 240, self.speed_unit)
        self.speed_gauge.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.rpm_gauge = self.make_gauge(hero, "", 0, 10000, "RPM")
        self.rpm_gauge.pack(side="left", fill="both", expand=True, padx=(6, 0))

        # Compact transmission selector. It supports up to 3 reverse gears and
        # 18 forward gears; the packet exposes the gears as integer positions.
        telemetry = tk.Frame(content, bg=BG, height=72)
        telemetry.pack(fill="x", pady=(0, 8))
        telemetry.pack_propagate(False)

        gear_wrap = tk.Frame(telemetry, bg=BG)
        gear_wrap.pack(expand=True)
        self.label(gear_wrap, "GEAR", 7, MUTED, True, bg=BG).grid(row=0, column=0, rowspan=2, padx=(0, 10))

        self.gear_neutral = tk.Label(gear_wrap, text="N", bg=PANEL2, fg=MUTED,
                                     font=("Segoe UI", 10, "bold"), width=3, height=1,
                                     relief="flat", bd=0, padx=2, pady=4)
        self.gear_neutral.grid(row=0, column=1, padx=2)

        self.gear_reverse_boxes = {}
        for idx in range(1, 4):
            box = tk.Label(gear_wrap, text=("R" if idx == 1 else f"R{idx}"), bg=PANEL2, fg=MUTED,
                           font=("Segoe UI", 9, "bold"), width=3, height=1,
                           relief="flat", bd=0, padx=2, pady=4)
            box.grid(row=0, column=1 + idx, padx=2)
            self.gear_reverse_boxes[idx] = box
            if idx > 1:
                box.grid_remove()

        self.gear_boxes = {}
        for gear in range(1, 19):
            box = tk.Label(gear_wrap, text=str(gear), bg=PANEL2, fg=MUTED,
                           font=("Segoe UI", 9, "bold"), width=3, height=1,
                           relief="flat", bd=0, padx=2, pady=3)
            box.grid(row=1, column=gear, padx=2, pady=(4, 0))
            self.gear_boxes[gear] = box

        self.user_status = self.label(telemetry, "WAITING FOR TELEMETRY", 8, MUTED, True, bg=BG)
        self.user_status.place(relx=1.0, rely=0.5, anchor="e", x=-6)

        # Flags use the same compact card language as the control cards.
        flags_row = tk.Frame(content, bg=BG, height=62)
        flags_row.pack(fill="x", pady=(0, 7))
        flags_row.pack_propagate(False)
        self.user_flags = {}
        for title in ("HANDBRAKE", "LIGHTS", "ABS", "TCS", "CRUISE", "AUTOPILOT"):
            panel, frame = self.rounded_panel(flags_row, PANEL, 14, 2)
            panel.pack(side="left", fill="both", expand=True, padx=3)
            self.label(frame, title, 7, MUTED, True, bg=PANEL).pack(pady=(8, 0))
            val = self.label(frame, "—", 10, TEXT, True, bg=PANEL)
            val.pack(pady=(3, 0))
            self.user_flags[title] = val

        cards = tk.Frame(content, bg=BG, height=68)
        cards.pack(fill="x", pady=(0, 8))
        cards.pack_propagate(False)
        self.user_cards = {}
        for title in ("THROTTLE", "BRAKE", "CLUTCH", "STEERING", "FUEL"):
            panel, frame = self.rounded_panel(cards, PANEL, 14, 2)
            panel.pack(side="left", fill="both", expand=True, padx=3)
            self.label(frame, title, 7, MUTED, True, bg=PANEL).pack(pady=(8, 0))
            val = self.label(frame, "—", 17, TEXT, True, bg=PANEL)
            val.pack(pady=(4, 0))
            self.user_cards[title] = val

        # Bottom area: larger, fully visible G-ball plus a clean dynamics card.
        bottom = tk.Frame(content, bg=BG, height=220)
        bottom.pack(fill="both", expand=True)
        bottom.pack_propagate(False)

        g_panel, g_inner = self.rounded_panel(bottom, PANEL, 18, 3)
        g_panel.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.g_canvas = tk.Canvas(g_inner, bg=PANEL, highlightthickness=0, bd=0)
        self.g_canvas.pack(fill="both", expand=True, padx=5, pady=5)
        self.g_canvas.bind("<Configure>", lambda e: self.draw_g_meter())
        self.draw_g_meter()

        # Bottom-right race timing panel.
        race_panel, race_inner = self.rounded_panel(bottom, PANEL, 18, 3)
        race_panel.pack(side="left", fill="both", expand=True, padx=(5, 0))

        self.race_values = {}
        self.label(race_inner, "RACE TIMING", 11, TEXT, True, bg=PANEL).pack(
            anchor="w", padx=14, pady=(12, 3)
        )
        self.label(race_inner, "RACE DATA • WORK IN PROGRESS", 7, MUTED, True, bg=PANEL).pack(
            anchor="w", padx=14, pady=(0, 7)
        )

        for title in ("TOTAL RACE TIME", "LAP TIME"):
            row = tk.Frame(race_inner, bg=PANEL)
            row.pack(fill="x", padx=14, pady=(2, 5))
            self.label(row, title, 8, MUTED, True, bg=PANEL).pack(side="left")
            value = self.label(row, "--:--.--", 16, TEXT, True, bg=PANEL)
            value.pack(side="right")
            self.race_values[title] = value

        for title in ("CURRENT LAP", "LAP NUMBER", "BEST LAP", "RACE TIME"):
            row = tk.Frame(race_inner, bg=PANEL)
            row.pack(fill="x", padx=14, pady=2)
            self.label(row, title, 8, MUTED, True, bg=PANEL).pack(side="left")
            value = self.label(row, "--", 10, TEXT, True, bg=PANEL)
            value.pack(side="right")
            self.race_values[title] = value

        note = tk.Frame(race_inner, bg=PANEL2, highlightthickness=0, bd=0)
        note.pack(fill="x", padx=14, pady=(12, 10), side="bottom")
        self.label(note, "WIP", 8, self.accent, True, bg=PANEL2).pack(
            anchor="w", padx=10, pady=(8, 2)
        )
        self.label(
            note,
            "Lap and race timing are work in progress.\n"
            "Native-v1 does not currently provide lap timing data.",
            8, MUTED, False, bg=PANEL2, justify="left"
        ).pack(anchor="w", padx=10, pady=(0, 9))

    def make_gauge(self, parent, title, minimum, maximum, unit):
        outer, frame = self.rounded_panel(parent, PANEL, 18, 2)
        canvas = tk.Canvas(frame, bg=PANEL, highlightthickness=0, bd=0, height=300)
        canvas.pack(fill="both", expand=True)
        outer._gauge_canvas = canvas
        outer._gauge_title = title
        outer._gauge_min = minimum
        outer._gauge_max = maximum
        outer._gauge_unit = unit
        outer._gauge_value = minimum
        canvas.bind("<Configure>", lambda e, f=outer: self.draw_gauge(f))
        self.draw_gauge(outer)
        return outer

    def draw_gauge(self, frame):
        c = frame._gauge_canvas
        c.delete("all")
        w = max(c.winfo_width(), 10)
        h = max(c.winfo_height(), 10)
        cx, cy = w / 2, h * 0.57
        radius = min(w * 0.39, h * 0.49)

        # Negative extent = clockwise in Tk's canvas coordinate system.
        start, extent = 225, -270

        c.create_arc(cx-radius-7, cy-radius-7, cx+radius+7, cy+radius+7,
                     start=start, extent=extent, style="arc", width=2,
                     outline=PANEL2)
        c.create_arc(cx-radius, cy-radius, cx+radius, cy+radius,
                     start=start, extent=extent, style="arc", width=15,
                     outline=PANEL2)
        c.create_arc(cx-radius, cy-radius, cx+radius, cy+radius,
                     start=start, extent=extent, style="arc", width=4,
                     outline=self.accent)

        for i in range(21):
            frac = i / 20
            angle = math.radians(start + extent * frac)
            major = i % 2 == 0
            r1 = radius - (29 if major else 22)
            r2 = radius - 7
            x1, y1 = cx+r1*math.cos(angle), cy-r1*math.sin(angle)
            x2, y2 = cx+r2*math.cos(angle), cy-r2*math.sin(angle)
            c.create_line(x1, y1, x2, y2, fill=TEXT if major else MUTED,
                          width=2 if major else 1)
            if major:
                value = frame._gauge_min + (frame._gauge_max-frame._gauge_min)*frac
                tx = cx + (radius-49)*math.cos(angle)
                ty = cy - (radius-49)*math.sin(angle)
                text = f"{value/1000:.0f}k" if frame._gauge_title == "RPM" else f"{value:.0f}"
                c.create_text(tx, ty, text=text, fill=MUTED,
                              font=("Segoe UI", 8, "bold"))

        # The User Mode gauges intentionally have no large title above them.
        # The unit remains centered inside the instrument for a clean look.
        if frame._gauge_title:
            c.create_text(cx, 15, text=frame._gauge_title, fill=TEXT,
                          font=("Segoe UI", 14, "bold"))
        c.create_text(cx, cy - radius * 0.43, text=frame._gauge_unit, fill=self.accent,
                      font=("Segoe UI", 8, "bold"))

        value = max(frame._gauge_min, min(frame._gauge_max, frame._gauge_value))
        frac = (value-frame._gauge_min)/(frame._gauge_max-frame._gauge_min or 1)
        angle = math.radians(start + extent*frac)
        tip_r = radius - 22
        tx, ty = cx + tip_r*math.cos(angle), cy - tip_r*math.sin(angle)
        c.create_line(cx, cy, tx, ty, fill=self.accent, width=4, capstyle="round")
        c.create_oval(cx-6, cy-6, cx+6, cy+6, fill=self.accent, outline="")
        c.create_text(cx, cy+radius*0.12, text=f"{value:.0f}", fill=TEXT,
                      font=("Segoe UI", 18, "bold"))

    def set_gauge_value(self, gauge, value):
        gauge._gauge_value = value
        self.draw_gauge(gauge)

    def animate_gauges(self):
        """Continuously animate the two main gauges at the UI frame rate."""
        if not hasattr(self, "speed_gauge") or not self.root.winfo_exists():
            self._animating_gauge = False
            return

        for gauge, attr, target in (
            (self.speed_gauge, "_display_speed", self._target_speed),
            (self.rpm_gauge, "_display_rpm", self._target_rpm),
        ):
            current = getattr(self, attr)
            # Exponential smoothing; the display keeps moving even when the
            # telemetry packet rate is much lower than the UI frame rate.
            current += (target - current) * self._self_check_smoothing
            if abs(target - current) < 0.02:
                current = target
            setattr(self, attr, current)
            gauge._gauge_value = current
            self.draw_gauge(gauge)

        self._animating_gauge = True
        self.root.after(16, self.animate_gauges)

    def animate_g_meter(self):
        """Continuously animate the G-force display at the UI frame rate.

        Keep this loop alive even when the current G value is zero. Telemetry
        updates arrive independently, so stopping the animation when the
        target happens to be zero can make the meter appear frozen later.
        """
        if not hasattr(self, "g_canvas") or not self.root.winfo_exists():
            self._animating_g = False
            return

        for attr, target in (("_display_lateral_g", self._target_lateral_g),
                             ("_display_longitudinal_g", self._target_longitudinal_g)):
            current = getattr(self, attr)
            current += (target - current) * 0.16
            if abs(target - current) < 0.002:
                current = target
            setattr(self, attr, current)

        self.g_history.append(self._display_lateral_g)
        self.long_g_history.append(self._display_longitudinal_g)
        self.g_history = self.g_history[-24:]
        self.long_g_history = self.long_g_history[-24:]
        self.draw_g_meter()

        self._animating_g = True
        self.root.after(16, self.animate_g_meter)

    def draw_g_meter(self):
        if not hasattr(self, "g_canvas"):
            return
        c = self.g_canvas
        c.delete("all")
        w = max(c.winfo_width(), 10)
        h = max(c.winfo_height(), 10)
        cx, cy = w * 0.5, h * 0.53
        # Keep the complete instrument inside the card while making it as
        # large as the available height allows.
        radius = min(w * 0.34, h * 0.34)

        c.create_text(16, 10, anchor="nw", text="G-FORCE",
                      fill=TEXT, font=("Segoe UI", 11, "bold"))
        c.create_text(w-16, 10, anchor="ne", text="2-AXIS ACCELEROMETER",
                      fill=MUTED, font=("Segoe UI", 7, "bold"))

        # Outer instrument rings.
        c.create_oval(cx-radius-8, cy-radius-8, cx+radius+8, cy+radius+8,
                      outline=PANEL2, width=5)
        c.create_oval(cx-radius, cy-radius, cx+radius, cy+radius,
                      outline=MUTED, width=1)
        c.create_oval(cx-radius*0.66, cy-radius*0.66,
                      cx+radius*0.66, cy+radius*0.66,
                      outline=PANEL2, width=1)

        # Crosshair and cardinal direction marks.
        c.create_line(cx-radius, cy, cx+radius, cy, fill=PANEL2, width=2)
        c.create_line(cx, cy-radius, cx, cy+radius, fill=PANEL2, width=2)
        for frac in (-1, -0.5, 0.5, 1):
            x = cx + frac * radius
            y = cy - frac * radius
            c.create_line(x, cy-4, x, cy+4, fill=MUTED, width=1)
            c.create_line(cx-4, y, cx+4, y, fill=MUTED, width=1)

        c.create_text(cx, cy-radius-13, text="BRAKE / FWD",
                      fill=MUTED, font=("Segoe UI", 7, "bold"))
        c.create_text(cx, cy+radius+13, text="ACCEL / BACK",
                      fill=MUTED, font=("Segoe UI", 7, "bold"))
        c.create_text(cx-radius-28, cy, text="LEFT", fill=MUTED,
                      font=("Segoe UI", 7, "bold"))
        c.create_text(cx+radius+28, cy, text="RIGHT", fill=MUTED,
                      font=("Segoe UI", 7, "bold"))

        # Local X = lateral, local Z = longitudinal. The longitudinal sign is
        # inverted so acceleration sends the ball backward and braking forward,
        # matching the behavior of a real vehicle-mounted G-meter.
        lateral = self._display_lateral_g
        longitudinal = self._display_longitudinal_g
        lateral = max(-self.g_max, min(self.g_max, lateral))
        longitudinal = max(-self.g_max, min(self.g_max, longitudinal))
        px = cx + (lateral / self.g_max) * radius * 0.72
        py = cy - (longitudinal / self.g_max) * radius * 0.72

        # Trail follows the ball's recent path.
        hist = min(len(self.g_history), len(self.long_g_history), 40)
        if hist:
            for i in range(hist):
                gx = self.g_history[-hist+i]
                gz = self.long_g_history[-hist+i]
                tx = cx + max(-1, min(1, gx/self.g_max)) * radius * 0.72
                ty = cy - max(-1, min(1, gz/self.g_max)) * radius * 0.72
                if i > 0:
                    pgx = self.g_history[-hist+i-1]
                    pgz = self.long_g_history[-hist+i-1]
                    ptx = cx + max(-1, min(1, pgx/self.g_max)) * radius * 0.72
                    pty = cy - max(-1, min(1, pgz/self.g_max)) * radius * 0.72
                    c.create_line(ptx, pty, tx, ty, fill=self.accent,
                                  width=2, capstyle="round")
                if i >= hist - 7:
                    r = 2 + (i-(hist-7)) * 0.7
                    c.create_oval(tx-r, ty-r, tx+r, ty+r,
                                  fill=self.accent, outline="")

        c.create_oval(px-10, py-10, px+10, py+10,
                      fill=self.accent, outline=TEXT, width=2)
        c.create_oval(px-3, py-3, px+3, py+3, fill=TEXT, outline="")
        c.create_text(px, py-19, text=f"{math.hypot(lateral, longitudinal):.2f} G",
                      fill=TEXT, font=("Segoe UI", 9, "bold"))
        c.create_text(cx, h-12, text=f"LATERAL {lateral:+.2f} G    •    LONGITUDINAL {longitudinal:+.2f} G",
                      fill=MUTED, font=("Segoe UI", 8, "bold"))

    def build_expert(self):
        outer = tk.Frame(self.body, bg=BG)
        outer.pack(fill="both", expand=True, padx=24, pady=20)

        left = tk.Frame(outer, bg=BG, width=320)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        self.expert_nav = {}
        for name in [
            "Overview", "Engine", "Movement", "Controls",
            "Position", "Flags", "Raw Data"
        ]:
            b = self.button(
                left, name, lambda n=name: self.set_page(n),
                active=self.page == name
            )
            b.pack(fill="x", pady=3)
            self.expert_nav[name] = b

        right = tk.Frame(outer, bg=PANEL, padx=24, pady=22)
        right.pack(side="left", fill="both", expand=True)

        self.expert_title = self.label(
            right, self.page.upper(), 18, TEXT, True, bg=PANEL
        )
        self.expert_title.pack(anchor="w")

        self.expert_text = tk.Text(
            right,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            font=("Consolas", 11),
            padx=10,
            pady=20,
        )
        self.expert_text.pack(fill="both", expand=True)

        self.expert_text.tag_configure("accent", foreground=self.accent)
        self.expert_text.tag_configure("muted", foreground=MUTED)

    def set_page(self, page):
        self.page = page
        self.build()
        self._animating_gauge = True
        self.root.after(16, self.animate_gauges)
        self.update_ui()

    def settings(self):
        win = tk.Toplevel(self.root)
        win.title("Telemetry Settings")
        win.configure(bg=PANEL)
        win.geometry("640x700")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        self.label(win, "⚙  SETTINGS", 20, TEXT, True, bg=PANEL).pack(
            anchor="w", padx=28, pady=(22, 4)
        )
        self.label(
            win, "Dashboard appearance and telemetry connection", 10, MUTED, bg=PANEL
        ).pack(anchor="w", padx=28, pady=(0, 18))

        appearance = tk.Frame(win, bg=PANEL2)
        appearance.pack(fill="x", padx=24, pady=6)
        self.label(appearance, "APPEARANCE", 10, self.accent, True, bg=PANEL2).pack(
            anchor="w", padx=18, pady=(14, 8)
        )

        bg_row = tk.Frame(appearance, bg=PANEL2)
        bg_row.pack(fill="x", padx=18, pady=5)
        self.label(bg_row, "Background", 11, MUTED, True, bg=PANEL2).pack(side="left")
        appearance_var = tk.StringVar(value=self.appearance_name)
        bg_menu = tk.OptionMenu(bg_row, appearance_var, *APPEARANCES.keys())
        bg_menu.configure(bg=BG, fg=TEXT, activebackground=self.accent,
                          activeforeground=TEXT, relief="flat", bd=0, highlightthickness=0)
        bg_menu["menu"].configure(bg=PANEL2, fg=TEXT)
        bg_menu.pack(side="right")

        accent_row = tk.Frame(appearance, bg=PANEL2)
        accent_row.pack(fill="x", padx=18, pady=5)
        self.label(accent_row, "Accent color", 11, MUTED, True, bg=PANEL2).pack(side="left")
        accent_var = tk.StringVar(value=self.accent_name)
        accent_menu = tk.OptionMenu(accent_row, accent_var, *ACCENTS.keys())
        accent_menu.configure(bg=BG, fg=TEXT, activebackground=self.accent,
                              activeforeground=TEXT, relief="flat", bd=0, highlightthickness=0)
        accent_menu["menu"].configure(bg=PANEL2, fg=TEXT)
        accent_menu.pack(side="right")

        unit_row = tk.Frame(appearance, bg=PANEL2)
        unit_row.pack(fill="x", padx=18, pady=(2, 14))
        self.label(unit_row, "Speed unit", 11, MUTED, True, bg=PANEL2).pack(side="left")
        unit_var = tk.StringVar(value=self.speed_unit)
        unit_menu = tk.OptionMenu(unit_row, unit_var, "km/h", "mph")
        unit_menu.configure(bg=BG, fg=TEXT, activebackground=self.accent,
                            activeforeground=TEXT, relief="flat", bd=0, highlightthickness=0)
        unit_menu["menu"].configure(bg=PANEL2, fg=TEXT)
        unit_menu.pack(side="right")

        # Telemetry connection
        connection = tk.Frame(win, bg=PANEL2)
        connection.pack(fill="x", padx=24, pady=10)
        self.label(connection, "TELEMETRY CONNECTION", 10, self.accent, True, bg=PANEL2).pack(
            anchor="w", padx=18, pady=(14, 3)
        )
        self.label(
            connection,
            "Change these values to match Motor Town's Telemetry Data Output settings.",
            9, MUTED, bg=PANEL2
        ).pack(anchor="w", padx=18, pady=(0, 10))

        host_row = tk.Frame(connection, bg=PANEL2)
        host_row.pack(fill="x", padx=18, pady=5)
        self.label(host_row, "IP address", 11, MUTED, True, bg=PANEL2).pack(side="left")
        host_var = tk.StringVar(value=str(self.cfg.get("host", HOST)))
        host_entry = tk.Entry(
            host_row, textvariable=host_var, width=22,
            bg=BG, fg=TEXT, insertbackground=TEXT,
            relief="flat", bd=0, font=("Consolas", 11)
        )
        host_entry.pack(side="right", ipady=7, padx=(20, 0))

        port_row = tk.Frame(connection, bg=PANEL2)
        port_row.pack(fill="x", padx=18, pady=(5, 14))
        self.label(port_row, "UDP port", 11, MUTED, True, bg=PANEL2).pack(side="left")
        port_var = tk.StringVar(value=str(self.cfg.get("port", PORT)))
        port_entry = tk.Entry(
            port_row, textvariable=port_var, width=22,
            bg=BG, fg=TEXT, insertbackground=TEXT,
            relief="flat", bd=0, font=("Consolas", 11)
        )
        port_entry.pack(side="right", ipady=7, padx=(20, 0))

        status_var = tk.StringVar(value="")
        status_label = self.label(win, "", 9, MUTED, bg=PANEL)
        status_label.pack(anchor="w", padx=28, pady=(6, 0))

        def apply():
            new_host = host_var.get().strip()
            new_port_text = port_var.get().strip()

            if not new_host:
                status_label.config(text="IP address cannot be empty.", fg="#ef4444")
                return
            try:
                new_port = int(new_port_text)
                if not 1 <= new_port <= 65535:
                    raise ValueError
            except ValueError:
                status_label.config(text="UDP port must be a number between 1 and 65535.", fg="#ef4444")
                return

            self.accent_name = accent_var.get()
            self.appearance_name = appearance_var.get()
            self.accent = ACCENTS[self.accent_name]
            apply_appearance(self.appearance_name)
            self.speed_unit = unit_var.get()
            self.cfg["speed_unit"] = self.speed_unit
            self.cfg["accent"] = self.accent_name
            self.cfg["theme"] = self.accent_name
            self.cfg["appearance"] = self.appearance_name
            self.cfg["host"] = new_host
            self.cfg["port"] = new_port
            save_config(self.cfg)

            # Apply the new telemetry endpoint immediately.
            self.receiver.host = new_host
            self.receiver.port = new_port
            self.receiver.restart()

            win.destroy()
            self.build()
            self.update_ui()

        self.button(win, "APPLY & RESTART TELEMETRY", apply, active=True).pack(
            anchor="e", padx=28, pady=18
        )

    def show_tutorial(self):
        steps = [
            ("WELCOME", "This quick tour shows you where the important dashboard controls are."),
            ("SPEED & RPM", "The two large gauges at the top show your current vehicle speed and engine RPM."),
            ("GEAR", "The gear strip below the gauges shows the current gear and available forward/reverse positions."),
            ("VEHICLE INPUTS", "Throttle, Brake, Clutch, Steering and Fuel are shown across the middle of User Mode."),
            ("VEHICLE STATUS", "Handbrake, Headlights, ABS, TCS and Cruise Control (Autopilot is not supported by Motor Town yet) are shown in the status cards."),
            ("G-FORCE", "The circular G-force meter shows lateral and longitudinal acceleration."),
            ("USER / EXPERT", "Use the buttons in the top-right to switch between the clean User Mode and detailed Expert Mode."),
            ("⚙ SETTINGS", "The clearly marked Settings button in the top-right opens telemetry connection, background, accent and speed-unit options."),
            ("YOU'RE READY", "Start Motor Town with Native-v1 telemetry enabled, then start driving. The dashboard will switch to LIVE automatically."),
        ]
        win = tk.Toplevel(self.root)
        win.title("Motor Town Dashboard Tour")
        win.configure(bg=PANEL)
        win.geometry("680x420")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        index = 0
        title = self.label(win, steps[0][0], 22, self.accent, True, bg=PANEL)
        title.pack(pady=(38, 12))
        body = self.label(win, steps[0][1], 13, TEXT, bg=PANEL, justify="center", wraplength=560)
        body.pack(fill="x", padx=50, pady=15)
        where = self.label(win, "", 10, MUTED, bg=PANEL, justify="center", wraplength=560)
        where.pack(fill="x", padx=50, pady=8)
        progress = self.label(win, "1 / 9", 9, MUTED, bg=PANEL)
        progress.pack(pady=8)

        controls = tk.Frame(win, bg=PANEL)
        controls.pack(side="bottom", fill="x", padx=28, pady=24)
        prev = self.button(controls, "BACK", lambda: None, active=False)
        prev.pack(side="left")
        next_btn = self.button(controls, "NEXT", lambda: None, active=True)
        next_btn.pack(side="right")

        locations = [
            "Dashboard overview", "Top of the dashboard", "Below the main gauges",
            "Middle of User Mode", "Status row", "Vehicle Dynamics panel",
            "Top-right mode buttons", "Top-right ⚙ SETTINGS button", "Live dashboard"
        ]
        def render():
            title.config(text=steps[index][0], fg=self.accent)
            body.config(text=steps[index][1])
            where.config(text="LOCATION  •  " + locations[index])
            progress.config(text=f"{index + 1} / {len(steps)}")
            prev.config(state="normal" if index else "disabled")
            next_btn.config(text="FINISH" if index == len(steps) - 1 else "NEXT")
        def back():
            nonlocal index
            if index > 0:
                index -= 1
                render()
        def forward():
            nonlocal index
            if index < len(steps) - 1:
                index += 1
                render()
            else:
                self.cfg["tutorial_seen"] = True
                save_config(self.cfg)
                win.destroy()
        prev.config(command=back)
        next_btn.config(command=forward)
        render()

    def show_setup(self):
        win = tk.Toplevel(self.root)
        win.title("Motor Town Telemetry Setup")
        win.configure(bg=PANEL)
        win.geometry("720x620")
        win.transient(self.root)

        self.label(win, APP_NAME, 20, TEXT, True, bg=PANEL).pack(
            pady=(28, 4)
        )
        self.label(win, "FIRST START SETUP", 11, self.accent, True, bg=PANEL).pack()

        text = (
            "\nBefore using the dashboard, enable Motor Town telemetry.\n\n"
            "1. Start Motor Town.\n\n"
            "2. Open the game's telemetry / Data Output settings.\n\n"
            "3. Enable Native-v1 telemetry.\n\n"
            "4. Set the destination to:\n\n"
            "      IP:    127.0.0.1\n"
            "      Port:  33330\n\n"
            "5. Start driving or move the vehicle.\n\n"
            "The dashboard automatically listens for the 153-byte\n"
            "Native-v1 UDP packets and switches to LIVE when they arrive.\n\n"
            "If no packets arrive, the dashboard will remain in WAITING\n"
            "mode and show the connection information at the bottom."
        )

        self.label(
            win, text, 12, TEXT, bg=PANEL, justify="left",
            anchor="w"
        ).pack(fill="both", expand=True, padx=55, pady=10)

        def close():
            self.cfg["setup_seen"] = True
            save_config(self.cfg)
            win.destroy()

        self.button(win, "GOT IT", close, active=True).pack(pady=25)

    def start_self_check(self, data):
        """Run the startup instrument/warning-light self-check exactly once."""
        if self._self_check_active or self._startup_self_check_done:
            return

        self._startup_self_check_done = True
        self._self_check_active = True
        self._self_check_actual_handbrake = bool(data["handbrake"])
        flags = data["flags"]
        self._self_check_actual_states = {
            "HANDBRAKE": bool(data["handbrake"]),
            "LIGHTS": bool(flags & 0x08),
            "ABS": bool(flags & 0x10),
            "TCS": bool(flags & 0x20),
            "CRUISE": bool(flags & 0x40),
        }

        # Slow the gauge animation down during the sweep so it feels like a
        # real instrument self-test rather than an instant jump.
        self._self_check_smoothing = 0.055
        self._target_speed = self.speed_gauge._gauge_max
        self._target_rpm = self.rpm_gauge._gauge_max

        # Simulate the startup warning-light check.
        for name in ("HANDBRAKE", "LIGHTS", "ABS", "TCS"):
            self.user_flags[name].config(text="ACTIVE", fg=self.accent)

        if self._self_check_after_id:
            try:
                self.root.after_cancel(self._self_check_after_id)
            except Exception:
                pass

        # Hold the needles at maximum briefly, then make the return sweep.
        self._self_check_after_id = self.root.after(2200, self._self_check_return_phase)

    def _self_check_return_phase(self):
        if not self._self_check_active:
            return

        self._target_speed = 0.0
        self._target_rpm = 0.0
        for name in ("HANDBRAKE", "LIGHTS", "ABS", "TCS"):
            active = self._self_check_actual_states.get(name, False)
            self.user_flags[name].config(
                text="OFF" if not active else "ACTIVE",
                fg=self.accent if active else MUTED
            )

        # Let the needles take their time returning to zero before handing
        # control back to live telemetry.
        self._self_check_after_id = self.root.after(2200, self._finish_self_check)

    def _finish_self_check(self):
        if not self._self_check_active:
            return

        self._self_check_active = False
        self._self_check_after_id = None
        self._self_check_smoothing = 0.18

        for name, active in self._self_check_actual_states.items():
            self.user_flags[name].config(
                text="ACTIVE" if active else "OFF",
                fg=self.accent if active else MUTED
            )

        # Return to the live telemetry values after the complete sweep.
        data = self.receiver.snapshot()
        if data:
            speed = data["speed_kmh"] if self.speed_unit == "km/h" else data["speed_kmh"] * 0.621371
            self._target_speed = speed
            self._target_rpm = data["engine_rpm"]

    def update_ui(self):
        if hasattr(self, "footer_label"):
            self.footer_label.config(
                text=f"Native-v1  •  UDP {self.receiver.host}:{self.receiver.port}  •  153 bytes"
            )
        data = self.receiver.snapshot()

        connected = (
            data is not None and
            time.time() - self.receiver.last_packet_time < 2.0
        )

        if connected:
            self.status_label.config(text="● LIVE", fg=self.accent)
        else:
            self.status_label.config(text="● WAITING", fg=MUTED)

        if self.mode == "USER":
            self.update_user(data, connected)
        else:
            self.update_expert(data, connected)

        self.root.after(100, self.update_ui)

    def update_user(self, data, connected):
        if not hasattr(self, "speed_gauge"):
            return

        if not data:
            self._observed_reverse_gears = 1
            self._last_vehicle_signature = None
            self._last_vehicle_position = None
            self._last_vehicle_timestamp = None
            self._target_speed = 0.0
            self._target_rpm = 0.0
            self._engine_was_running = False
            if self._self_check_active:
                self._self_check_active = False
                self._self_check_after_id = None
            if not self._animating_gauge:
                self._animating_gauge = True
                self.root.after(0, self.animate_gauges)
            for box in self.gear_boxes.values():
                box.config(bg=PANEL2, fg=MUTED)
            for box in self.gear_reverse_boxes.values():
                box.config(bg=PANEL2, fg=MUTED)
            self.gear_neutral.config(bg=PANEL2, fg=MUTED)
            for v in self.user_cards.values():
                v.config(text="—")
            for v in self.user_flags.values():
                v.config(text="—", fg=TEXT)
            self.user_status.config(text="WAITING FOR TELEMETRY", fg=MUTED)
            self._target_lateral_g = 0.0
            self._target_longitudinal_g = 0.0
            self.g_history.clear()
            self.long_g_history.clear()
            if not self._animating_g:
                self._animating_g = True
                self.root.after(0, self.animate_g_meter)
            for v in self.race_values.values():
                v.config(text="—")
            return

        speed_kmh = data["speed_kmh"]
        speed = speed_kmh if self.speed_unit == "km/h" else speed_kmh * 0.621371
        max_speed = 240 if self.speed_unit == "km/h" else 150
        self.speed_gauge._gauge_max = max_speed
        self.speed_gauge._gauge_unit = self.speed_unit

        # The self-check belongs to dashboard startup, not to an RPM transition.
        # It is triggered once when the first valid telemetry packet arrives.
        if not self._startup_self_check_done:
            self.start_self_check(data)

        if not self._self_check_active:
            self._target_speed = speed
            self._target_rpm = data["engine_rpm"]
        if not self._animating_gauge:
            self._animating_gauge = True
            self.root.after(0, self.animate_gauges)

        current_gear = int(data["current_gear"])
        max_gear = max(0, min(18, int(data["max_forward_gear"])))
        reverse_active = bool(data["flags"] & 0x04) or current_gear < 0

        # Reverse-gear discovery is vehicle-specific. Native-v1 does not
        # provide a reverse-count field, so reset the learned count whenever
        # the telemetry indicates that the current vehicle has disappeared,
        # the transmission signature changes, or the vehicle teleports/spawns
        # at a new location. This prevents R2/R3 from leaking into a new car.
        vehicle_present = bool(data["flags"] & 0x02)
        signature = (max_gear, round(float(data["engine_max_rpm"]), 1))
        pos = data["position"]
        reset_reverse = not vehicle_present
        if self._last_vehicle_signature is not None and signature != self._last_vehicle_signature:
            reset_reverse = True
        if self._last_vehicle_position is not None:
            dx = pos[0] - self._last_vehicle_position[0]
            dy = pos[1] - self._last_vehicle_position[1]
            dz = pos[2] - self._last_vehicle_position[2]
            # Position is in centimetres. A large jump is a strong spawn/
            # vehicle-switch signal and is not normal driving movement.
            if math.sqrt(dx*dx + dy*dy + dz*dz) > 1500.0:
                reset_reverse = True
        if reset_reverse:
            self._observed_reverse_gears = 1
        self._last_vehicle_signature = signature
        self._last_vehicle_position = pos
        self._last_vehicle_timestamp = data["timestamp"]

        for gear, box in self.gear_boxes.items():
            if gear <= max_gear:
                box.config(bg=self.accent if current_gear == gear else PANEL2,
                           fg="#ffffff" if current_gear == gear else MUTED)
            else:
                box.config(bg=BG, fg="#334155")

        self.gear_neutral.config(
            bg=self.accent if current_gear == 0 and not reverse_active else PANEL2,
            fg="#ffffff" if current_gear == 0 and not reverse_active else MUTED
        )

        # Native-v1 has no "maximum reverse gear" field. The only reliable
        # discovery signal is the negative current_gear value itself.
        # Therefore R2/R3 can be revealed automatically as soon as the game
        # reports -2/-3; before that, showing them as available would be a
        # guess. R1 is displayed simply as "R" for a one-reverse transmission.
        if current_gear < 0:
            self._observed_reverse_gears = max(
                self._observed_reverse_gears,
                min(3, abs(current_gear))
            )

        reverse_count = max(1, min(3, self._observed_reverse_gears))
        for rev, box in self.gear_reverse_boxes.items():
            # Do not reserve/show undiscovered reverse gears. This prevents
            # R2/R3 from looking available on a vehicle that only has R.
            if rev > reverse_count:
                box.grid_remove()
                continue
            if rev > 1:
                box.grid()

            box.config(text="R" if reverse_count == 1 and rev == 1 else f"R{rev}")
            active = reverse_active and rev == (abs(current_gear) if current_gear < 0 else 1)
            box.config(bg=self.accent if active else PANEL2,
                       fg="#ffffff" if active else MUTED)
        self.user_cards["THROTTLE"].config(text=f"{data['throttle']*100:.0f}%")
        self.user_cards["BRAKE"].config(text=f"{data['brake']*100:.0f}%")
        self.user_cards["CLUTCH"].config(text=f"{data['clutch']*100:.0f}%")
        self.user_cards["STEERING"].config(text=f"{data['steering']*100:+.0f}%")
        self.user_cards["FUEL"].config(text=f"{data['fuel_ratio']*100:.0f}%")

        flags = data["flags"]
        states = {
            "HANDBRAKE": data["handbrake"],
            "LIGHTS": bool(flags & 0x08),
            "ABS": bool(flags & 0x10),
            "TCS": bool(flags & 0x20),
            "CRUISE": bool(flags & 0x40),
        }
        for name, active in states.items():
            display_text = "ACTIVE" if active else "OFF"
            self.user_flags[name].config(
                text=display_text,
                fg=self.accent if active else MUTED
            )

        # Native-v1 does not currently expose a separate Autopilot state.
        # Keep the User Mode card visible and explicitly mark it as WIP
        # rather than incorrectly treating Cruise Control as Autopilot.
        self.user_flags["AUTOPILOT"].config(text="WORK IN PROGRESS", fg=MUTED)

        # Native-v1 local vehicle axes:
        # X = left/right, Y = vertical, Z = fore/aft.
        # Use X for the lateral G meter so bumps/hills on the vertical Y axis
        # do not incorrectly move the ball left/right.
        # Native-v1 local acceleration: X is fore/aft and Z is lateral.
        # Keep the display orientation with braking UP and acceleration DOWN.
        longitudinal_g = -data["acceleration"][0] / 980.665
        lateral_g = -data["acceleration"][1] / 980.665
        self._target_lateral_g = lateral_g
        self._target_longitudinal_g = longitudinal_g
        if not self._animating_g:
            self._animating_g = True
            self.root.after(0, self.animate_g_meter)

        # G-force is displayed by the circular G meter.
        self.user_status.config(
            text="● TELEMETRY LIVE" if connected else "TELEMETRY PAUSED",
            fg=self.accent if connected else MUTED
        )

    def update_expert(self, data, connected):
        if not hasattr(self, "expert_text"):
            return

        if data:
            self.history.append(
                (data["timestamp"], data["speed_kmh"], data["engine_rpm"])
            )
            self.history = self.history[-self.max_history:]

        lines = []

        if not data:
            lines = [
                "WAITING FOR TELEMETRY",
                "",
                "Protocol: Native-v1",
                "Listen:   127.0.0.1:33330",
                "Packet:   153 bytes",
                "",
                "Start Motor Town and enable Native-v1 telemetry."
            ]
        elif self.page == "Overview":
            lines = [
                f"CONNECTION     {'LIVE' if connected else 'WAITING'}",
                f"PACKET RATE    {self.receiver.rate:.1f} /s",
                f"PACKETS        {self.receiver.packet_count}",
                f"BAD PACKETS    {self.receiver.bad_packets}",
                f"PACKET SIZE    {PACKET_SIZE} bytes",
                "",
                f"SPEED          {data['speed_kmh']:.3f} km/h",
                f"RPM            {data['engine_rpm']:.2f}",
                f"GEAR           {data['current_gear']} / {data['max_forward_gear']}",
                f"THROTTLE       {data['throttle']:.4f}",
                f"BRAKE          {data['brake']:.4f}",
                f"CLUTCH         {data['clutch']:.4f}",
                f"STEERING       {data['steering']:.4f}",
                f"FUEL           {data['fuel_ratio']:.4f}",
                f"HANDBRAKE      {'ON' if data['handbrake'] else 'OFF'}",
                f"YAW/PITCH/ROLL {data['yaw']:.2f} / {data['pitch']:.2f} / {data['roll']:.2f} deg",
                f"BYTES          {self.receiver.bytes_received}",
            ]
        elif self.page == "Engine":
            lines = [
                f"RPM            {data['engine_rpm']:.4f}",
                f"MAX RPM        {data['engine_max_rpm']:.4f}",
                f"GEAR           {data['current_gear']}",
                f"MAX FWD GEAR   {data['max_forward_gear']}",
                f"THROTTLE       {data['throttle']:.6f}",
                f"BRAKE          {data['brake']:.6f}",
                f"CLUTCH         {data['clutch']:.6f}",
                f"FUEL RATIO     {data['fuel_ratio']:.6f}",
            ]
        elif self.page == "Movement":
            wx, wy, wz = data["velocity_world"]
            lx, ly, lz = data["velocity_local"]
            ax, ay, az = data["acceleration"]
            lines = [
                "WORLD VELOCITY (cm/s)",
                f"  X            {wx:.4f}",
                f"  Y            {wy:.4f}",
                f"  Z            {wz:.4f}",
                "",
                "LOCAL VELOCITY (cm/s)",
                f"  X            {lx:.4f}",
                f"  Y            {ly:.4f}",
                f"  Z            {lz:.4f}",
                "",
                "LOCAL ACCELERATION (cm/s²)",
                f"  X            {ax:.4f}",
                f"  Y            {ay:.4f}",
                f"  Z            {az:.4f}",
            ]
        elif self.page == "Controls":
            lines = [
                f"THROTTLE       {data['throttle'] * 100:.2f}%",
                f"BRAKE          {data['brake'] * 100:.2f}%",
                f"CLUTCH         {data['clutch'] * 100:.2f}%",
                f"STEERING       {data['steering'] * 100:+.2f}%",
                f"HANDBRAKE      {'ON' if data['handbrake'] else 'OFF'}",
            ]
        elif self.page == "Position":
            px, py, pz = data["position"]
            lines = [
                f"POSITION X     {px:.4f} cm",
                f"POSITION Y     {py:.4f} cm",
                f"POSITION Z     {pz:.4f} cm",
                "",
                f"YAW            {data['yaw']:.3f}°",
                f"PITCH          {data['pitch']:.3f}°",
                f"ROLL           {data['roll']:.3f}°",
                "",
                "QUATERNION",
                f"X              {data['rotation'][0]:.6f}",
                f"Y              {data['rotation'][1]:.6f}",
                f"Z              {data['rotation'][2]:.6f}",
                f"W              {data['rotation'][3]:.6f}",
            ]
        elif self.page == "Flags":
            flags = data["flags"]
            lines = [
                f"FLAGS          0x{flags:08X}",
                "",
                f"VEHICLE        {'ON' if flags & 0x02 else 'OFF'}",
                f"REVERSE        {'ON' if flags & 0x04 else 'OFF'}",
                f"LIGHTS         {'ON' if flags & 0x08 else 'OFF'}",
                f"ABS            {'ON' if flags & 0x10 else 'OFF'}",
                f"TCS            {'ON' if flags & 0x20 else 'OFF'}",
                f"CRUISE         {'ON' if flags & 0x40 else 'OFF'}",
            ]
        elif self.page == "Raw Data":
            raw = data["raw"]
            lines = [
                "OFFSET   TYPE       VALUE",
                "-" * 55,
                "108      Float      " + f"{data['engine_rpm']:.6f}",
                "112      Float      " + f"{data['engine_max_rpm']:.6f}",
                "116      Int32      " + str(data["current_gear"]),
                "120      Int32      " + str(data["max_forward_gear"]),
                "124      Float      " + f"{data['speed_kmh']:.6f}",
                "128      Float      " + f"{data['throttle']:.6f}",
                "132      Float      " + f"{data['brake']:.6f}",
                "136      Float      " + f"{data['clutch']:.6f}",
                "140      Float      " + f"{data['steering']:.6f}",
                "144      UInt8      " + str(raw[144]) + ("  (HANDBRAKE ON)" if raw[144] else "  (HANDBRAKE OFF)"),
                "145      UInt32     " + f"0x{data['flags']:08X}",
                "149      Float      " + f"{data['fuel_ratio']:.6f}",
            ]

        self.expert_title.config(text=self.page.upper())
        self.expert_text.delete("1.0", "end")
        self.expert_text.insert("1.0", "\n".join(lines))

        for name, b in self.expert_nav.items():
            b.config(bg=self.accent if name == self.page else PANEL2)

        self.footer_right.config(
            text=f"Rate {self.receiver.rate:.1f} Hz  •  "
                 f"Packets {self.receiver.packet_count}  •  "
                 f"Bad {self.receiver.bad_packets}"
        )


def main():
    cfg = load_config()

    if not ensure_dependencies():
        return

    # First start opens the 9-step dashboard tour directly.
    # No separate console or telemetry setup screen is shown.
    first_start = not cfg.get("tutorial_seen", False)

    receiver = TelemetryReceiver(
        cfg.get("host", HOST),
        int(cfg.get("port", PORT))
    )
    receiver.start()

    root = tk.Tk()
    app = App(root, receiver, cfg)

    if first_start:
        root.after(350, app.show_tutorial)

    root.protocol("WM_DELETE_WINDOW", app.close_dashboard)
    root.mainloop()


if __name__ == "__main__":
    main()
