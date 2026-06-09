"""
FrogNodePack — Checkpoint-Aware Library Selector

Matches the currently selected checkpoint/diffusion model filename against a
user-defined keyword ruleset and outputs the matching library entry ID.

Wire the output → 🐸 Library node's  prompt_id_input  to auto-switch the
active library entry based on which model is loaded.

Rules format (one rule per line):
    keyword1, keyword2 : library_entry_id

  • Keywords are comma-separated; any ONE matching = rule fires.
  • Matching is case-insensitive substring of the model filename stem.
  • First matching rule wins.
  • Lines starting with # (or blank) are ignored.

Example rules:
    # ANIMA variants
    anima, ribbity          : anima_kim
    # Pony / PDXL
    pony, pdxl              : pony_style
    # Flux
    flux                    : flux_base
"""
from __future__ import annotations
from pathlib import Path

try:
    import folder_paths as _fp
except ImportError:
    _fp = None


def _get_model_list() -> list[str]:
    """Return combined diffusion_models + checkpoints list, deduplicated."""
    if _fp is None:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for bucket in ("diffusion_models", "checkpoints"):
        try:
            for n in _fp.get_filename_list(bucket):
                if n not in seen:
                    seen.add(n)
                    names.append(n)
        except Exception:
            pass
    return names or [""]


def _parse_rules(rules_text: str) -> list[tuple[list[str], str]]:
    """
    Parse the rules string into a list of (keywords, library_id) pairs.
    Returns [] on empty input.
    """
    parsed: list[tuple[list[str], str]] = []
    for raw_line in rules_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        kw_part, _, id_part = line.partition(":")
        lib_id = id_part.strip()
        if not lib_id:
            continue
        keywords = [k.strip().lower() for k in kw_part.split(",") if k.strip()]
        if keywords:
            parsed.append((keywords, lib_id))
    return parsed


def _match(model_name: str, rules: list[tuple[list[str], str]]) -> str | None:
    """
    Test model_name stem (lowercase, no extension) against each rule.
    Returns the first matching library_id, or None.
    """
    stem = Path(model_name).stem.lower()
    for keywords, lib_id in rules:
        for kw in keywords:
            if kw in stem:
                return lib_id
    return None


# ── Node ──────────────────────────────────────────────────────────────────────

class FrogCheckpointLibrarySelector:
    """
    🐸 Checkpoint Library Selector

    Picks a 🐸 Library entry ID based on which diffusion model is loaded.
    Wire  prompt_id  →  🐸 Library  prompt_id_input.

    Rules (one per line):
        keyword1, keyword2 : library_entry_id
    First matching rule wins.  Matching is a case-insensitive substring of
    the model filename stem.
    """

    @classmethod
    def INPUT_TYPES(cls):
        model_list = _get_model_list()
        return {
            "required": {
                "model_name": (model_list, {
                    "tooltip": "Select the diffusion model / checkpoint that is loaded in your workflow.",
                }),
                "rules": ("STRING", {
                    "default":   "# keyword1, keyword2 : library_entry_id\nanima : ",
                    "multiline": True,
                    "tooltip":
                        "One rule per line:  keyword1, keyword2 : library_entry_id\n"
                        "First matching rule wins.  Matching is a case-insensitive\n"
                        "substring of the model filename stem.\n"
                        "Lines starting with # are comments.",
                }),
                "default_id": ("STRING", {
                    "default":   "",
                    "multiline": False,
                    "tooltip":   "Library entry ID returned when no rule matches.",
                }),
            },
            "optional": {
                "model_name_override": ("STRING", {
                    "forceInput": True,
                    "tooltip":
                        "If wired, overrides the model_name dropdown.\n"
                        "Useful if another node outputs the checkpoint filename as a string.",
                }),
            },
        }

    RETURN_TYPES  = ("STRING", "STRING")
    RETURN_NAMES  = ("prompt_id", "debug")
    FUNCTION      = "select"
    CATEGORY      = "🐸 Node Pack/Utility"
    OUTPUT_TOOLTIPS = (
        "Library entry ID — wire to 🐸 Library → prompt_id_input.",
        "Debug: shows which rule matched and the resolved ID.",
    )

    def select(
        self,
        model_name: str,
        rules: str,
        default_id: str,
        model_name_override: str = "",
    ):
        # Override from wired input if provided
        active_name = (model_name_override or "").strip() or model_name

        debug_lines = [f"[🐸 CheckpointLibrarySelector]"]
        debug_lines.append(f"  model : {active_name}")

        parsed = _parse_rules(rules)
        debug_lines.append(f"  rules : {len(parsed)} loaded")

        matched_id = _match(active_name, parsed)

        if matched_id is not None:
            result = matched_id
            stem = Path(active_name).stem.lower()
            # Find which rule fired for the debug line
            for keywords, lib_id in parsed:
                if any(kw in stem for kw in keywords):
                    debug_lines.append(
                        f"  match : keywords [{', '.join(keywords)}] → '{lib_id}'"
                    )
                    break
        else:
            result = default_id
            debug_lines.append(
                f"  match : none — using default '{default_id}'"
            )

        debug_lines.append(f"  output prompt_id = '{result}'")
        debug = "\n".join(debug_lines)
        print(f"[🐸 CheckpointLibrarySelector]  {active_name!r} → '{result}'")
        return (result, debug)


# ── Registration ──────────────────────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "FrogCheckpointLibrarySelector": FrogCheckpointLibrarySelector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogCheckpointLibrarySelector": "🐸 Checkpoint Library Selector",
}
