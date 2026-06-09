"""
FrogNodePack — Tag to Description

Sends a tag list to a local Ollama model and returns a short
natural-language description suitable for the Duo Character Builder's
description fields.

Requires Ollama running locally (http://localhost:11434).
"""

import json
import re
import urllib.request
import urllib.error

_OLLAMA_URL = "http://localhost:11434/api/generate"

# Tags that describe the scene, group, or a named IP — stripped before
# sending so the model only sees physical appearance attributes.
_SCENE_TAGS = {
    "2girls", "2boys", "1girl", "1boy", "multiple_girls", "multiple_boys",
    "duo", "couple", "group", "3girls", "4girls", "5girls", "6+girls",
    "3boys", "4boys", "siblings", "sisters", "brothers", "twins",
}

_SYSTEM_PROMPT = (
    "You are a concise image prompt writer. "
    "You will receive physical appearance tags for a SINGLE person. "
    "Convert them into a trait-list phrase that completes the sentence "
    "'The one on the left/right has ...'. "
    "Output ONLY the traits — do not start with 'A woman', 'A man', 'She', 'He', or any subject. "
    "STRICT RULE: only describe what is explicitly listed in the tags. "
    "NEVER add anything that is not in the tag list. No glasses, no clothing, no accessories, "
    "no expressions, no poses — nothing unless it appears in the tags. "
    "You MUST include every physical attribute from the tags — do not skip or omit any. "
    "Hair length (short hair, long hair, medium hair) refers to the HAIR. "
    "Always write hair as '[length] [colour] hair', e.g. 'short orange hair'. "
    "CHARACTER NAMES are identifiers only — never derive physical attributes from them. "
    "If the tags say 'purple_hair', write 'purple hair' even if the character is named Raven. "
    "The explicit colour tag always wins over any connotation the name carries. "
    "If a character name is present in the tags, include it naturally at the start, "
    "e.g. 'Gwen Tennyson's short orange hair, green eyes, and a blue hairclip'. "
    "Do not use the word 'resembling'. "
    "Do not reference other people, pairs, or groups. "
    "No preamble, no trailing punctuation.\n\n"
    "Example (no name):\n"
    "Tags: short hair, orange hair, green eyes, small breasts, blue hairclip, hourglass waist\n"
    "Output: short orange hair, green eyes, a blue hairclip, small breasts, and an hourglass waist\n\n"
    "Example (with name):\n"
    "Tags: gwen tennyson, short hair, orange hair, green eyes, small breasts, blue hairclip\n"
    "Output: Gwen Tennyson's short orange hair, green eyes, a blue hairclip, and small breasts"
)


_APPEARANCE_WORDS = {
    "hair", "eyes", "eye", "breast", "breasts", "skin", "body", "waist",
    "choker", "hairclip", "clip", "ponytail", "braid", "bang", "bangs",
    "short", "long", "medium", "small", "large", "slim", "slender",
    "pale", "dark", "light", "blue", "red", "green", "orange", "purple",
    "black", "white", "pink", "brown", "yellow", "blonde", "silver",
    "toned", "petite", "tall", "thin", "curvy", "hourglass", "single",
    # Body parts & physical features that are NOT names
    "ear", "ears", "pointy", "tail", "tails", "horn", "horns",
    "fang", "fangs", "claw", "claws", "wing", "wings", "lip", "lips",
    "nose", "mouth", "chin", "cheek", "cheeks", "neck", "shoulder",
    "arm", "arms", "leg", "legs", "hand", "hands", "foot", "feet",
    "back", "chest", "hip", "hips", "belly", "navel", "thigh", "thighs",
    "freckle", "freckles", "mole", "scar", "tattoo", "piercing",
    "glasses", "ribbon", "bow", "hat", "collar", "uniform",
}

_FRANCHISE_SUFFIXES = (
    "_(series)", "_(dc)", "_(marvel)", "_(anime)", "_(game)",
    "_(film)", "_(comics)", "_(cartoon)", "_(tv)",
)


def _extract_name(raw: str) -> str:
    """Return the given name of the first character found in the raw tag string.
    Uses the shortest word in a name tag to handle franchise_firstname patterns
    like 'theowlhouse_luz' → 'Luz', 'gwen_tennyson' → 'Gwen'.
    Returns empty string if none found."""
    cleaned = re.sub(r"\\[()\[\]]", "", raw)
    cleaned = re.sub(r"[()]", "", cleaned)
    for part in cleaned.split(","):
        t = part.strip().strip("_").replace("\\", "")
        if not t:
            continue
        normalised = t.lower().replace(" ", "_")
        # Skip scene tags
        if normalised in _SCENE_TAGS:
            continue
        # Skip franchise/series suffix tags
        if any(normalised.endswith(s) for s in _FRANCHISE_SUFFIXES):
            continue
        # Name heuristic: two+ underscore-joined words, none of which are appearance words
        words = [w for w in normalised.split("_") if w]
        if len(words) >= 2 and not any(w in _APPEARANCE_WORDS for w in words):
            # Take the shortest word — given names are shorter than surnames/franchise prefixes
            given = min((w for w in words if len(w) >= 2), key=len, default="")
            if given:
                return given.title()
    return ""


def _clean_tags(raw: str) -> str:
    """Strip escaping, parenthetical groupings, and scene-level tags."""
    # Remove A1111 weight notation: \( \) and bare ( )
    cleaned = re.sub(r"\\[()\[\]]", "", raw)
    cleaned = re.sub(r"[()]", "", cleaned)
    tags = []
    for part in cleaned.split(","):
        t = part.strip().strip("_").replace("\\", "")
        if not t:
            continue
        normalised = t.lower().replace(" ", "_")
        if normalised in _SCENE_TAGS:
            continue
        # Convert underscores to spaces so the model reads names naturally
        tags.append(t.replace("_", " "))
    return ", ".join(tags)


def _call_ollama(model: str, tags: str, seed: int) -> str:
    payload = {
        "model":  model,
        "system": _SYSTEM_PROMPT,
        "prompt": f"Tags: {tags}",
        "stream": False,
        "options": {
            "seed":        seed,
            "temperature": 0.1,   # very low = minimal hallucination
            "num_predict": 160,   # cap response length
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        _OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "").strip()
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"[TagToDescription] Could not reach Ollama at {_OLLAMA_URL}. "
            f"Is Ollama running?  ({e})"
        )
    except Exception as e:
        raise RuntimeError(f"[TagToDescription] Ollama call failed: {e}")


class TagToDescription:
    """
    Converts two character tag strings into separate natural-language
    descriptions using a local Ollama model (default: mistral).

    Wire char_a_tags / char_b_tags from two 🐸 Library nodes, then
    wire description_a / description_b to the Duo Character Builder.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "char_a_tags": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Tags for Character A. Wire from a 🐸 Library 'positive' output.",
                }),
                "char_b_tags": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Tags for Character B. Wire from a 🐸 Library 'positive' output.",
                }),
                "model": ("STRING", {
                    "default": "mistral",
                    "multiline": False,
                    "tooltip": "Ollama model name (must be pulled via 'ollama pull <name>').",
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xFFFFFFFF,
                    "tooltip": "Seed passed to the model for reproducibility.",
                }),
            },
            "optional": {
                "char_a_name": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Wire from 🐸 Library 'name' output for Character A. "
                               "Used directly in the names output — more reliable than tag extraction.",
                }),
                "char_b_name": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Wire from 🐸 Library 'name' output for Character B.",
                }),
            },
        }

    CATEGORY      = "🐸 Node Pack/Utility"
    FUNCTION        = "convert"
    RETURN_TYPES    = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES    = ("description_a", "description_b", "names", "debug")
    OUTPUT_TOOLTIPS = (
        "Description for Character A — wire to char_a_NL on Duo Character Builder.",
        "Description for Character B — wire to char_b_NL on Duo Character Builder.",
        "Both character names joined as 'Name1 & Name2'.",
        "Debug info for both characters.",
    )

    def convert(self, char_a_tags, char_b_tags, model, seed,
                char_a_name="", char_b_name=""):
        results = []
        name_list = []
        debug_lines = [f"[TagToDescription]  model={model}  seed={seed}"]

        for label, raw, wired_name in (
            ("A", char_a_tags, char_a_name),
            ("B", char_b_tags, char_b_name),
        ):
            # Prefer wired name from Library; fall back to tag extraction
            if wired_name and wired_name.strip():
                name = wired_name.strip()
                name_source = "wired"
            else:
                name = _extract_name(raw) if raw else ""
                name_source = "extracted"
            if name:
                name_list.append(name)

            if not raw or not raw.strip():
                results.append("")
                debug_lines.append(f"  Char {label}: (no tags provided)")
                continue

            cleaned = _clean_tags(raw)
            if not cleaned:
                results.append("")
                debug_lines.append(f"  Char {label}: (no usable tags after cleaning)")
                continue

            try:
                desc = _call_ollama(model, cleaned, seed)
            except RuntimeError as e:
                desc = cleaned   # pass tags through if LLM is unreachable
                debug_lines.append(f"  Char {label}: LLM ERROR (passthrough): {e}")
            results.append(desc)
            debug_lines.append(
                f"  Char {label}:\n"
                f"    name   : {name or '(none)'} [{name_source}]\n"
                f"    raw    : {raw.strip()}\n"
                f"    cleaned: {cleaned}\n"
                f"    output : {desc}"
            )

        names_out = " & ".join(name_list)
        return (results[0], results[1], names_out, "\n".join(debug_lines))


# ─────────────────────────────────────────────
#  REGISTRATION
# ─────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "TagToDescription": TagToDescription,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TagToDescription": "🐸 Tag to Description (Ollama)",
}
