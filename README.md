# Secure Trash Shredder for Linux

A graphical tool to **securely overwrite and delete** the contents of your Trash folder on Linux.  
Uses a single `pkexec` authentication at startup – no repeated password prompts.

## Features

- **Single authentication** – helper runs with `pkexec`, one‑time password entry.
- **Multiple overwrite methods** – from single zero pass to 8‑pass random (DoD, Gutmann‑like).
- **Live trash listing** – shows first‑level content of `~/.local/share/Trash/files`.
- **Real‑time progress** – percentage inside the progress bar + detailed status messages.
- **Cancel button** – safely stop the process at any time.
- **Fully resizable window** – adapts to your screen.
- **Dependency check on startup** – offers to install missing system packages (`python3-tk`, `policykit-1`).

## Requirements

- Linux with `pkexec` (package `policykit-1` on Debian/Ubuntu/Mint)
- Python 3.6+ with tkinter (package `python3-tk` on Debian/Ubuntu/Mint)

On first start, missing packages are detected automatically and can be installed via `pkexec`/`sudo`.

## Usage

```bash
git clone https://github.com/joruf/shredder.git
cd shredder
chmod +x shredder.py
./shredder.py
