#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Runtime dependency checks and optional installation.

Verifies that tkinter and pkexec are available before the GUI starts.
Missing system packages can be installed via the detected package manager.
"""

import os
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Tuple


def is_tkinter_available() -> bool:
    """
    Check whether tkinter can be imported in the current Python interpreter.

    @return bool True when tkinter is available
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import tkinter"],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def is_pkexec_available() -> bool:
    """
    Check whether pkexec is available on PATH.

    @return bool True when pkexec is available
    """
    return shutil.which("pkexec") is not None


def detect_package_manager() -> Optional[str]:
    """
    Detect the system package manager.

    @return str | None Package manager key (apt, dnf, pacman) or None
    """
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("pacman"):
        return "pacman"
    return None


def package_map_for_manager(manager: str) -> Dict[str, str]:
    """
    Return the package names required for each dependency check.

    @param str manager Package manager key
    @return dict[str, str] Mapping of dependency key to package name
    """
    maps: Dict[str, Dict[str, str]] = {
        "apt": {
            "tkinter": "python3-tk",
            "pkexec": "policykit-1",
        },
        "dnf": {
            "tkinter": "python3-tkinter",
            "pkexec": "polkit",
        },
        "pacman": {
            "tkinter": "tk",
            "pkexec": "polkit",
        },
    }
    return maps.get(manager, {})


def get_missing_packages() -> Tuple[Optional[str], List[str]]:
    """
    Determine missing system packages for this application.

    @return tuple[str | None, list[str]] Package manager key and missing packages
    """
    manager = detect_package_manager()
    if manager is None:
        return None, []

    package_map = package_map_for_manager(manager)
    missing: List[str] = []

    if not is_tkinter_available() and "tkinter" in package_map:
        missing.append(package_map["tkinter"])
    if not is_pkexec_available() and "pkexec" in package_map:
        missing.append(package_map["pkexec"])

    return manager, missing


def manual_install_hint(packages: List[str]) -> str:
    """
    Build a manual installation command hint for the user.

    @param list[str] packages Package names to install
    @return str Installation hint text
    """
    manager = detect_package_manager()
    names = " ".join(packages)
    if manager == "apt":
        return f"sudo apt-get install -y {names}"
    if manager == "dnf":
        return f"sudo dnf install -y {names}"
    if manager == "pacman":
        return f"sudo pacman -S --noconfirm {names}"
    return f"Install these packages: {names}"


def prompt_install(packages: List[str]) -> bool:
    """
    Ask the user whether missing packages should be installed.

    @param list[str] packages Package names to install
    @return bool True when the user agrees to install
    """
    package_list = "\n".join(f"  - {name}" for name in packages)
    text = (
        "The following packages are required but not installed:\n"
        f"{package_list}\n\n"
        "Install them now?"
    )

    if shutil.which("zenity"):
        result = subprocess.run(
            [
                "zenity",
                "--question",
                "--title=Missing Dependencies",
                f"--text={text}",
                "--width=420",
            ],
            check=False,
        )
        return result.returncode == 0

    if sys.stdin.isatty():
        answer = input(f"{text}\nInstall now? [y/N]: ").strip().lower()
        return answer in ("y", "yes")

    print(text, file=sys.stderr)
    print(f"Install manually: {manual_install_hint(packages)}", file=sys.stderr)
    return False


def install_packages(manager: str, packages: List[str]) -> bool:
    """
    Install packages using the system package manager with elevated privileges.

    @param str manager Package manager key
    @param list[str] packages Package names to install
    @return bool True when installation succeeded
    """
    if manager == "apt":
        install_cmd = ["apt-get", "install", "-y", *packages]
    elif manager == "dnf":
        install_cmd = ["dnf", "install", "-y", *packages]
    elif manager == "pacman":
        install_cmd = ["pacman", "-S", "--noconfirm", *packages]
    else:
        return False

    if shutil.which("pkexec"):
        cmd = ["pkexec", *install_cmd]
    elif shutil.which("sudo"):
        cmd = ["sudo", *install_cmd]
    else:
        return False

    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_dependencies() -> bool:
    """
    Verify required dependencies and install missing packages when approved.

    Restarts the application after a successful installation so new packages
    are picked up by the Python interpreter.

    @return bool True when all dependencies are available
    """
    manager, missing = get_missing_packages()
    if not missing:
        return True

    if manager is None:
        print(
            "Unsupported package manager. "
            f"Install manually: {manual_install_hint(missing)}",
            file=sys.stderr,
        )
        return False

    if not prompt_install(missing):
        print(
            "Required dependencies are missing. "
            f"Install manually: {manual_install_hint(missing)}",
            file=sys.stderr,
        )
        return False

    if not install_packages(manager, missing):
        print(
            "Could not install required dependencies. "
            f"Install manually: {manual_install_hint(missing)}",
            file=sys.stderr,
        )
        return False

    os.execv(sys.executable, [sys.executable, *sys.argv])
