"""
FrogNodePack — Duo Dupe Check

Checks whether the current character pair already has a saved entry in the
🐸 Library. If a match is found (either order), the job is cancelled via
InterruptProcessingException — same mechanism as the Image Picker cancel.

If no match is found, name_a and name_b pass through unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    import comfy.model_management as _mm
except ImportError:
    _mm = None

_STORE_PATH = Path(__file__).parent / "data" / "prompts.json"


def _load_library() -> list[dict]:
    if not _STORE_PATH.exists():
        return []
    try:
        with _STORE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("prompts"), list):
            return data["prompts"]
    except Exception as e:
        print(f"[🐸 Duo Dupe Check] failed to read library: {e}")
    return []


def _normalise(name: str) -> str:
    return name.strip().lower()


class FrogDuoDupeCheck:
    """
    Cancels the current job if a library entry already exists for this
    character pair (checked in both orders: 'A & B' and 'B & A').
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name_a": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Name of Character A — wire from 🐸 Tag to Description 'names' "
                               "or a Library 'name' output.",
                }),
                "name_b": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Name of Character B.",
                }),
            },
        }

    CATEGORY        = "🐸 Node Pack"
    FUNCTION        = "check"
    RETURN_TYPES    = ("STRING", "STRING", "STRING")
    RETURN_NAMES    = ("name_a", "name_b", "status")
    OUTPUT_TOOLTIPS = (
        "Name A passthrough.",
        "Name B passthrough.",
        "Status message — shows which pair was checked.",
    )

    def check(self, name_a: str, name_b: str):
        a = name_a.strip()
        b = name_b.strip()

        # Same character picked twice
        if _normalise(a) == _normalise(b):
            msg = f"[🐸 Duo Dupe Check] '{a} & {b}' — same character twice, cancelling job."
            print(msg)
            if _mm is not None:
                raise _mm.InterruptProcessingException()
            else:
                raise RuntimeError(msg)

        candidates = {
            _normalise(f"{a} & {b}"),
            _normalise(f"{b} & {a}"),
        }

        entries = _load_library()
        for entry in entries:
            entry_name = _normalise(entry.get("name", ""))
            if entry_name in candidates:
                msg = (
                    f"[🐸 Duo Dupe Check] '{a} & {b}' already exists in the library "
                    f"(matched: '{entry.get('name', '')}') — cancelling job."
                )
                print(msg)
                if _mm is not None:
                    raise _mm.InterruptProcessingException()
                else:
                    raise RuntimeError(msg)

        status = f"[🐸 Duo Dupe Check] '{a} & {b}' — no duplicate found, continuing."
        print(status)
        return (a, b, status)


# ─────────────────────────────────────────────
#  REGISTRATION
# ─────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "FrogDuoDupeCheck": FrogDuoDupeCheck,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogDuoDupeCheck": "🐸 Duo Dupe Check",
}
