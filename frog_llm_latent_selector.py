"""
FrogNodePack — LLM Latent Selector

Sends the image prompt to an Ollama model, asks it to pick the best
resolution from the preset list, then outputs an empty LATENT at that
resolution — plus width and height integers for downstream nodes.

Falls back to the chosen fallback preset if the LLM is unreachable or
returns an unrecognisable response.
"""

import json
import re
import torch
import urllib.request
import urllib.error

import comfy.model_management
from .ribbity_empty_latent import PRESET_MAP, PRESETS

# ---------------------------------------------------------------------------
_OLLAMA_URL = "http://localhost:11434/api/generate"

_DEFAULT = "1536 × 1536"

_SYSTEM_PROMPT = """\
You select image canvas resolutions. Given an image generation prompt, \
choose the single best resolution from the list below.

RULES
- Single character / portrait / head-and-shoulders / close-up  → tall (portrait)
- Full body single character                                    → portrait
- Two or more characters side by side                          → landscape
- Wide scene / background-heavy / cinematic                    → cinematic wide
- Square or unclear composition                                → square
- Scrolling scene / comic panel                                → panoramic or ultra tall

AVAILABLE RESOLUTIONS (respond with EXACTLY one line — the resolution string only):
1536 × 1536
1728 × 1344
1344 × 1728
1856 × 1248
1248 × 1856
2016 × 1152
1152 × 2016
2304 × 1024
1024 × 2304

Output the chosen resolution string on a single line. Nothing else."""


# ---------------------------------------------------------------------------

def _call_ollama(model: str, prompt: str, keep_alive: int = 0) -> str:
    payload = {
        "model":      model,
        "system":     _SYSTEM_PROMPT,
        "prompt":     f"Prompt: {prompt[:400]}",   # cap to avoid huge tokens
        "stream":     False,
        "think":      False,
        "keep_alive": keep_alive,   # 0 = unload immediately, frees VRAM after response
        "options": {
            "temperature": 0.1,
            "num_predict": 20,
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            text = body.get("response", "").strip()
            # Strip any stray <think> blocks
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            return text
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"[LLMLatentSelector] Could not reach Ollama at {_OLLAMA_URL}.  ({e})"
        )
    except Exception as e:
        raise RuntimeError(f"[LLMLatentSelector] Ollama call failed: {e}")


def _parse_resolution(text: str) -> str:
    """Extract a valid preset string from the LLM response."""
    text = text.strip()
    # Direct match against known presets (handles extra whitespace / trailing text)
    for res in PRESET_MAP:
        if res in text:
            return res
    # Numeric fallback: e.g. "1344x1728" or "1344 x 1728"
    m = re.search(r'(\d{3,4})\s*[×xX]\s*(\d{3,4})', text)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        key = f"{w} × {h}"
        if key in PRESET_MAP:
            return key
    return _DEFAULT


# ---------------------------------------------------------------------------

class FrogLLMLatentSelector:
    """
    Asks an Ollama LLM to pick the best canvas resolution for the prompt,
    then outputs an empty LATENT at that size.

    Wire the output latent into 🐸 Smart Latent Switch's override slot so
    the workflow falls back to a manual preset when the LLM is offline.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "forceInput": True,
                    "tooltip": "The image prompt. Wire from your prompt node. The LLM picks the best resolution for it.",
                }),
                "model": ("STRING", {
                    "default": "mistral",
                    "multiline": False,
                    "tooltip": "Ollama model to use. Should match what's loaded on the remote machine.",
                }),
                "batch_size": ("INT", {
                    "default": 1,
                    "min":     1,
                    "max":     64,
                }),
                "fallback": (PRESETS, {
                    "default": _DEFAULT,
                    "tooltip": "Resolution used if the LLM is unreachable or returns garbage.",
                }),
                "unload_after": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Unload the model from VRAM immediately after each call. "
                               "Frees ~35% VRAM for Anima and the Detailer. "
                               "Disable if you are doing rapid repeated runs and can spare the VRAM.",
                }),
            },
        }

    RETURN_TYPES    = ("LATENT", "INT", "INT", "STRING")
    RETURN_NAMES    = ("latent", "w", "h", "resolution")
    FUNCTION        = "select"
    CATEGORY      = "🐸 Node Pack/Utility"
    OUTPUT_TOOLTIPS = (
        "Empty latent at the chosen resolution.",
        "Width in pixels.",
        "Height in pixels.",
        "The resolution string that was chosen (e.g. '1344 × 1728').",
    )

    def select(self, prompt, model, batch_size, fallback, unload_after):
        chosen     = fallback
        keep_alive = 0 if unload_after else 300   # 0 = eject now, 300 = 5-min default

        if prompt and prompt.strip():
            try:
                response = _call_ollama(model, prompt.strip(), keep_alive=keep_alive)
                chosen   = _parse_resolution(response)
                print(f"[🐸 LLM Latent Selector]  LLM → '{response}'  →  {chosen}"
                      f"  (keep_alive={keep_alive}s)")
            except RuntimeError as e:
                print(f"[🐸 LLM Latent Selector]  {e}  →  fallback: {fallback}")
                chosen = fallback
        else:
            print(f"[🐸 LLM Latent Selector]  no prompt — using fallback: {fallback}")

        w, h  = PRESET_MAP[chosen]
        lw    = w // 8
        lh    = h // 8

        device = comfy.model_management.intermediate_device()
        latent = torch.zeros([batch_size, 4, lh, lw], device=device)

        return ({"samples": latent}, w, h, chosen)


# ─────────────────────────────────────────────
#  REGISTRATION
# ─────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "FrogLLMLatentSelector": FrogLLMLatentSelector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogLLMLatentSelector": "🐸 LLM Latent Selector",
}
