"""
FrogNodePack — Pixel Upscaler

Upscales an image using classic pixel-based interpolation methods.
Supports Nearest Neighbour, Bilinear, and Lanczos resampling.
Scale factor is adjustable from 0.1 to 10.0.
"""

import torch
import torch.nn.functional as F
import numpy as np

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


UPSCALE_METHODS = [
    "Nearest Neighbour",
    "Bilinear",
    "Lanczos",
]


def _upscale(image, scale, method):
    """Upscale a ComfyUI image tensor (B, H, W, C) by scale factor."""
    B, H, W, C = image.shape
    new_h = max(1, round(H * scale))
    new_w = max(1, round(W * scale))

    if method == "Nearest Neighbour":
        img = image.permute(0, 3, 1, 2).float()
        img = F.interpolate(img, size=(new_h, new_w), mode="nearest")
        return img.permute(0, 2, 3, 1)

    elif method == "Bilinear":
        img = image.permute(0, 3, 1, 2).float()
        img = F.interpolate(img, size=(new_h, new_w),
                            mode="bilinear", align_corners=False)
        return img.permute(0, 2, 3, 1)

    elif method == "Lanczos":
        if not _PIL_AVAILABLE:
            raise RuntimeError(
                "Pillow is required for Lanczos upscaling. "
                "Install it with: pip install Pillow"
            )
        resample = Image.LANCZOS
        results = []
        for b in range(B):
            frame = image[b].cpu().numpy()
            frame_uint8 = (frame.clip(0, 1) * 255).astype(np.uint8)
            pil_img = Image.fromarray(frame_uint8, mode="RGB" if C == 3 else "RGBA")
            pil_img = pil_img.resize((new_w, new_h), resample)
            result = np.array(pil_img).astype(np.float32) / 255.0
            results.append(torch.from_numpy(result))
        return torch.stack(results)

    else:
        raise ValueError(f"Unknown upscale method: {method}")


class FrogPixelUpscaler:
    """Upscale an image using classic pixel interpolation methods."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {
                    "tooltip": "Input image to upscale.",
                }),
                "scale": ("FLOAT", {
                    "default": 2.0,
                    "min": 0.1,
                    "max": 10.0,
                    "step": 0.05,
                    "tooltip": "Scale multiplier. 2.0 = double size, 0.5 = half size.",
                }),
                "method": (UPSCALE_METHODS, {
                    "default": "Lanczos",
                    "tooltip": "Resampling method. Nearest = sharp/pixelated, "
                               "Bilinear = smooth, Lanczos = sharp + smooth.",
                }),
            }
        }

    RETURN_TYPES    = ("IMAGE",)
    RETURN_NAMES    = ("image",)
    FUNCTION        = "upscale"
    CATEGORY        = "🐸 Node Pack"

    def upscale(self, image, scale, method):
        B, H, W, C = image.shape
        new_h = max(1, round(H * scale))
        new_w = max(1, round(W * scale))

        print(f"[🐸 Pixel Upscaler] {W}x{H} → {new_w}x{new_h} "
              f"(scale={scale}x, method={method})")

        result = _upscale(image, scale, method)
        return (result,)


# ── Registration ──────────────────────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "FrogPixelUpscaler": FrogPixelUpscaler,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogPixelUpscaler": "🐸 Pixel Upscaler",
}
