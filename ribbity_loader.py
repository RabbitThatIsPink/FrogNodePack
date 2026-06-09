import comfy.sd
import comfy.utils
import folder_paths

# ---------------------------------------------------------------------------
# 🐸-Pack — Ribbity Loader
# Combined Diffusion Model + CLIP + VAE loader node.
# Replaces three separate native loader nodes with one.
# ---------------------------------------------------------------------------

class RibbityLoader:
    """
    Loads a diffusion model (unet), a CLIP text encoder, and a VAE in one node.
    Outputs MODEL, CLIP, and VAE as separate tensors so they wire into any
    downstream node just like the native loaders do.
    """

    @classmethod
    def INPUT_TYPES(cls):
        lora_list = ["Empty"] + folder_paths.get_filename_list("loras")
        return {
            "required": {
                "diffusion_model": (folder_paths.get_filename_list("diffusion_models"),),
                "clip_encoder":    (folder_paths.get_filename_list("text_encoders"),),
                "vae_model":       (folder_paths.get_filename_list("vae"),),
                "Turbo_Lora":      (lora_list,),
                "lora_strength":   ("FLOAT", {
                    "default": 1.0,
                    "min": -10.0,
                    "max": 10.0,
                    "step": 0.01,
                    "tooltip": "Strength applied to the selected LoRA. Ignored when Empty.",
                }),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "VAE")
    RETURN_NAMES = ("MODEL", "CLIP", "VAE")
    FUNCTION     = "load_all"
    CATEGORY     = "🐸 Node Pack"

    def load_all(self, diffusion_model, clip_encoder, vae_model,
                 Turbo_Lora, lora_strength):

        # --- Load diffusion model (unet) ---
        unet_path = folder_paths.get_full_path("diffusion_models", diffusion_model)
        model = comfy.sd.load_diffusion_model(unet_path)

        # --- Load CLIP / text encoder ---
        clip_path = folder_paths.get_full_path("text_encoders", clip_encoder)
        clip = comfy.sd.load_clip(ckpt_paths=[clip_path])

        # --- Load VAE ---
        vae_path = folder_paths.get_full_path("vae", vae_model)
        sd  = comfy.utils.load_torch_file(vae_path)
        vae = comfy.sd.VAE(sd=sd)

        # --- Apply Turbo LoRA (if selected) ---
        if Turbo_Lora != "Empty":
            lora_path = folder_paths.get_full_path("loras", Turbo_Lora)
            lora_sd   = comfy.utils.load_torch_file(lora_path, safe_load=True)
            model, clip = comfy.sd.load_lora_for_models(
                model, clip, lora_sd, lora_strength, lora_strength
            )
            print(f"[🐸 Loader] LoRA applied: {Turbo_Lora} @ {lora_strength}")

        return (model, clip, vae)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "FrogLoader": RibbityLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogLoader": "🐸 Load: Model + CLIP + VAE",
}
