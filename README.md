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

## Testing

```bash
python3 -m unittest tests.test_cross_platform_contract -v
python3 -m unittest discover -s tests -v
```

CI runs these checks on Ubuntu 22.04/24.04 (Python 3.11 and 3.12) on every push and
pull request. **Windows is not supported** — this is a Linux Trash shredder (`pkexec`).

### Multi-OS matrix (local Linux host)

```bash
~/os-test-matrix/bin/test-project /path/to/shredder
~/os-test-matrix/bin/test-project "$PWD" --only ubuntu-2404
```

On-demand Linux runners: [`OS Matrix`](.github/workflows/os-matrix.yml).
Results: `~/os-test-matrix/results/`.
