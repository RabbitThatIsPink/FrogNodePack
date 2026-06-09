"""
FrogNodePack — Prompt Processor

Merge → Wildcard Resolve → Sort → Dedupe in a single node.

Replaces the 4-node chain:
  FrogMerge + FrogWildcardResolver + RibbitySorter + FrogDedupe
"""
from __future__ import annotations
import random

from .ribbity_wildcards import (
    _resolve_inline_wildcards,
    _resolve_file_wildcards,
    _get_wildcards_dir,
    _deconflict,
    _BUILTIN_OPPOSITES,
)
from .ribbity_sorter import (
    _split_tags  as _sorter_split,
    _detect_category,
)
from .ribbity_dedupe import (
    _normalise   as _dedupe_normalise,
    _split_tags  as _dedupe_split,
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _merge_inputs(parts: list[str], separator: str) -> str:
    """Strip and join non-empty input strings."""
    cleaned = [p.strip().strip(",").strip() for p in parts if p and p.strip()]
    return separator.join(cleaned)


def _resolve(text: str, seed: int,
             use_builtin_opposites: bool,
             use_autodetected_pairs: bool) -> tuple[str, list[str]]:
    """Run the wildcard resolver. Returns (resolved_text, debug_lines)."""
    debug = []
    if not text.strip():
        return ("", debug)

    inline_rng    = random.Random() if seed == 0 else random.Random(seed)
    file_seed     = None if seed == 0 else seed
    detected      = []
    wildcards_dir = _get_wildcards_dir()

    resolved = text
    for _ in range(10):
        before   = resolved
        resolved = _resolve_inline_wildcards(resolved, inline_rng, detected)
        resolved = _resolve_file_wildcards(resolved, file_seed, wildcards_dir, detected)
        if resolved == before:
            break

    opposite_groups = []
    if use_autodetected_pairs:
        opposite_groups.extend(detected)
    if use_builtin_opposites:
        detected_words = {w.lower().strip() for g in detected for w in g}
        for bg in _BUILTIN_OPPOSITES:
            if any(w.lower() in detected_words for w in bg):
                opposite_groups.append(bg)

    final = _deconflict(resolved, opposite_groups, inline_rng, debug)
    return (final, debug)


def _sort_and_dedupe(text: str) -> tuple[str, list[str]]:
    """Sort tags into category buckets and deduplicate. Returns (result, log)."""
    tags = _sorter_split(text)
    buckets: dict[str, list[str]] = {
        "quality": [], "subject": [], "character": [],
        "series": [], "artist": [], "general": [],
    }
    log = []

    for tag in tags:
        cat = _detect_category(tag)
        if   cat in ("artist_at", "artist_named", "style"):
            buckets["artist"].append(tag);    log.append(f"  ARTIST    <- {tag}")
        elif cat == "quality":
            buckets["quality"].append(tag);   log.append(f"  QUALITY   <- {tag}")
        elif cat == "subject":
            buckets["subject"].append(tag);   log.append(f"  SUBJECT   <- {tag}")
        elif cat == "character":
            buckets["character"].append(tag); log.append(f"  CHARACTER <- {tag}")
        elif cat == "series":
            buckets["series"].append(tag);    log.append(f"  SERIES    <- {tag}")
        else:
            buckets["general"].append(tag);   log.append(f"  GENERAL   <- {tag}")

    ordered: list[str] = []
    for key in ("quality", "subject", "character", "series", "artist", "general"):
        ordered.extend(buckets[key])

    # Deduplicate preserving first occurrence
    seen: set[str] = set()
    deduped: list[str] = []
    for tag in ordered:
        key = _dedupe_normalise(tag)
        if key not in seen:
            seen.add(key)
            deduped.append(tag)

    return (", ".join(deduped), log)


# ── Node ──────────────────────────────────────────────────────────────────────

class FrogPromptProcessor:
    """
    🐸 Prompt Processor

    Merge → Wildcard Resolve → Sort → Dedupe in a single node.

    Replaces the 4-node chain:
      FrogMerge + FrogWildcardResolver + RibbitySorter + FrogDedupe

    Wire up to 6 STRING inputs. Toggle-gated inputs (raffle, scene, tagger)
    are included only when their corresponding toggle_pack flag is True.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed": ("INT", {
                    "default": 0,
                    "min":     0,
                    "max":     0xFFFFFFFFFFFF,
                    "tooltip": "Wildcard seed. 0 = random each run.",
                }),
                "use_builtin_opposites": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Auto-swap left/right, top/bottom etc. from {left|right} wildcards.",
                }),
                "use_autodetected_pairs": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Detect and deconflict opposing wildcard choices automatically.",
                }),
                "separator": ("STRING", {
                    "default":   ", ",
                    "multiline": False,
                    "tooltip":   "Separator used when joining inputs.",
                }),
            },
            "optional": {
                "library": ("STRING", {"forceInput": True,
                    "tooltip": "Wire from the LAST library node in the chain — "
                               "its positive output already contains all chained "
                               "passthroughs (character + style merged). Always included."}),
                "raffle":  ("STRING", {"forceInput": True,
                    "tooltip": "Raffle node output. Gated by toggle_pack 'raffle'."}),
                "scene":   ("STRING", {"forceInput": True,
                    "tooltip": "Wire from the Scenes node output. Gated by toggle_pack 'scene'."}),
                "tagger":  ("STRING", {"forceInput": True,
                    "tooltip": "Tagger or Florence2 output. Gated by toggle_pack 'tagger'."}),
                "extra_1": ("STRING", {"forceInput": True,
                    "tooltip": "Any additional tags. Always included."}),
                "extra_2": ("STRING", {"forceInput": True,
                    "tooltip": "Any additional tags. Always included."}),
                "toggle_pack": ("ANIMA_TOGGLES", {
                    "tooltip": "Wire from 🐸 Toggle Pack. Controls raffle, scene, and tagger inputs. "
                               "If unwired, those three inputs are excluded."}),
            },
        }

    CATEGORY        = "🐸 Node Pack"
    FUNCTION        = "process"
    RETURN_TYPES    = ("STRING", "STRING")
    RETURN_NAMES    = ("prompt", "debug")
    OUTPUT_TOOLTIPS = (
        "Processed prompt — merged, wildcards resolved, sorted, deduped.",
        "Debug log from wildcard resolution and tag sorting.",
    )

    def process(
        self,
        seed,
        use_builtin_opposites,
        use_autodetected_pairs,
        separator,
        library="", raffle="",
        scene="", tagger="", extra_1="", extra_2="",
        toggle_pack=None,
    ):
        debug_lines = [f"[🐸 PromptProcessor]  seed={seed}"]

        # Unpack toggles — default False if nothing wired
        _t = toggle_pack or {}
        include_raffle = _t.get("raffle",   False)
        include_scene  = _t.get("scene",    False)
        include_tagger = _t.get("tagger",   False)

        debug_lines.append(
            f"  toggles: raffle={include_raffle} "
            f"scene={include_scene} tagger={include_tagger}"
        )

        # 1. Merge — library/extras always in; others gated by toggle
        merged = _merge_inputs(
            [
                library,
                raffle  if include_raffle else "",
                scene   if include_scene  else "",
                tagger  if include_tagger else "",
                extra_1,
                extra_2,
            ],
            separator,
        )
        debug_lines.append(f"  merged : {merged[:120]}{'...' if len(merged) > 120 else ''}")

        if not merged.strip():
            debug_lines.append("  (no inputs — returning empty)")
            return ("", "\n".join(debug_lines))

        # 2. Wildcard resolution
        resolved, wc_debug = _resolve(
            merged, seed, use_builtin_opposites, use_autodetected_pairs
        )
        if wc_debug:
            debug_lines.extend(wc_debug)
        debug_lines.append(f"  resolved: {resolved[:120]}{'...' if len(resolved) > 120 else ''}")

        # 3. Sort + dedupe
        final, sort_log = _sort_and_dedupe(resolved)
        debug_lines.extend(sort_log)
        debug_lines.append(f"  final   : {final[:120]}{'...' if len(final) > 120 else ''}")

        print(f"[🐸 PromptProcessor]  Done. {len(_dedupe_split(final))} tags out.")
        return (final, "\n".join(debug_lines))


# ── Registration ──────────────────────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "FrogPromptProcessor": FrogPromptProcessor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogPromptProcessor": "🐸 Prompt Processor",
}
