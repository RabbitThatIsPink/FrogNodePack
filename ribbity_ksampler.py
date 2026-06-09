import torch
import comfy.sample
import comfy.samplers
import comfy.utils
import latent_preview

# ---------------------------------------------------------------------------
# 🐸-Pack — Ribbity KSampler
# ---------------------------------------------------------------------------

def _inject_beta57():
    schedulers = comfy.samplers.KSampler.SCHEDULERS
    if "beta57" not in schedulers:
        try:
            idx = schedulers.index("beta")
            schedulers.insert(idx + 1, "beta57")
        except ValueError:
            schedulers.append("beta57")

_inject_beta57()

_SCHEDULERS = list(comfy.samplers.KSampler.SCHEDULERS)
_SAMPLERS   = list(comfy.samplers.KSampler.SAMPLERS)


class RibbityKSampler:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed":         ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xFFFFFFFFFFFFFFFF,
                }),
                "steps":        ("INT",   {"default": 30,  "min": 1,   "max": 10000}),
                "cfg":          ("FLOAT", {"default": 4.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "sampler_name": (_SAMPLERS,),
                "scheduler":    (_SCHEDULERS,),
                "latent_image": ("LATENT",),
                "denoise":      ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "tile_size":    ("INT",   {"default": 512, "min": 256, "max": 2048, "step": 64,
                                           "tooltip": "Tile size for tiled VAE decode only."}),
                "Tiled":        ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "basic_pipe": ("BASIC_PIPE", {
                    "tooltip": "When connected, overrides model/positive/negative/vae inputs. "
                               "Compatible with Impact Pack's ToBasicPipe / 🐸 Pipe In.",
                }),
                "model":    ("MODEL",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "vae":      ("VAE",),
            },
        }

    RETURN_TYPES  = ("LATENT", "IMAGE", "STRING")
    RETURN_NAMES  = ("latent", "Image", "debug")
    FUNCTION      = "sample"
    CATEGORY      = "🐸 Node Pack"

    def sample(self, seed, steps, cfg, sampler_name, scheduler,
               latent_image, denoise, tile_size, Tiled,
               basic_pipe=None, model=None, positive=None, negative=None, vae=None):

        # Pipe overrides individual inputs when connected
        if basic_pipe is not None:
            model, _clip, vae, positive, negative = basic_pipe

        if model is None or vae is None or positive is None or negative is None:
            raise ValueError(
                "[🐸 KSampler] Connect either basic_pipe or individual "
                "model / vae / positive / negative inputs."
            )

        if scheduler == "beta57":
            latent_out = self._sample_beta57(
                model, seed, steps, cfg, sampler_name,
                positive, negative, latent_image, denoise
            )
        else:
            latent_out = self._common_sample(
                model, seed, steps, cfg, sampler_name, scheduler,
                positive, negative, latent_image, denoise
            )

        samples = latent_out["samples"]
        decoded = []
        for i in range(samples.shape[0]):
            single = samples[i:i+1]
            if Tiled:
                img = vae.decode_tiled(single, tile_x=tile_size, tile_y=tile_size)
            else:
                img = vae.decode(single)
            while img.dim() > 4:
                img = img.squeeze(0)
            if img.dim() == 3:
                img = img.unsqueeze(0)
            decoded.append(img)
        image = torch.cat(decoded, dim=0).clamp(0.0, 1.0).float()

        # DEBUG — remove this block when done
        debug_lines = [
            "seed=" + str(seed),
            "shape=" + str(tuple(image.shape)),
            "dtype=" + str(image.dtype),
            "min=" + "{:.4f}".format(image.min().item()),
            "max=" + "{:.4f}".format(image.max().item()),
        ]
        debug = "\n".join(debug_lines)
        # END DEBUG

        return (latent_out, image, debug)

    def _common_sample(self, model, seed, steps, cfg, sampler_name, scheduler,
                       positive, negative, latent_image, denoise):
        latent     = latent_image["samples"]
        latent     = comfy.sample.fix_empty_latent_channels(model, latent)
        batch_inds = latent_image.get("batch_index", None)
        noise      = comfy.sample.prepare_noise(latent, seed, batch_inds)
        noise_mask = latent_image.get("noise_mask", None)
        callback   = latent_preview.prepare_callback(model, steps)

        samples = comfy.sample.sample(
            model, noise, steps, cfg, sampler_name, scheduler,
            positive, negative, latent,
            denoise=denoise,
            disable_noise=False,
            start_step=None,
            last_step=None,
            force_full_denoise=True,
            noise_mask=noise_mask,
            callback=callback,
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED,
            seed=seed,
        )

        out = latent_image.copy()
        out["samples"] = samples
        return out

    def _sample_beta57(self, model, seed, steps, cfg, sampler_name,
                       positive, negative, latent_image, denoise):
        model_sampling = model.get_model_object("model_sampling")

        total_steps = steps
        if denoise < 1.0:
            total_steps = max(int(steps / denoise), 1)

        sigmas = comfy.samplers.beta_scheduler(
            model_sampling, total_steps, alpha=0.5, beta=0.7
        )
        sigmas = sigmas[-(steps + 1):]

        latent     = latent_image["samples"]
        latent     = comfy.sample.fix_empty_latent_channels(model, latent)
        batch_inds = latent_image.get("batch_index", None)
        noise      = comfy.sample.prepare_noise(latent, seed, batch_inds)
        callback   = latent_preview.prepare_callback(model, steps)
        noise_mask = latent_image.get("noise_mask", None)
        sampler    = comfy.samplers.sampler_object(sampler_name)

        samples = comfy.sample.sample_custom(
            model, noise, cfg, sampler, sigmas,
            positive, negative, latent,
            noise_mask=noise_mask,
            callback=callback,
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED,
            seed=seed,
        )

        out = latent_image.copy()
        out["samples"] = samples
        return out


NODE_CLASS_MAPPINGS = {
    "FrogKSampler": RibbityKSampler,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogKSampler": "🐸 KSampler",
}
