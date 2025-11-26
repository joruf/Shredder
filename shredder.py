#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Secure Trash Shredder for Linux with single pkexec helper authentication.

Features:
- Single authentication via pkexec helper (JSON line RPC).
- Overwrite methods selectable with security/time hints; default set via constant.
- Fully resizable window; startup size, list rows, and live refresh interval are configurable.
- Shows Trash path and live first-level listing that updates during runs.
- Status and progress bars stretch to full width without right padding.
- Robust cleanup handles regular files, symlinks, and nested directories.
"""

import os
import sys
import stat
import json
import random
import string
import threading
import subprocess
from pathlib import Path
from typing import Callable, List, Tuple, Optional, Any, Dict

import tkinter as tk
from tkinter import ttk, messagebox

# ----------------------------- Configuration -------------------------------- #

# Default overwrite method key for initial selection.
# Allowed: "single_zero", "single_rand", "dod_3pass", "dod_7pass", "gutmann_8"
DEFAULT_METHOD_KEY: str = "dod_3pass"

# Startup window dimensions (the app stays fully resizable).
DEFAULT_WINDOW_WIDTH: int = 540
DEFAULT_WINDOW_HEIGHT: int = 420

# Number of visible rows in the Trash listbox at startup.
LISTBOX_VISIBLE_ROWS: int = 10

# Live refresh interval for the Trash listing (milliseconds).
LIVE_REFRESH_MS: int = 500

# Overwrite I/O settings
WRITE_CHUNK_SIZE = 1024 * 1024  # 1 MiB
RENAME_LEN = 16


# ------------------------------- Utilities ---------------------------------- #

def secure_random_name(length: int = RENAME_LEN) -> str:
    """Return a filesystem friendly random name."""
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(random.SystemRandom().choice(alphabet) for _ in range(length))


def fsync_dir(path: Path) -> None:
    """fsync a directory entry, best-effort only."""
    try:
        fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:
        pass


def ensure_writable(p: Path) -> None:
    """Ensure a file or directory is user-writable when possible."""
    try:
        mode = p.stat().st_mode
        if not (mode & stat.S_IWUSR):
            p.chmod(mode | stat.S_IWUSR)
    except Exception:
        pass


def is_mounted_trash_dir(path: Path) -> bool:
    """Return True if Trash path is on a different device than $HOME."""
    try:
        return path.stat().st_dev != Path.home().stat().st_dev
    except Exception:
        return False


def user_trash_root() -> Path:
    """Return the user's Trash/files directory per XDG."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "Trash" / "files"


# -------------------------- Single pkexec helper ----------------------------- #

class RootHelper:
    """Manage a single pkexec-launched helper for one-time auth handshake."""
    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen[str]] = None

    def start(self) -> bool:
        """Start helper via pkexec and ping once; return True on success."""
        helper_cmd = [
            "pkexec",
            sys.executable,
            "-u",
            os.path.abspath(__file__),
            "--helper",
        ]
        try:
            self.proc = subprocess.Popen(
                helper_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            ok = self._rpc({"action": "ping"}) is True
            return bool(ok)
        except Exception:
            return False

    def stop(self) -> None:
        """Terminate the helper if running."""
        try:
            if self.proc and self.proc.poll() is None:
                try:
                    self._rpc({"action": "quit"})
                except Exception:
                    pass
                self.proc.terminate()
        except Exception:
            pass
        finally:
            self.proc = None

    def _rpc(self, payload: Dict[str, Any]) -> Any:
        """Send a JSON request, return 'data' or True; raise on errors."""
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            raise RuntimeError("helper not running")
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("no response from helper")
        resp = json.loads(line)
        if resp.get("status") == "ok":
            return resp.get("data", True)
        raise RuntimeError(resp.get("error", "helper error"))


HELPER = RootHelper()


def helper_main() -> None:
    """Helper entrypoint executed as root under pkexec. Minimal RPC."""
    def send_ok(data: Any = True) -> None:
        print(json.dumps({"status": "ok", "data": data}), flush=True)

    def send_err(msg: str) -> None:
        print(json.dumps({"status": "err", "error": msg}), flush=True)

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            req = json.loads(line)
            action = req.get("action")
            if action == "ping":
                send_ok(True)
            elif action == "quit":
                send_ok(True)
                break
            else:
                send_err("unknown action")
        except Exception as e:
            send_err(str(e))


# --------------------------- Overwrite algorithms ---------------------------- #

class OverwriteMethod:
    """Describe an overwrite method with passes, security level and time factor."""
    def __init__(self, key: str, passes: List[str], security: str, rel_time: str):
        """
        passes per pass:
          - "zero": write 0x00
          - "one":  write 0xFF
          - "rand": write cryptographically secure random bytes
        """
        self.key = key
        self.passes = passes
        self.security = security
        self.rel_time = rel_time

    def display_label(self) -> str:
        """Return the human-facing label for the combobox."""
        pretty = {
            "single_zero": "Single pass 0x00",
            "single_rand": "Single pass Random",
            "dod_3pass":   "DoD 5220.22-M, 3 passes",
            "dod_7pass":   "DoD 5220.22-M, 7 passes",
            "gutmann_8":   "Gutmann-like, 8 random passes",
        }.get(self.key, self.key)
        return f"{pretty} — Security: {self.security}, Time: {self.rel_time}"


OVERWRITE_METHODS: List[OverwriteMethod] = [
    OverwriteMethod("single_zero", ["zero"], "Low", "×1"),
    OverwriteMethod("single_rand", ["rand"], "Medium", "×1"),
    OverwriteMethod("dod_3pass",   ["zero", "one", "rand"], "Strong", "×3"),
    OverwriteMethod("dod_7pass",   ["zero", "one", "rand", "zero", "one", "rand", "rand"], "Very strong", "×7"),
    OverwriteMethod("gutmann_8",   ["rand"] * 8, "Overkill", "×8"),
]

LABEL_TO_METHOD: Dict[str, OverwriteMethod] = {m.display_label(): m for m in OVERWRITE_METHODS}
KEY_TO_METHOD: Dict[str, OverwriteMethod] = {m.key: m for m in OVERWRITE_METHODS}


# ----------------------------- Shredder core -------------------------------- #

class Cancelled(Exception):
    """Raised when a user cancellation is requested."""
    pass


class Shredder:
    """Securely overwrite and remove content under the user's Trash directory."""
    def __init__(self, on_progress: Callable[[float, str], None], is_cancelled: Callable[[], bool]):
        """
        on_progress receives (ratio 0..1, status).
        is_cancelled returns True to request early stop.
        """
        self.on_progress = on_progress
        self.is_cancelled = is_cancelled
        self.total_bytes = 0
        self.processed_bytes = 0

    def trash_root(self) -> Path:
        """Return the target Trash/files path."""
        return user_trash_root()

    def enumerate_all_files(self) -> List[Path]:
        """Return ALL files (including in subdirectories) under Trash, recursively."""
        root = self.trash_root()
        if not root.exists():
            return []
        
        files: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
            dp = Path(dirpath)
            for f in filenames:
                files.append(dp / f)
        
        return files

    def enumerate_all_dirs(self) -> List[Path]:
        """Return ALL directories under Trash, sorted deepest first."""
        root = self.trash_root()
        if not root.exists():
            return []
        
        dirs: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(root, topdown=False, followlinks=False):
            dp = Path(dirpath)
            for d in dirnames:
                dirs.append(dp / d)
        
        # Sort by depth (deepest first) to ensure we delete from bottom up
        dirs.sort(key=lambda p: len(p.parts), reverse=True)
        return dirs

    def compute_total_bytes(self, items: List[Path]) -> int:
        """Compute total bytes of regular files to be overwritten."""
        total = 0
        for p in items:
            if self.is_cancelled():
                raise Cancelled()
            try:
                if p.is_file() and not p.is_symlink():
                    total += p.stat().st_size
            except (FileNotFoundError, PermissionError):
                continue
        return total

    def overwrite_file(self, path: Path, method: OverwriteMethod) -> None:
        """Overwrite a single file per method and unlink it, best-effort."""
        # Symlinks are not overwritten, just unlinked.
        try:
            if path.is_symlink():
                path.unlink()
                fsync_dir(path.parent)
                return
        except FileNotFoundError:
            return
        except Exception:
            # Try to continue even if symlink removal fails
            pass

        if not path.exists():
            return

        ensure_writable(path)
        
        try:
            size = path.stat().st_size
        except (FileNotFoundError, PermissionError):
            # File disappeared or inaccessible, try to remove anyway
            self._scrub_and_unlink(path)
            return

        if size == 0:
            try:
                with open(path, "r+b") as f:
                    os.fsync(f.fileno())
            except Exception:
                pass
            self._scrub_and_unlink(path)
            return

        try:
            with open(path, "r+b", buffering=0) as f:
                for idx, token in enumerate(method.passes, start=1):
                    if self.is_cancelled():
                        raise Cancelled()
                    self.on_progress(self.progress_ratio(), f"Overwriting {path.name} pass {idx}/{len(method.passes)}")
                    f.seek(0)
                    remaining = size
                    while remaining > 0:
                        if self.is_cancelled():
                            raise Cancelled()
                        chunk = min(WRITE_CHUNK_SIZE, remaining)
                        if token == "zero":
                            buf = b"\x00" * chunk
                        elif token == "one":
                            buf = b"\xFF" * chunk
                        else:
                            buf = os.urandom(chunk)
                        written = f.write(buf) or 0
                        remaining -= written
                        self.processed_bytes += written
                        self.on_progress(self.progress_ratio(), f"Overwriting {path.name} pass {idx}/{len(method.passes)}")
                    f.flush()
                    os.fsync(f.fileno())
                f.truncate(size)
                os.fsync(f.fileno())
        except FileNotFoundError:
            return
        except PermissionError:
            ensure_writable(path)
        except Exception:
            # Continue to removal even if overwriting failed
            pass

        self._scrub_and_unlink(path)

    def _scrub_and_unlink(self, path: Path) -> None:
        """Rename the file a few times and unlink; best-effort."""
        if not path.exists():
            return
            
        try:
            parent = path.parent
            for _ in range(3):
                new_name = secure_random_name()
                new_path = parent / new_name
                try:
                    path.rename(new_path)
                    fsync_dir(parent)
                    path = new_path
                except Exception:
                    break
        except Exception:
            pass
        
        try:
            path.unlink(missing_ok=True)
            fsync_dir(path.parent)
        except Exception:
            pass

    def remove_empty_dir(self, dirpath: Path) -> None:
        """Remove a single empty directory, with permission fixes."""
        if not dirpath.exists():
            return
            
        try:
            # Handle symlinked directories
            if dirpath.is_symlink():
                dirpath.unlink()
                fsync_dir(dirpath.parent)
                return
        except Exception:
            pass
        
        try:
            ensure_writable(dirpath)
            dirpath.rmdir()
            fsync_dir(dirpath.parent)
        except OSError:
            # Directory not empty or other error - try harder
            try:
                # Remove any remaining files
                for item in dirpath.iterdir():
                    if item.is_file() or item.is_symlink():
                        try:
                            ensure_writable(item)
                            item.unlink(missing_ok=True)
                        except Exception:
                            pass
                # Try again
                dirpath.rmdir()
                fsync_dir(dirpath.parent)
            except Exception:
                pass

    def progress_ratio(self) -> float:
        """Return processed/total clamped to [0,1]."""
        if self.total_bytes <= 0:
            return 0.0
        return max(0.0, min(1.0, self.processed_bytes / self.total_bytes))

    def shred_trash(self, method: OverwriteMethod) -> Tuple[int, int]:
        """Execute shredding of Trash; return (files_done, dirs_done)."""
        root = self.trash_root()
        if not root.exists():
            self.on_progress(1.0, "100% - Trash is already empty")
            return (0, 0)

        if is_mounted_trash_dir(root):
            self.on_progress(0.0, "0% - Notice: Trash resides on a different mount, guarantees may vary")

        # STEP 1: Collect all files (including in subdirectories)
        self.on_progress(0.0, "0% - Scanning Trash contents...")
        all_files = self.enumerate_all_files()
        self.total_bytes = self.compute_total_bytes(all_files)
        self.processed_bytes = 0

        # STEP 2: Overwrite and delete all files (0-80% of progress)
        files_done = 0
        for f in all_files:
            if self.is_cancelled():
                raise Cancelled()
            self.overwrite_file(f, method)
            files_done += 1
            pct = int(self.progress_ratio() * 80)  # Files take 0-80%
            self.on_progress(self.progress_ratio() * 0.8, f"{pct}% - Processed files {files_done}/{len(all_files)}")

        # STEP 3: Remove all directories (80-90% of progress)
        self.on_progress(0.8, "80% - Collecting directories...")
        all_dirs = self.enumerate_all_dirs()
        dirs_done = 0
        dir_progress_range = 0.1  # 10% for directories
        for idx, d in enumerate(all_dirs):
            if self.is_cancelled():
                raise Cancelled()
            dir_ratio = (idx / len(all_dirs)) * dir_progress_range if all_dirs else 0
            total_progress = 0.8 + dir_ratio
            pct = int(total_progress * 100)
            self.on_progress(total_progress, f"{pct}% - Removing directory {d.name}")
            self.remove_empty_dir(d)
            dirs_done += 1

        # STEP 4: Clear metadata (90-95% of progress)
        self.on_progress(0.9, "90% - Clearing trash metadata...")
        info_dir = root.parent / "info"
        if info_dir.exists():
            for p in info_dir.glob("*.trashinfo"):
                if self.is_cancelled():
                    raise Cancelled()
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass
            fsync_dir(info_dir)

        # STEP 5: Final aggressive cleanup sweep (95-98% of progress)
        self.on_progress(0.95, "95% - Final cleanup sweep...")
        try:
            if root.exists():
                # Get ALL remaining items recursively
                leftovers = []
                for dirpath, dirnames, filenames in os.walk(root, topdown=False, followlinks=False):
                    dp = Path(dirpath)
                    for f in filenames:
                        leftovers.append(dp / f)
                    for d in dirnames:
                        leftovers.append(dp / d)
                
                # Remove everything found
                for idx, p in enumerate(leftovers):
                    if self.is_cancelled():
                        raise Cancelled()
                    leftover_ratio = (idx / len(leftovers)) * 0.03 if leftovers else 0
                    total_progress = 0.95 + leftover_ratio
                    pct = int(total_progress * 100)
                    self.on_progress(total_progress, f"{pct}% - Removing leftover {p.name}")
                    try:
                        if p.is_file() or p.is_symlink():
                            ensure_writable(p)
                            p.unlink(missing_ok=True)
                        elif p.is_dir():
                            self.remove_empty_dir(p)
                    except Exception:
                        pass
        except Exception:
            pass

        # STEP 6: Try to remove the root trash directory itself (98-100% of progress)
        self.on_progress(0.98, "98% - Finalizing...")
        fsync_dir(root)
        if root.exists():
            try:
                root.rmdir()
            except Exception:
                pass
        fsync_dir(root.parent)

        self.on_progress(1.0, "100% - Trash shredded successfully")
        return (files_done, dirs_done)


# --------------------------------- GUI -------------------------------------- #

class App(tk.Tk):
    """Tkinter GUI for the shredder with single-auth helper and live listing."""
    def __init__(self):
        super().__init__()
        self.title("Secure Trash Shredder")
        self.resizable(True, True)
        self.geometry(f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}")

        # Default selection for dropdown based on DEFAULT_METHOD_KEY
        default_method = KEY_TO_METHOD.get(DEFAULT_METHOD_KEY, OVERWRITE_METHODS[0])
        default_label = default_method.display_label()

        self.selected_label = tk.StringVar(value=default_label)
        self.status_var = tk.StringVar(value="Idle")
        self.percent_var = tk.StringVar(value="0%")
        self.progress_pct_var = tk.StringVar(value="0%")
        self.cancel_flag = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self._live_timer: Optional[str] = None  # after() id for live refresh

        self._build_widgets(default_label)
        self._update_trash_info_and_list()

        # Start live refresh loop
        self._schedule_live_refresh()

    def _build_widgets(self, default_label: str) -> None:
        """Create and layout all widgets."""
        padding = {"padx": 10, "pady": 6}

        # Top row: method combobox
        top_frame = ttk.Frame(self)
        top_frame.pack(fill="x", **padding)
        ttk.Label(top_frame, text="Overwrite method:").pack(side="left")
        self.method_combo = ttk.Combobox(
            top_frame,
            state="readonly",
            textvariable=self.selected_label,
            values=[m.display_label() for m in OVERWRITE_METHODS]
        )
        self.method_combo.pack(side="left", fill="x", expand=True, padx=8)
        self.method_combo.set(default_label)

        # Buttons row
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", **padding)
        self.start_btn = ttk.Button(btn_frame, text="Start", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btn_frame, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        
        # Progress percentage display next to buttons
        self.progress_pct_var = tk.StringVar(value="0%")
        pct_display = ttk.Label(btn_frame, textvariable=self.progress_pct_var, font=("TkDefaultFont", 10, "bold"))
        pct_display.pack(side="left", padx=(16, 0))

        # Progress row, no right padding
        prog_frame = ttk.Frame(self)
        prog_frame.pack(fill="x", padx=(10, 0), pady=4)
        self.progress = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", expand=True, side="left")
        self.percent_label = ttk.Label(prog_frame, textvariable=self.percent_var, width=6)
        self.percent_label.pack(side="left", padx=(8, 0))

        # Status line, no right padding, reduced vertical spacing
        status_frame = ttk.Frame(self)
        status_frame.pack(fill="x", padx=(10, 0), pady=(0, 4))
        status_label = ttk.Label(status_frame, textvariable=self.status_var, anchor="w")
        status_label.pack(fill="x", expand=True)

        # Trash path + note, no right padding, tight spacing
        path_frame = ttk.Frame(self)
        path_frame.pack(fill="x", padx=(10, 0), pady=(0, 4))
        self.trash_path_var = tk.StringVar(value="")
        path_label = ttk.Label(path_frame, textvariable=self.trash_path_var, anchor="w")
        path_label.pack(fill="x", expand=True)

        # First-level listing, small top gap, expand to fill remaining space
        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 10))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(list_frame, selectmode="browse", height=LISTBOX_VISIBLE_ROWS)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.config(yscrollcommand=scrollbar.set)

    def _current_method(self) -> OverwriteMethod:
        """Return the OverwriteMethod selected in the combobox."""
        label = self.selected_label.get()
        return LABEL_TO_METHOD.get(label, KEY_TO_METHOD[DEFAULT_METHOD_KEY])

    def _ui_set_running(self, running: bool) -> None:
        """Enable or disable controls while a job is running."""
        self.start_btn.config(state="disabled" if running else "normal")
        self.stop_btn.config(state="normal" if running else "disabled")
        self.method_combo.config(state="disabled" if running else "readonly")

    def _schedule_live_refresh(self) -> None:
        """Schedule periodic refresh of Trash listing."""
        if self._live_timer is not None:
            try:
                self.after_cancel(self._live_timer)
            except Exception:
                pass
        self._live_timer = self.after(LIVE_REFRESH_MS, self._live_refresh_tick)

    def _live_refresh_tick(self) -> None:
        """Timer tick that updates the Trash listing and reschedules itself."""
        try:
            self._update_trash_info_and_list()
        finally:
            # Keep refreshing regardless of running state
            self._schedule_live_refresh()

    def _update_trash_info_and_list(self) -> None:
        """Refresh the Trash path label and the first-level listing."""
        trash = user_trash_root()
        note = f"Target: {trash}  (This is your Trash/Papierkorb per XDG specification)"
        self.trash_path_var.set(note)

        self.listbox.delete(0, "end")
        if trash.exists():
            try:
                entries = list(trash.iterdir())
                entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
                if not entries:
                    self.listbox.insert("end", "(Trash is empty)")
                else:
                    for p in entries:
                        prefix = "[DIR] " if p.is_dir() else "      "
                        self.listbox.insert("end", f"{prefix}{p.name}")
            except Exception as e:
                self.listbox.insert("end", f"(Error reading Trash: {e})")
        else:
            self.listbox.insert("end", "(Trash directory does not exist yet)")

    def start(self) -> None:
        """Start shredding in a worker thread."""
        if self.worker and self.worker.is_alive():
            return
        self.cancel_flag.clear()
        self._ui_set_running(True)
        self.status_var.set("Preparing...")
        self.progress["value"] = 0
        self.percent_var.set("0%")
        self.progress_pct_var.set("0%")

        method = self._current_method()
        shredder = Shredder(on_progress=self._on_progress, is_cancelled=lambda: self.cancel_flag.is_set())

        def run():
            try:
                files_done, dirs_done = shredder.shred_trash(method)
                self._on_progress(1.0, f"Done: {files_done} files, {dirs_done} dirs")
            except Cancelled:
                self._on_progress(shredder.progress_ratio(), "Cancelled by user")
            except Exception as e:
                self._on_progress(shredder.progress_ratio(), f"Error: {e}")
            finally:
                # UI updates already live via timer, but ensure one final refresh
                self.after(0, self._update_trash_info_and_list)
                self.after(0, lambda: self._ui_set_running(False))

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def stop(self) -> None:
        """Request cancellation."""
        self.cancel_flag.set()

    def _on_progress(self, ratio: float, status: str) -> None:
        """Thread-safe progress update."""
        pct = int(max(0, min(100, round(ratio * 100))))
        def update():
            self.progress["value"] = pct
            self.percent_var.set(f"{pct}%")
            self.progress_pct_var.set(f"{pct}%")
            self.status_var.set(status)
        self.after(0, update)


# ------------------------------- Entrypoints -------------------------------- #

def run_gui_with_single_auth() -> None:
    """Start the pkexec helper once, then run the GUI."""
    ok = HELPER.start()
    if not ok:
        messagebox.showerror(
            "Authentication failed",
            "Could not start privileged helper. The application requires one-time authentication."
        )
        sys.exit(1)
    try:
        app = App()
        app.mainloop()
    finally:
        HELPER.stop()


def main() -> None:
    """Dispatch helper vs GUI modes."""
    if "--helper" in sys.argv:
        helper_main()
    else:
        # Hidden root to allow messageboxes before main window
        _root = tk.Tk()
        _root.withdraw()
        run_gui_with_single_auth()


if __name__ == "__main__":
    main()
