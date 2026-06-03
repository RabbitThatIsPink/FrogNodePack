from __future__ import annotations
import os
import glob
from pathlib import Path

# ---------------------------------------------------------------------------
# 🐸-Pack — Ribbity Log Reader
# Reads the most recent ComfyUI log file and outputs it as a string.
# Wire into a Show Text node to read the log without leaving ComfyUI.
# ---------------------------------------------------------------------------

# ComfyUI Desktop logs live in %AppData%\ComfyUI\logs\
# Portable/standard logs live next to main.py as comfyui.log
# We check both locations.

def _find_log_file() -> str | None:
    # Desktop app log location (Windows)
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        desktop_logs = Path(appdata) / "ComfyUI" / "logs"
        if desktop_logs.exists():
            logs = sorted(desktop_logs.glob("comfyui_*.log"), key=os.path.getmtime, reverse=True)
            if logs:
                return str(logs[0])

    # Portable / standard install — log next to main.py
    # Walk up from this file to find comfyui.log
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "comfyui.log"
        if candidate.exists():
            return str(candidate)

    return None


class RibbityLogReader:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "tail_lines": ("INT", {
                    "default": 50,
                    "min": 1,
                    "max": 500,
                    "tooltip": "How many lines from the end of the log to show.",
                }),
                "filter_text": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Optional: only show lines containing this text",
                }),
            }
        }

    RETURN_TYPES  = ("STRING",)
    RETURN_NAMES  = ("log",)
    FUNCTION      = "read_log"
    CATEGORY      = "🐸 Node Pack"

    def read_log(self, tail_lines, filter_text):
        log_path = _find_log_file()

        if not log_path:
            return ("No log file found.\n"
                    "Checked: %APPDATA%\\ComfyUI\\logs\\comfyui_*.log\n"
                    "and comfyui.log next to main.py",)

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return (f"Error reading log: {e}",)

        # Apply filter
        if filter_text.strip():
            lines = [l for l in lines if filter_text.lower() in l.lower()]

        # Tail
        lines = lines[-tail_lines:]
        result = f"Log: {log_path}\n" + "".join(lines)
        return (result,)


NODE_CLASS_MAPPINGS       = {"FrogLogReader": RibbityLogReader}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogLogReader": "🐸 Log Reader"}
