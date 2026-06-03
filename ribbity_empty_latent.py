import torch
import comfy.model_management

# ---------------------------------------------------------------------------
# 🐸-Pack — Ribbity Empty Latent
# Preset resolution picker. Outputs LATENT, width (INT), and height (INT).
# ---------------------------------------------------------------------------

# Ordered exactly as shown in the UI
PRESETS = [
    "1536 × 1536",
    "1728 × 1344",
    "1344 × 1728",
    "1856 × 1248",
    "1248 × 1856",
    "2016 × 1152",
    "1152 × 2016",
    "2304 × 1024",
    "1024 × 2304",
]

PRESET_MAP = {
    "1536 × 1536": (1536, 1536),
    "1728 × 1344": (1728, 1344),
    "1344 × 1728": (1344, 1728),
    "1856 × 1248": (1856, 1248),
    "1248 × 1856": (1248, 1856),
    "2016 × 1152": (2016, 1152),
    "1152 × 2016": (1152, 2016),
    "2304 × 1024": (2304, 1024),
    "1024 × 2304": (1024, 2304),
}


class RibbityEmptyLatent:
    """
    Generates an empty latent tensor from a preset resolution.
    Outputs the LATENT, and the resolved width and height as integers
    so they can wire into other nodes (e.g. conditioning, upscalers).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "preset":     (PRESETS, {"default": "1536 × 1536"}),
                "batch_size": ("INT", {"default": 1, "min": 1, "max": 64}),
            }
        }

    RETURN_TYPES  = ("LATENT", "INT", "INT")
    RETURN_NAMES  = ("latent", "w", "h")
    FUNCTION      = "generate"
    CATEGORY      = "🐸 Node Pack"

    def generate(self, preset, batch_size):
        w, h = PRESET_MAP[preset]

        # ComfyUI latent space is 1/8 of pixel dimensions
        lw = w // 8
        lh = h // 8

        device = comfy.model_management.intermediate_device()
        latent = torch.zeros([batch_size, 4, lh, lw], device=device)

        return ({"samples": latent}, w, h)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "FrogEmptyLatent": RibbityEmptyLatent,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogEmptyLatent": "🐸 Empty Latent",
}
