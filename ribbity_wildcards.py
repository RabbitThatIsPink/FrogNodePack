"""
🐸-Pack — Wildcard Nodes
  • RibbityWildcardBox      — text input with wildcard support, outputs STRING
  • RibbityWildcardResolver — resolves wildcards + deconflicts opposites
"""

from __future__ import annotations
import os
import re
import random
from pathlib import Path

try:
    from aiohttp import web
    from server import PromptServer
    _server = PromptServer.instance
except Exception:
    _server = None
    web = None

# ---------------------------------------------------------------------------
# Wildcards directory
# ---------------------------------------------------------------------------

def _get_wildcards_dir() -> Path:
    here = Path(__file__).parent
    candidates = [
        here.parent.parent / "wildcards",
        here / "wildcards",
        here.parent / "wildcards",
        here.parent.parent.parent / "wildcards",
    ]
    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    default = here / "wildcards"
    default.mkdir(exist_ok=True)
    return default


def _get_wildcard_names() -> list[str]:
    d = _get_wildcards_dir()
    names = []
    for f in sorted(d.rglob("*.txt")):
        rel = f.relative_to(d)
        names.append(str(rel.with_suffix("")).replace("\\", "/"))
    return names


# Register wildcard list endpoint
if _server is not None and web is not None:
    try:
        @_server.routes.get("/ribbity/wildcards/list")
        async def _wildcards_list(request):
            return web.json_response({"wildcards": _get_wildcard_names()})
    except Exception as e:
        print(f"[🐸 Wildcards] Failed to register route: {e}")

# ---------------------------------------------------------------------------
# Wildcard resolution helpers
# ---------------------------------------------------------------------------

_BUILTIN_OPPOSITES = [
    ["right", "left"], ["top", "bottom"], ["up", "down"],
    ["front", "back"], ["forward", "backward"],
    ["north", "south", "east", "west"],
    ["inner", "outer"], ["inside", "outside"],
    ["over", "under"], ["above", "below"],
    ["high", "low"], ["near", "far"],
    ["close", "distant"], ["bright", "dark"],
    ["light", "dark"], ["hot", "cold"],
    ["warm", "cool"], ["large", "small"],
    ["big", "little"], ["tall", "short"],
    ["wide", "narrow"], ["thick", "thin"],
    ["fast", "slow"], ["loud", "quiet"],
    ["happy", "sad"], ["good", "bad"],
    ["new", "old"], ["young", "old"],
    ["full", "empty"], ["open", "closed"],
    ["first", "last"], ["start", "end"],
    ["begin", "finish"],
]


def _load_wildcard_file(name: str, wildcards_dir: Path) -> list[str] | None:
    for path in [wildcards_dir / f"{name}.txt", wildcards_dir / name]:
        if path.exists() and path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f.readlines()]
                    return [l for l in lines if l and not l.startswith("#")]
            except Exception:
                continue
    return None


def _resolve_inline_wildcards(text: str, rng: random.Random,
                               detected_pairs: list) -> str:
    pattern = re.compile(r'\{([^{}]+)\}')
    for _ in range(50):
        m = pattern.search(text)
        if not m:
            break
        options = [o.strip() for o in m.group(1).split("|")]
        if len(options) > 1:
            detected_pairs.append(list(options))
        pick = rng.choice(options) if options else ""
        text = text[:m.start()] + pick + text[m.end():]
    return text


def _resolve_file_wildcards(text: str, base_seed,
                             wildcards_dir: Path, detected_pairs: list) -> str:
    pattern = re.compile(r'__([a-zA-Z0-9_/\\ \t-]+)__')
    counter: dict[str, int] = {}
    for _ in range(50):
        m = pattern.search(text)
        if not m:
            break
        name = m.group(1)
        lines = _load_wildcard_file(name, wildcards_dir)
        if lines:
            counter[name] = counter.get(name, 0) + 1
            rng = (random.Random() if base_seed is None
                   else random.Random(f"{base_seed}::{name.lower()}::{counter[name]}"))
            pick = rng.choice(lines)
            detected_pairs.append(list(lines))
            text = text[:m.start()] + pick + text[m.end():]
        else:
            text = text[:m.start()] + f"[wildcard '{name}' missing]" + text[m.end():]
    return text


def _find_word_positions(text: str, word: str) -> list[tuple[int, int]]:
    return [m.span() for m in re.finditer(
        r'\b' + re.escape(word) + r'\b', text, re.IGNORECASE)]


def _deconflict(text: str, opposite_groups: list,
                rng: random.Random, debug_log: list) -> str:
    for group in opposite_groups:
        if len(group) < 2:
            continue
        occurrences = {w: _find_word_positions(text, w) for w in group}
        if max((len(v) for v in occurrences.values()), default=0) < 2:
            continue
        all_hits = sorted(
            (s[0], s[1], w) for w, spans in occurrences.items() for s in spans)
        seen: set[str] = set()
        used_count = {w: 1 if occurrences.get(w) else 0 for w in group}
        swaps = []
        for start, end, word in all_hits:
            if word not in seen:
                seen.add(word)
                continue
            candidates = sorted(group, key=lambda w: used_count.get(w, 0))
            replacement = candidates[0]
            if replacement == word:
                others = [w for w in group if w != word]
                if others:
                    replacement = rng.choice(others)
                else:
                    continue
            swaps.append((start, end, word, replacement))
            used_count[replacement] = used_count.get(replacement, 0) + 1
        for start, end, original, replacement in sorted(swaps, reverse=True):
            visible = text[start:end]
            if visible.isupper():
                r = replacement.upper()
            elif visible[0].isupper():
                r = replacement.capitalize()
            else:
                r = replacement
            text = text[:start] + r + text[end:]
            debug_log.append(f"Swapped duplicate '{original}' -> '{r}'")
    return text


# ---------------------------------------------------------------------------
# 🐸 Wildcard Box
# ---------------------------------------------------------------------------

class RibbityWildcardBox:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Type __ to use wildcards (e.g. __hair/color__). Outputs the text as-is.",
                }),
            }
        }

    RETURN_TYPES  = ("STRING",)
    RETURN_NAMES  = ("output",)
    FUNCTION      = "run"
    CATEGORY      = "🐸 Node Pack"

    def run(self, text):
        return (text,)


# ---------------------------------------------------------------------------
# 🐸 Wildcard Resolver
# ---------------------------------------------------------------------------

class RibbityWildcardResolver:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "string_input": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Wired string containing wildcards to resolve.",
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff,
                    "tooltip": "Seed for wildcard picks. 0 = random each run.",
                }),
                "use_builtin_opposites": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Use built-in opposite pairs (right/left, top/bottom, etc.) "
                               "to prevent duplicates. Only activates pairs found in wildcard groups.",
                }),
                "use_autodetected_pairs": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Auto-detect opposite pairs from {a|b} wildcard groups.",
                }),
            }
        }

    RETURN_TYPES  = ("STRING", "STRING")
    RETURN_NAMES  = ("resolved_text", "debug")
    FUNCTION      = "resolve"
    CATEGORY      = "🐸 Node Pack"

    def resolve(self, string_input, seed,
                use_builtin_opposites, use_autodetected_pairs):

        combined = string_input or ""
        if not combined.strip():
            return ("", "No input provided.")

        inline_rng   = random.Random() if seed == 0 else random.Random(seed)
        file_seed    = None if seed == 0 else seed
        debug_log    = []
        detected     = []
        wildcards_dir = _get_wildcards_dir()

        debug_log.append(f"Wildcards dir: {wildcards_dir}")

        resolved = combined
        for _ in range(10):
            before   = resolved
            resolved = _resolve_inline_wildcards(resolved, inline_rng, detected)
            resolved = _resolve_file_wildcards(resolved, file_seed, wildcards_dir, detected)
            if resolved == before:
                break

        debug_log.append(f"Resolved: {resolved[:200]}{'...' if len(resolved) > 200 else ''}")

        opposite_groups = []
        if use_autodetected_pairs:
            opposite_groups.extend(detected)
        if use_builtin_opposites:
            detected_words = {w.lower().strip() for g in detected for w in g}
            for bg in _BUILTIN_OPPOSITES:
                if any(w.lower() in detected_words for w in bg):
                    opposite_groups.append(bg)

        final = _deconflict(resolved, opposite_groups, inline_rng, debug_log)

        debug = "\n".join(debug_log)
        num_swaps = sum(1 for l in debug_log if "Swapped" in l)
        print(f"[🐸 Wildcard Resolver] Resolved. {num_swaps} swap(s) applied.")

        return (final, debug)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "FrogWildcardBox":         RibbityWildcardBox,
    "FrogWildcardResolver":    RibbityWildcardResolver,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogWildcardBox":         "🐸 Wildcard Box",
    "FrogWildcardResolver":    "🐸 Wildcard Resolver",
}
