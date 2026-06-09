"""
FrogNodePack — Prompt Refiner (Ollama)

Takes a tag-based prompt (danbooru-style or mixed) and rewrites it as a
fluent, natural-language image-generation prompt.

Completely separate context from 🐸 Tag to Description — that node extracts
appearance traits for character builders. This node rewrites whole-scene
prompts for direct use in CLIP/text encoders.

Requires Ollama running locally (http://localhost:11434).
"""

import json
import re
import urllib.request
import urllib.error

_OLLAMA_URL = "http://192.168.0.194:11434/api/generate"

# ---------------------------------------------------------------------------
# System prompt — kept entirely separate from Tag to Description's prompt.
# Goal: fluent, vivid, scene-level rewrite. Strict no-hallucination rule.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are an image prompt writer. Convert danbooru-style tags into a single \
fluent prose description for an AI image generator. Follow every rule below.

RULE 1 — NO INVENTION
Only use what is in the tags. Never add adjectives, props, clothing, body \
parts, context, or motivation that are not in the tag list. Every word you \
write must be traceable to a tag.

RULE 1B — UNKNOWN TAGS
If a tag's meaning is unclear or unfamiliar, include it as plain text \
(underscores replaced with spaces) rather than guessing. NEVER invent a \
meaning for a tag you do not recognise. Do NOT interpret unknown tags as \
character names, places, or actions. Example: if "wariza" is unfamiliar, \
write "wariza" — do not write "towards Wariza" or invent a person named Wariza.

RULE 2 — COLOURS ARE MANDATORY
Every colour tag must appear in the output verbatim. "red_hair" → "red hair". \
Never substitute, paraphrase, or drop a colour. Never add adjectives to a \
colour — "red hair" not "sleek red hair" or "vibrant red hair".

RULE 3 — HAIR
Write hair as "[length] [colour] hair". Both are required if both are tagged. \
"long_hair, red_hair" → "long red hair". Never invent texture words like \
"flowing", "silky", or "cascading" unless they are explicit tags.

RULE 4 — EYES
Eye colour is mandatory. "green_eyes" → "green eyes". Never drop it.

RULE 5 — CHARACTER NAMES
If a character name is in the tags, it must be the first word(s) of the \
output. "Kim Possible stands..." not "A girl... Kim Possible...". \
State the name as plain fact — they ARE that character, not a lookalike, \
not someone whose outfit implies a connection to them. \
Never use: "embodying", "resembling", "inspired by", "in the style of", \
"named [X]", "known as", "known in", "connected to", "associated with", \
"reminiscent of", "evokes", "suggests", "implies", or any phrase that \
distances, hedges, or derives identity indirectly from clothing or context. \
Never call them "a girl", "a woman", or "a character" — use the name. \
WRONG: "Her outfit implies she's connected to the character known in Ben 10." \
RIGHT: "Gwen Tennyson stands..."

RULE 6 — METADATA TAGS (IGNORE)
Tags ending in "_(series)", "_(anime)", "_(game)" etc. are database labels. \
Ignore them completely. Studio/publisher tags (disney, marvel, etc.) are also \
metadata — ignore them. Never write "Disney character" or "from the series".

RULE 7 — STYLE TAGS
Art style tags ("american comic book", "halftone dots", "ink linework", etc.) \
describe rendering only — never attach them to clothing or characters. \
Place them at the very end as: "Rendered in [style]." \
If no style tags are present, write no style clause.

RULE 8 — FORMAT
Single flowing prose. No bullet points. No preamble or explanation. \
No closing commentary ("This image evokes...", "This scene showcases..."). \
Output the prompt only.

═══════════════════════════════════════
EXAMPLES
═══════════════════════════════════════
--- Example 1 ---
Input:
1girl, solo, school_uniform, sitting, window, afternoon, light_rays, smile, \
short_hair, brown_hair, blue_eyes, cherry_blossoms, classroom

Output:
A young girl with short brown hair and blue eyes sits beside a classroom \
window, smiling softly as afternoon light rays stream through the glass, \
cherry blossom petals drifting past outside, her school uniform neat in the \
warm golden light.

--- Example 2 ---
Input:
1girl, fantasy, armor, sword, standing, ruins, dramatic_lighting, \
grey_skin, short_hair, white_hair, red_eyes, cape, stormy_sky, \
determined_expression

Output:
A determined woman with grey skin, short white hair, and red eyes stands \
amid ancient ruins in gleaming armor. She grips a sword at her side, a cape \
billowing behind her beneath a stormy sky lit by dramatic light.

--- Example 3 (named character + metadata tags + style tags) ---
Input:
kim_possible, kim_possible_(series), disney, 1girl, solo, long_hair, \
red_hair, green_eyes, athletic build, petite, black crop top, cargo pants, \
black gloves, mission outfit, rooftop, night, city lights, dynamic pose, \
smirking, american comic book, bold ink linework, flat saturated colors, \
halftone dots

Output:
Kim Possible stands on a rooftop at night, smirking in a dynamic pose. She \
has long red hair, green eyes, a petite and athletic build. She wears a black \
crop top, cargo pants, black gloves, and a mission outfit. City lights glow \
against the dark sky behind her. Rendered in a bold American comic book style \
with flat saturated colors, halftone dot shading, and heavy ink linework.\
"""


def _preprocess_tags(raw: str) -> str:
    """Light cleanup: strip A1111 weight notation, normalise underscores."""
    # Remove \( \) and bare ( ) weight notation
    cleaned = re.sub(r"\\[()\[\]]", "", raw)
    cleaned = re.sub(r"\([^)]*:[0-9.]+\)", "", cleaned)   # (tag:1.2)
    cleaned = re.sub(r"[()]", "", cleaned)
    # Normalise each tag
    parts = []
    for part in cleaned.split(","):
        t = part.strip().replace("\\", "").strip("_")
        if t:
            parts.append(t.replace("_", " "))
    return ", ".join(parts)


def _call_ollama(model: str, prompt_text: str, seed: int,
                 temperature: float, max_tokens: int) -> str:
    payload = {
        "model":  model,
        "system": _SYSTEM_PROMPT,
        "prompt": f"Tags: {prompt_text}",
        "stream": False,
        "think":  False,   # disable Qwen3 / DeepSeek-R1 chain-of-thought blocks
        "options": {
            "seed":        seed,
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            text = body.get("response", "").strip()
            # Strip any <think>...</think> blocks (Qwen3 / DeepSeek-R1 reasoning)
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            return text
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"[PromptRefiner] Could not reach Ollama at {_OLLAMA_URL}. "
            f"Is Ollama running?  ({e})"
        )
    except Exception as e:
        raise RuntimeError(f"[PromptRefiner] Ollama call failed: {e}")


class FrogPromptRefiner:
    """
    Paste in a tag-based prompt → get back a fluent natural-language prompt.

    Different from 🐸 Tag to Description, which extracts appearance traits
    for the Duo Character Builder. This node rewrites whole-scene prompts
    for direct use in your text encoder.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "tags": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Tag prompt input. Wire from a 🐸 Library or prompt node.",
                }),
                "model": ("STRING", {
                    "default": "qwen3:8b",
                    "multiline": False,
                    "tooltip": "Ollama model name. Must be pulled via 'ollama pull <name>'.",
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xFFFFFFFF,
                    "tooltip": "Seed for reproducibility. Same seed + same tags = same output.",
                }),
                "temperature": ("FLOAT", {
                    "default": 0.3,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.05,
                    "tooltip": "0 = very literal/consistent. Higher = more creative/varied.",
                }),
                "max_tokens": ("INT", {
                    "default": 220,
                    "min": 40,
                    "max": 600,
                    "step": 10,
                    "tooltip": "Maximum output length in tokens.",
                }),
                "prepend_tags": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Prepend the original tags before the NL prose. "
                               "Gives the CLIP encoder both tag signals and fluent context.",
                }),
            },
            "optional": {
                "prepend": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Optional text to prepend to the output (e.g. quality tags, "
                               "LoRA triggers). Appended before the refined prompt.",
                }),
                "append": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Optional text to append after the refined prompt "
                               "(e.g. style tags, negative-space cues).",
                }),
            },
        }

    CATEGORY      = "🐸 Node Pack/Utility"
    FUNCTION        = "refine"
    RETURN_TYPES    = ("STRING", "STRING")
    RETURN_NAMES    = ("prompt", "debug")
    OUTPUT_TOOLTIPS = (
        "Refined natural-language prompt, ready for your text encoder.",
        "Debug info: cleaned input, model settings, and raw LLM output.",
    )

    def refine(self, tags, model, seed, temperature, max_tokens,
               prepend_tags=True, prepend="", append=""):

        debug_lines = [
            f"[PromptRefiner]  model={model}  seed={seed}  "
            f"temp={temperature}  max_tokens={max_tokens}  prepend_tags={prepend_tags}",
        ]

        if not tags or not tags.strip():
            debug_lines.append("  (no tags provided — returning empty)")
            return ("", "\n".join(debug_lines))

        cleaned = _preprocess_tags(tags)
        debug_lines.append(f"  input (raw)    : {tags.strip()}")
        debug_lines.append(f"  input (cleaned): {cleaned}")

        try:
            refined = _call_ollama(model, cleaned, seed, temperature, max_tokens)
        except RuntimeError as e:
            debug_lines.append(f"  LLM ERROR (passthrough): {e}")
            refined = cleaned   # pass tags through if LLM is unreachable
        debug_lines.append(f"  LLM output     : {refined}")

        # Assemble final prompt
        parts = []
        if prepend and prepend.strip():
            parts.append(prepend.strip().rstrip(",").strip())
        if prepend_tags:
            parts.append(cleaned)
        parts.append(refined)
        if append and append.strip():
            parts.append(append.strip().lstrip(",").strip())

        final = ", ".join(p for p in parts if p)
        debug_lines.append(f"  final output   : {final}")

        return (final, "\n".join(debug_lines))


# ─────────────────────────────────────────────
#  REGISTRATION
# ─────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "FrogPromptRefiner": FrogPromptRefiner,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogPromptRefiner": "🐸 LLM Prompt Refiner (Ollama)",
}
