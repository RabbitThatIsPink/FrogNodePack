"""
FrogNodePack — Load Library by Name

Receives a model_name string from 🐸 Load: Model + CLIP + VAE + Name,
finds the Library entry whose name matches, applies its LoRAs to the
incoming MODEL and CLIP, and outputs combined positive/negative text.

Matching order:
  1. Exact        — entry name == model_name (case-insensitive)
  2. Entry-in-name — entry name is a substring of model_name
  3. Name-in-entry — model_name is a substring of entry name
  If nothing matches the passthrough inputs are returned unchanged.

Typical wiring:
  🐸 Load: Model + CLIP + VAE + Name
    MODEL       →  this node  MODEL
    CLIP        →  this node  CLIP
    model_name  →  this node  model_name

  this node
    MODEL     →  🐸 Library (character)  model
    CLIP      →  🐸 Library (character)  clip
    positive  →  🐸 Library (character)  positive_passthrough
    negative  →  🐸 Library (character)  negative_passthrough
"""
from __future__ import annotations
from pathlib import Path

from .ribbity_library import _load, _lock, _apply_loras


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_entry(model_name: str) -> dict | None:
    name_lc = model_name.lower().strip()
    with _lock:
        entries = _load()

    exact = contains = reverse = None
    for entry in entries:
        entry_lc = (entry.get("name") or "").lower().strip()
        if not entry_lc:
            continue
        if entry_lc == name_lc:
            exact = entry
            break
        if contains is None and entry_lc in name_lc:
            contains = entry
        if reverse is None and name_lc in entry_lc:
            reverse = entry

    return exact or contains or reverse


def _combine(a: str, b: str, sep: str = ", ") -> str:
    a, b = (a or "").strip(), (b or "").strip()
    if a and b:
        return a + sep + b
    return a or b


# ── Node ──────────────────────────────────────────────────────────────────────

class FrogLibraryByName:
    """
    🐸 Load Library by Name

    Finds the Library entry whose name matches model_name, applies its LoRAs
    to MODEL + CLIP, and outputs the entry's positive/negative text combined
    with optional passthrough inputs.

    Wire positive/negative → 🐸 Library  positive_passthrough/negative_passthrough
    so character prompts stack on top of these quality prompts.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model":      ("MODEL",),
                "clip":       ("CLIP",),
                "model_name": ("STRING", {
                    "forceInput": True,
                    "tooltip":
                        "Wire from 🐸 Load: Model + CLIP + VAE + Name  model_name output.\n"
                        "Must match the name of a Library entry exactly\n"
                        "(or as a substring).",
                }),
            },
            "optional": {
                "positive_passthrough": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Prepended before the library entry's positive text.",
                }),
                "negative_passthrough": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Prepended before the library entry's negative text.",
                }),
            },
        }

    RETURN_TYPES  = ("MODEL", "CLIP", "STRING", "STRING", "STRING")
    RETURN_NAMES  = ("MODEL", "CLIP", "positive", "negative", "matched_name")
    FUNCTION      = "load_by_name"
    CATEGORY      = "🐸 Node Pack"
    OUTPUT_TOOLTIPS = (
        "MODEL with library LoRAs applied.",
        "CLIP with library LoRAs applied.",
        "Library positive text combined with positive_passthrough.",
        "Library negative text combined with negative_passthrough.",
        "The name of the Library entry that was matched. Empty if none found.",
    )

    def load_by_name(
        self,
        model, clip, model_name,
        positive_passthrough="", negative_passthrough="",
    ):
        entry = _find_entry(model_name)

        if entry is None:
            print(f"[🐸 LibByName] ⚠ No Library entry matching '{model_name}' — "
                  f"passthrough only.")
            positive = (positive_passthrough or "").strip()
            negative = (negative_passthrough or "").strip()
            return (model, clip, positive, negative, "")

        matched_name = entry.get("name", "")
        lib_pos      = entry.get("text",     "") or ""
        lib_neg      = entry.get("negative", "") or ""

        # Apply library LoRAs
        loras = [l for l in (entry.get("loras") or []) if l.get("enabled", True)]
        if loras:
            model, clip, status = _apply_loras(model, clip, loras)
            print(f"[🐸 LibByName] '{matched_name}' LoRAs: {' '.join(status)}")
        else:
            print(f"[🐸 LibByName] matched '{matched_name}' (no LoRAs)")

        positive = _combine(positive_passthrough, lib_pos)
        negative = _combine(negative_passthrough, lib_neg)

        return (model, clip, positive, negative, matched_name)


# ── Registration ──────────────────────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "FrogLibraryByName": FrogLibraryByName,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogLibraryByName": "🐸 Load Library by Name",
}
