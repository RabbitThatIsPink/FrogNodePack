"""
FrogNodePack — Loader with Model Name

Extends 🐸 Load: Model + CLIP + VAE with a model_name STRING output.
The model_name is the filename stem of the selected diffusion model
(e.g. "ANIMA_beta57_v3" from "ANIMA_beta57_v3.safetensors").

Wire model_name → 🐸 Load Library by Name to automatically load the
matching Library entry's quality prompts and LoRAs.
"""
from __future__ import annotations
from pathlib import Path

import comfy.sd
import comfy.utils
import folder_paths


class FrogLoaderWithLibrary:
    """
    🐸 Load: Model + CLIP + VAE + Name

    Identical to 🐸 Load: Model + CLIP + VAE, plus a model_name STRING output.
    The name is the diffusion model filename stem — wire it to
    🐸 Load Library by Name to auto-select quality prompts and LoRAs.
    """

    @classmethod
    def INPUT_TYPES(cls):
        lora_list = ["Empty"] + folder_paths.get_filename_list("loras")
        return {
            "required": {
                "diffusion_model": (folder_paths.get_filename_list("diffusion_models"), {
                    "tooltip":
                        "Filename stem is output as model_name.\n"
                        "Wire model_name → 🐸 Load Library by Name to auto-load\n"
                        "the matching Library entry.",
                }),
                "clip_encoder":  (folder_paths.get_filename_list("text_encoders"),),
                "vae_model":     (folder_paths.get_filename_list("vae"),),
                "Turbo_Lora":    (lora_list,),
                "lora_strength": ("FLOAT", {
                    "default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01,
                    "tooltip": "Strength applied to the Turbo LoRA. Ignored when Empty.",
                }),
            },
        }

    RETURN_TYPES  = ("MODEL", "CLIP", "VAE", "STRING")
    RETURN_NAMES  = ("MODEL", "CLIP", "VAE", "model_name")
    FUNCTION      = "load_all"
    CATEGORY      = "🐸 Node Pack/Utility"
    OUTPUT_TOOLTIPS = (
        "Diffusion model with Turbo LoRA applied.",
        "CLIP encoder.",
        "VAE.",
        "Diffusion model filename stem — wire to 🐸 Load Library by Name.",
    )

    def load_all(self, diffusion_model, clip_encoder, vae_model,
                 Turbo_Lora, lora_strength):

        unet_path = folder_paths.get_full_path("diffusion_models", diffusion_model)
        model     = comfy.sd.load_diffusion_model(unet_path)

        clip_path = folder_paths.get_full_path("text_encoders", clip_encoder)
        clip      = comfy.sd.load_clip(ckpt_paths=[clip_path])

        vae_path = folder_paths.get_full_path("vae", vae_model)
        vae      = comfy.sd.VAE(sd=comfy.utils.load_torch_file(vae_path))

        if Turbo_Lora != "Empty":
            lora_path = folder_paths.get_full_path("loras", Turbo_Lora)
            lora_sd   = comfy.utils.load_torch_file(lora_path, safe_load=True)
            model, clip = comfy.sd.load_lora_for_models(
                model, clip, lora_sd, lora_strength, lora_strength,
            )
            print(f"[🐸 Loader] Turbo LoRA: {Turbo_Lora} @ {lora_strength}")

        model_name = Path(diffusion_model).stem
        print(f"[🐸 Loader] model_name = '{model_name}'")
        return (model, clip, vae, model_name)


# ── Registration ──────────────────────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "FrogLoaderWithLibrary": FrogLoaderWithLibrary,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogLoaderWithLibrary": "🐸 Load: Model + CLIP + VAE + Name",
}
