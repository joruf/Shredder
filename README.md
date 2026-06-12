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
- **No external dependencies** – uses only Python standard library + tkinter.

## Requirements

- Linux with `pkexec` (part of `policykit-1`)
- Python 3.6+ (tkinter is usually pre‑installed)

## Usage

```bash
git clone https://github.com/joruf/shredder.git
cd shredder
chmod +x shredder.py
./shredder.py
