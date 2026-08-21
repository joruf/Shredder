#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
First-run setup for desktop shortcut creation.

On the first application start the user is asked once whether a desktop
shortcut should be created on Desktop or its localized equivalent. The shared
.initialized marker file in the project directory prevents repeated prompts.
"""

import stat
from pathlib import Path

from tkinter import messagebox

from nemo_setup import INIT_FILE, mark_initialization_done

SCRIPT_DIR = Path(__file__).resolve().parent
DESKTOP_TEMPLATE = SCRIPT_DIR / "Shredder.desktop"
DESKTOP_FILENAME = "Shredder.desktop"


def user_desktop_dir() -> Path:
    """
    Return the user's desktop directory.

    Reads XDG user-dirs when available and falls back to Desktop or Schreibtisch.

    @return Path Desktop directory path
    """
    config = Path.home() / ".config" / "user-dirs.dirs"
    if config.is_file():
        for line in config.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("XDG_DESKTOP_DIR="):
                value = line.split("=", 1)[1].strip().strip('"')
                if value.startswith("$HOME/"):
                    return Path.home() / value[len("$HOME/"):]
                if value == "$HOME":
                    return Path.home()
                return Path(value).expanduser()

    for name in ("Desktop", "Schreibtisch"):
        desktop = Path.home() / name
        if desktop.is_dir():
            return desktop

    return Path.home() / "Desktop"


def install_desktop_shortcut() -> tuple[bool, Path | None]:
    """
    Install the desktop shortcut on the user's desktop.

    The project ``.desktop`` file locates ``shredder.py`` via ``%k``. A symlink on the
    desktop keeps that true: ``readlink -f`` still resolves to the file beside the script.

    @return tuple[bool, Path | None] Success flag and created shortcut path
    """
    try:
        if not DESKTOP_TEMPLATE.is_file():
            return False, None
        dest_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"
        src = SCRIPT_DIR / "shredder.svg"
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            if src.is_file():
                (dest_dir / "shredder.svg").write_bytes(src.read_bytes())
        except OSError:
            pass
        desktop_dir = user_desktop_dir()
        desktop_dir.mkdir(parents=True, exist_ok=True)
        shortcut_path = desktop_dir / DESKTOP_FILENAME
        if shortcut_path.is_symlink() or shortcut_path.exists():
            shortcut_path.unlink()
        shortcut_path.symlink_to(DESKTOP_TEMPLATE.resolve())
        DESKTOP_TEMPLATE.chmod(
            DESKTOP_TEMPLATE.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )
        return True, shortcut_path
    except OSError:
        return False, None


def maybe_prompt_desktop_setup(parent=None) -> None:
    """
    Ask once on first run whether to create a desktop shortcut.

    @param parent Optional Tk parent window for message boxes
    """
    if INIT_FILE.exists():
        return

    answer = messagebox.askyesno(
        "Desktop Shortcut",
        "Would you like to create a desktop shortcut for the Shredder?",
        parent=parent,
    )

    if answer:
        success, _ = install_desktop_shortcut()
        if not success:
            messagebox.showerror(
                "Desktop Shortcut",
                "Could not create the desktop shortcut.",
                parent=parent,
            )

    mark_initialization_done()
