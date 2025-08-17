# Project virtual environment

This project uses a local virtual environment created in `.venv`.

To create the venv locally (if not already present):

- Windows (PowerShell):
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  ```

- Windows (cmd.exe):
  ```cmd
  python -m venv .venv
  .\.venv\Scripts\activate.bat
  ```

- macOS / Linux (bash/zsh):
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

Install dependencies with:

```bash
pip install -r requirements.txt
```
