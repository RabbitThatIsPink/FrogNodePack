"""
🐸-Pack — Ribbity Prompt Merge
Merges a base string with up to 4 optional inputs, each gated by a toggle
from the Anima Toggle Pack. If no toggle pack is wired, all inputs default
to OFF (excluded).
"""
from __future__ import annotations
import re


def _clean(text: str) -> str:
    if not text or not text.strip():
        return ""
    return text.strip().strip(",").strip()


def _join(*parts: str) -> str:
    return ", ".join(p for p in parts if p and p.strip())


class RibbityPromptMerge:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "string_input": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Base prompt string.",
                }),
            },
            "optional": {
                "Tagger":      ("STRING", {"forceInput": True}),
                "Raffle":    ("STRING", {"forceInput": True}),
                "Florence2":   ("STRING", {"forceInput": True}),
                "Scene":       ("STRING", {"forceInput": True}),
                "toggle_pack": ("ANIMA_TOGGLES", {
                    "tooltip": "Toggle pack from Anima Toggle Pack node. "
                               "If unwired, all merge inputs are excluded.",
                }),
            }
        }

    RETURN_TYPES  = ("STRING", "STRING")
    RETURN_NAMES  = ("merged_prompt", "debug")
    FUNCTION      = "merge"
    CATEGORY      = "🐸 Node Pack"

    def merge(self, string_input,
              Tagger=None, Raffle=None, Florence2=None, Scene=None,
              toggle_pack=None):

        # Unpack toggles — default False if no pack wired
        _t = toggle_pack or {}
        include_tagger    = _t.get("tagger",    False)
        include_raffle  = _t.get("raffle",  False)
        include_florence2 = _t.get("florence2", False)
        include_scene     = _t.get("scene",     False)

        base            = _clean(string_input)
        merge_tagger    = _clean(Tagger)    if (include_tagger    and Tagger)    else ""
        merge_raffle  = _clean(Raffle)  if (include_raffle  and Raffle)  else ""
        merge_florence2 = _clean(Florence2) if (include_florence2 and Florence2) else ""
        merge_scene     = _clean(Scene)     if (include_scene     and Scene)     else ""

        merged = _join(base, merge_tagger, merge_raffle, merge_florence2, merge_scene)

        def _status(included, value):
            if not included: return "OFF"
            if value and value.strip(): return "wired"
            return "empty"

        # DEBUG — remove this block when done
        debug_lines = [
            "=== 🐸 PROMPT MERGE ===",
            f"  Base:     {base[:80] or '(empty)'}",
            f"  Tagger    [{_status(include_tagger,    Tagger)}]:    {merge_tagger[:60]    or '(empty)'}",
            f"  Raffle  [{_status(include_raffle,  Raffle)}]:  {merge_raffle[:60]  or '(empty)'}",
            f"  Florence2 [{_status(include_florence2, Florence2)}]: {merge_florence2[:60] or '(empty)'}",
            f"  Scene     [{_status(include_scene,     Scene)}]:     {merge_scene[:60]     or '(empty)'}",
            f"  Output:   {merged[:120] or '(empty)'}",
        ]
        debug = "\n".join(debug_lines)
        # END DEBUG

        return (merged, debug)


NODE_CLASS_MAPPINGS        = {"FrogPromptMerge": RibbityPromptMerge}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogPromptMerge": "🐸 Prompt Merge"}
