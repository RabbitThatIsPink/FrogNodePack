"""
FrogNodePack — Detailer

Runs targeted detail passes on specific regions of an image.

For each enabled region that has a MASK connected:
  1.  Find the bounding box of the mask.
  2.  Expand the box by `padding` pixels on all sides.
  3.  Crop the image to that box.
  4.  Upscale the crop so its shortest side is at least `upscale_to` pixels.
  5.  Append any region-specific prompt text to the positive conditioning
      so the model knows what it is supposed to be improving.
  6.  Encode → sample → decode at the upscaled resolution.
  7.  Downscale the result back to the original crop size.
  8.  Feather-composite only the masked pixels back into the full image.

Three regions: face, hands, body/clothing.
Each region accepts its own prompt text for context-aware conditioning.
"""

import colorsys

import torch
import torch.nn.functional as F
import comfy.sample
import comfy.samplers
import comfy.utils
import latent_preview

_SCHEDULERS = list(comfy.samplers.KSampler.SCHEDULERS)
_SAMPLERS   = list(comfy.samplers.KSampler.SAMPLERS)


# ---------------------------------------------------------------------------
# Mask feathering
# ---------------------------------------------------------------------------

def _feather_mask(mask_2d: torch.Tensor, radius: int) -> torch.Tensor:
    """Gaussian-blur mask edges for smooth compositing. mask_2d: [H, W]"""
    if radius <= 0:
        return mask_2d
    size   = radius * 2 + 1
    sigma  = max(radius / 3.0, 0.1)
    coords = torch.arange(size, dtype=torch.float32, device=mask_2d.device) - radius
    gauss  = torch.exp(-coords ** 2 / (2.0 * sigma ** 2))
    gauss  = gauss / gauss.sum()
    kernel = (gauss.unsqueeze(0) * gauss.unsqueeze(1)).unsqueeze(0).unsqueeze(0)
    m      = mask_2d.unsqueeze(0).unsqueeze(0)
    return F.conv2d(m, kernel, padding=radius).squeeze(0).squeeze(0).clamp(0.0, 1.0)


# ---------------------------------------------------------------------------
# Eye colour auto-detection
# ---------------------------------------------------------------------------

def _normalise_mask_2d(mask, H, W):
    """Normalise any mask shape to [H, W] float32, resizing if needed."""
    if mask.dim() == 2:
        mask = mask.unsqueeze(0)
    mask = mask[:1].float()
    if mask.shape[1] != H or mask.shape[2] != W:
        mask = F.interpolate(
            mask.unsqueeze(1), size=(H, W),
            mode="bilinear", align_corners=False,
        ).squeeze(1)
    return mask[0]


def _sample_face_eye_color(image, mask_2d, padding):
    """
    Estimate the dominant eye colour from the approximate eye band of a face.

    Approach:
      - Compute the face bounding box (same as _inpaint_region).
      - Extract a horizontal band at y: 35–55 % of face height, x: 15–85 % of
        face width — this is where both eyes sit in a forward-facing anime face.
      - Filter out skin (low saturation) and specular highlights (near-white).
      - Take the median hue of the remaining colourful pixels and map it to a
        Danbooru-style eye colour tag.

    image   : [1, H, W, 3]  float32  0-1
    mask_2d : [H, W]        float32
    Returns : str  e.g. "blue eyes"  — or None if detection is uncertain.
    """
    H, W = image.shape[1], image.shape[2]

    hot = mask_2d.gt(0.05).nonzero(as_tuple=False)
    if len(hot) == 0:
        return None

    y1 = max(0, int(hot[:, 0].min()) - padding)
    y2 = min(H, int(hot[:, 0].max()) + padding + 1)
    x1 = max(0, int(hot[:, 1].min()) - padding)
    x2 = min(W, int(hot[:, 1].max()) + padding + 1)

    fH, fW = y2 - y1, x2 - x1
    if fH < 8 or fW < 8:
        return None

    # Eye band
    ey1 = min(H - 1, y1 + int(fH * 0.35))
    ey2 = min(H,     y1 + int(fH * 0.55))
    ex1 = min(W - 1, x1 + int(fW * 0.15))
    ex2 = min(W,     x1 + int(fW * 0.85))
    ey2 = max(ey1 + 1, ey2)
    ex2 = max(ex1 + 1, ex2)

    region = image[0, ey1:ey2, ex1:ex2, :3].reshape(-1, 3).float()

    # Vectorised HSV-style saturation and value
    cmax  = region.max(dim=1).values
    cmin  = region.min(dim=1).values
    delta = cmax - cmin
    sat   = torch.where(cmax > 1e-6, delta / cmax, torch.zeros_like(cmax))
    val   = cmax

    # Keep colourful pixels — exclude skin (low sat), specular (near-white), dark pupils
    keep = (sat > 0.20) & (val > 0.10) & (val < 0.92)
    colored = region[keep]
    if colored.shape[0] < 10:
        return None   # too few colourful pixels → unreliable

    # Median RGB of colourful pixels → single representative colour
    mr = float(colored[:, 0].median())
    mg = float(colored[:, 1].median())
    mb = float(colored[:, 2].median())

    h, s, v = colorsys.rgb_to_hsv(mr, mg, mb)
    h_deg = h * 360.0

    # Brown: warm hue, moderate saturation, darker value
    if 15.0 <= h_deg <= 52.0 and s > 0.25 and v < 0.62:
        return "brown eyes"

    if   h_deg <  15.0 or h_deg >= 345.0: return "red eyes"
    elif h_deg <  35.0:                   return "orange eyes"
    elif h_deg <  70.0:                   return "yellow eyes"
    elif h_deg < 150.0:                   return "green eyes"
    elif h_deg < 195.0:                   return "aqua eyes"
    elif h_deg < 255.0:                   return "blue eyes"
    elif h_deg < 285.0:                   return "purple eyes"
    elif h_deg < 345.0:                   return "pink eyes"
    return None


# ---------------------------------------------------------------------------
# Region-aware conditioning
# ---------------------------------------------------------------------------

def _append_region_prompt(positive, clip, region_text: str):
    """
    Encode `region_text` with CLIP and concatenate it onto every entry in
    `positive` along the sequence dimension.  This gives the model explicit
    context about what region it is detailing without overriding the main
    prompt — the original tokens are still there, just extended.

    Falls back to the original conditioning silently on any error.
    """
    if not region_text or not region_text.strip() or clip is None:
        return positive

    try:
        tokens    = clip.tokenize(region_text)
        extra, _  = clip.encode_from_tokens(tokens, return_pooled=True)
        # extra: [1, seq_extra, dim]

        result = []
        for (base_t, base_m) in positive:
            # Concatenate along the sequence dimension
            combined = torch.cat([base_t, extra], dim=1)
            result.append([combined, base_m])   # keep original metadata (pooled_output etc.)
        return result

    except Exception as e:
        print(f"[🐸 Detailer]  Region prompt encoding failed ({e}) — using base conditioning")
        return positive


# ---------------------------------------------------------------------------
# Core inpaint helper
# ---------------------------------------------------------------------------

def _interp(tensor_nchw, size, mode, antialias):
    """F.interpolate wrapper that handles mode-specific kwargs cleanly."""
    kwargs = {"size": size, "mode": mode}
    if mode in ("bilinear", "bicubic"):
        kwargs["align_corners"] = False
        kwargs["antialias"]     = antialias
    return F.interpolate(tensor_nchw, **kwargs)


def _inpaint_region(image, mask, model, positive, negative, vae,
                    seed, steps, cfg, sampler_name, scheduler, denoise,
                    padding=32, upscale_to=512, feather=16,
                    max_upscale=4.0, min_region_px=48,
                    resize_mode="bicubic", antialias=True):
    """
    Crop → upscale → sample → decode → downscale → feathered composite.

    image         : [1, H, W, 3]  float32  0–1
    mask          : [H, W] or [1, H, W]  float32  0=keep  1=repaint
    max_upscale   : hard cap on the scale factor (prevents tiny crops from being
                    reconstructed near-from-scratch → unrecognisable face fix)
    min_region_px : skip the pass if the shorter bounding-box dimension is below
                    this value; returns image unchanged rather than generating garbage
    Returns: [1, H, W, 3]  float32  0–1
    """
    H, W = image.shape[1], image.shape[2]

    # ── Normalise mask to [1, H, W] ──────────────────────────────────────
    if mask.dim() == 2:
        mask = mask.unsqueeze(0)
    mask = mask[:1].float()

    if mask.shape[1] != H or mask.shape[2] != W:
        mask = F.interpolate(
            mask.unsqueeze(1), size=(H, W),
            mode="bilinear", align_corners=False,
        ).squeeze(1)

    mask_2d = mask[0]  # [H, W]

    # ── Find bounding box ────────────────────────────────────────────────
    hot = mask_2d.gt(0.05).nonzero(as_tuple=False)
    if len(hot) == 0:
        return image

    y1 = max(0, int(hot[:, 0].min()) - padding)
    y2 = min(H, int(hot[:, 0].max()) + padding + 1)
    x1 = max(0, int(hot[:, 1].min()) - padding)
    x2 = min(W, int(hot[:, 1].max()) + padding + 1)

    cH, cW = y2 - y1, x2 - x1

    # ── Minimum region guard ─────────────────────────────────────────────
    # If the crop is too small, skip entirely — a tiny face upscaled 10× will
    # be generated from near-scratch and become unrecognisable.
    if min_region_px > 0 and min(cH, cW) < min_region_px:
        print(f"[🐸 Detailer]  ⚠ Skipping region — crop {cW}×{cH}px is below "
              f"min_region_px ({min_region_px}px). Image passed through unchanged.")
        return image

    # ── Upscale crop ─────────────────────────────────────────────────────
    # Cap the scale factor to avoid extreme reconstruction on small regions.
    # A 48×48 crop at max_upscale=4 → 192×192 (still has signal).
    # A 48×48 crop uncapped at upscale_to=512 → 10.7× (generates a new face).
    natural_scale = upscale_to / min(cH, cW)
    scale = min(max(1.0, natural_scale), max_upscale)
    tH    = ((max(int(round(cH * scale)), 8) + 7) // 8) * 8
    tW    = ((max(int(round(cW * scale)), 8) + 7) // 8) * 8

    crop_img  = image[:, y1:y2, x1:x2, :]
    crop_mask = mask_2d[y1:y2, x1:x2]

    if tH != cH or tW != cW:
        crop_up = _interp(
            crop_img.permute(0, 3, 1, 2), (tH, tW), resize_mode, antialias,
        ).permute(0, 2, 3, 1).clamp(0.0, 1.0)
    else:
        crop_up = crop_img

    # ── Encode ───────────────────────────────────────────────────────────
    latent_samples = vae.encode(crop_up[:, :, :, :3])
    latent_samples = comfy.sample.fix_empty_latent_channels(model, latent_samples)

    # ── Sample ───────────────────────────────────────────────────────────
    #
    # We always use sample_custom with manually-built sigmas so that
    # denoise < 1.0 is correctly honoured for every scheduler.
    # comfy.sample.sample() does not accept a denoise kwarg — it would be
    # silently discarded, making every pass run at full noise regardless.
    #
    noise    = comfy.sample.prepare_noise(latent_samples, seed)
    callback = latent_preview.prepare_callback(model, steps)

    model_sampling = model.get_model_object("model_sampling")
    total_steps    = steps if denoise >= 1.0 else max(int(steps / denoise), steps + 1)

    if scheduler == "beta57":
        sigmas = comfy.samplers.beta_scheduler(model_sampling, total_steps, alpha=0.5, beta=0.7)
    else:
        sigmas = comfy.samplers.calculate_sigmas(model_sampling, scheduler, total_steps)

    sigmas  = sigmas[-(steps + 1):].to(latent_samples.device)
    sampler = comfy.samplers.sampler_object(sampler_name)

    samples = comfy.sample.sample_custom(
        model, noise, cfg, sampler, sigmas,
        positive, negative, latent_samples,
        callback     = callback,
        disable_pbar = not comfy.utils.PROGRESS_BAR_ENABLED,
        seed         = seed,
    )

    # ── Decode ───────────────────────────────────────────────────────────
    decoded = vae.decode(samples)

    while decoded.dim() > 4:
        decoded = decoded.squeeze(0)
    if decoded.dim() == 3:
        decoded = decoded.unsqueeze(0)
    decoded = decoded.float()

    # Ensure decoded matches upscaled crop size
    if decoded.shape[1] != tH or decoded.shape[2] != tW:
        decoded = F.interpolate(
            decoded.permute(0, 3, 1, 2), size=(tH, tW),
            mode="bilinear", align_corners=False,
        ).permute(0, 2, 3, 1)

    # ── Downscale back to original crop size ─────────────────────────────
    if tH != cH or tW != cW:
        decoded = _interp(
            decoded.permute(0, 3, 1, 2), (cH, cW), resize_mode, antialias,
        ).permute(0, 2, 3, 1)

    decoded = decoded.clamp(0.0, 1.0)

    # ── Feathered composite ───────────────────────────────────────────────
    crop_mask_f = _feather_mask(crop_mask, feather)
    mask_region = crop_mask_f.unsqueeze(0).unsqueeze(-1).expand_as(crop_img)
    blended     = crop_img * (1.0 - mask_region) + decoded * mask_region

    result = image.clone().float()
    result[:, y1:y2, x1:x2, :] = blended
    return result


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class FrogDetailer:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image":        ("IMAGE",),
                "seed":         ("INT",   {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps":        ("INT",   {"default": 12, "min": 1, "max": 150,
                                          "tooltip": "ANIMA: 8–15 steps is sufficient. Higher has diminishing returns."}),
                "cfg":          ("FLOAT", {"default": 2.0, "min": 0.0, "max": 30.0, "step": 0.1,
                                           "tooltip": "ANIMA: 1.5–3.0 with er_sde. Higher CFG risks over-saturation."}),
                "sampler_name": (_SAMPLERS,   {"default": "er_sde"}),
                "scheduler":    (_SCHEDULERS, {"default": "beta57"}),
                "upscale_to":   ([512, 768, 1024, 1536], {"default": 512}),
                "padding":      ("INT", {"default": 32,  "min": 0, "max": 256, "step": 8,
                                         "tooltip": "Extra pixels around the mask bounding box."}),
                "feather":      ("INT", {"default": 8,   "min": 0, "max": 128, "step": 4,
                                         "tooltip": "ANIMA: 5–10 is sufficient. 16+ can blur seams too much."}),
                "max_upscale_ratio": ("FLOAT", {"default": 4.0, "min": 1.0, "max": 16.0, "step": 0.5,
                                         "tooltip":
                                             "Hard cap on how many times a crop can be enlarged.\n"
                                             "A 48×48 face at 4× → 192×192 (safe).\n"
                                             "Without a cap, a 48×48 face at upscale_to=512 → 10.7× "
                                             "— the model generates a new face from near-scratch.\n"
                                             "Lower = safer faces. Higher = allows more detail on genuinely small regions."}),
                "min_region_px":     ("INT",   {"default": 48,  "min": 0,   "max": 512,  "step": 8,
                                         "tooltip":
                                             "If the shorter side of a region's bounding box is below this many pixels, "
                                             "skip that pass entirely and leave the image unchanged.\n"
                                             "Prevents near-invisible faces from being over-processed.\n"
                                             "Set to 0 to disable."}),
                "resize_mode": (["bicubic", "bilinear", "area", "nearest"], {
                                         "default": "bicubic",
                                         "tooltip":
                                             "Interpolation used when scaling the crop up before sampling "
                                             "and back down after decoding.\n"
                                             "bicubic  — sharpest, recommended.\n"
                                             "bilinear — softer, faster.\n"
                                             "area     — best for pure downscaling (averages pixels).\n"
                                             "nearest  — no smoothing, pixelated."}),
                "antialias": ("BOOLEAN", {"default": True,
                                         "tooltip":
                                             "Apply antialiasing when resizing (bicubic / bilinear only).\n"
                                             "Reduces ringing and aliasing on sharp edges.\n"
                                             "Has no effect with area or nearest modes."}),
                # ── Face ──────────────────────────────────────────────────
                "face_enabled":     ("BOOLEAN", {"default": True}),
                "face_denoise":     ("FLOAT",   {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "auto_eye_color":   ("BOOLEAN", {"default": True,
                                        "tooltip":
                                            "Before each face pass, sample the dominant eye colour from the "
                                            "source image and prepend it to the face conditioning.\n"
                                            "Prevents left/right eye colour drift and stops two characters' "
                                            "eye colours from bleeding into each other when separate masks are used.\n"
                                            "Each face mask is sampled independently."}),
                # ── Hands ─────────────────────────────────────────────────
                "hands_enabled": ("BOOLEAN", {"default": True}),
                "hands_denoise": ("FLOAT",   {"default": 0.40, "min": 0.0, "max": 1.0, "step": 0.01}),
                # ── Body / clothing ───────────────────────────────────────
                "body_enabled":  ("BOOLEAN", {"default": False}),
                "body_denoise":  ("FLOAT",   {"default": 0.30, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": {
                "basic_pipe": ("BASIC_PIPE", {
                    "tooltip": "Overrides model/clip/vae/positive/negative when connected.",
                }),
                "model":    ("MODEL",),
                "clip":     ("CLIP",  {
                    "tooltip": "Required for region prompts to work. "
                               "Extracted automatically from basic_pipe if connected.",
                }),
                "vae":      ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                # ── Masks ─────────────────────────────────────────────────
                "face_mask":  ("MASK",),
                "face_mask_2": ("MASK", {
                    "tooltip": "Second character's face mask. Processed as a separate isolated pass — "
                               "no shared crop context with face_mask. Eye colour sampled independently."
                }),
                "face_mask_3": ("MASK", {
                    "tooltip": "Third character's face mask. Same isolation as face_mask_2."
                }),
                "hands_mask": ("MASK",),
                "body_mask":  ("MASK",),
                # ── Region-specific prompt context ─────────────────────────
                "face_prompt": ("STRING", {
                    "default":   "detailed face, detailed eyes, symmetrical eyes, sharp iris, clean linework, high quality",
                    "multiline": True,
                    "tooltip":   "Extra positive text appended to the conditioning for the face pass only.\n"
                                 "Eye colour is prepended automatically when auto_eye_color is on — don't add it here.",
                }),
                "hands_prompt": ("STRING", {
                    "default":   "detailed hands, five fingers, correct finger anatomy, clean fingernails, no extra fingers",
                    "multiline": True,
                    "tooltip":   "Extra positive text for the hands pass.",
                }),
                "body_prompt": ("STRING", {
                    "default":   "detailed clothing, fabric texture, clean linework, high quality",
                    "multiline": True,
                    "tooltip":   "Extra positive text for the body/clothing pass.",
                }),
            },
        }

    RETURN_TYPES    = ("IMAGE", "STRING")
    RETURN_NAMES    = ("image", "debug")
    FUNCTION        = "detail"
    CATEGORY        = "🐸 Node Pack"

    def detail(self, image, seed, steps, cfg, sampler_name, scheduler,
               upscale_to, padding, feather,
               max_upscale_ratio, min_region_px,
               resize_mode, antialias,
               face_enabled,  face_denoise,  auto_eye_color,
               hands_enabled, hands_denoise,
               body_enabled,  body_denoise,
               basic_pipe=None, model=None, clip=None, vae=None,
               positive=None, negative=None,
               face_mask=None, face_mask_2=None, face_mask_3=None,
               hands_mask=None, body_mask=None,
               face_prompt="", hands_prompt="", body_prompt=""):

        upscale_to = int(upscale_to)

        # Pipe provides model, clip, vae, positive, negative together
        if basic_pipe is not None:
            model, clip, vae, positive, negative = basic_pipe

        if model is None or vae is None or positive is None or negative is None:
            raise ValueError(
                "[🐸 Detailer] Connect either basic_pipe or individual "
                "model / vae / positive / negative inputs."
            )

        if clip is None:
            print("[🐸 Detailer]  ⚠ No CLIP — region prompts will be ignored.")

        result      = image.clone().float()
        debug_lines = []
        H, W        = result.shape[1], result.shape[2]

        # ── Build face passes (up to 3 independent masks) ────────────────
        face_passes = []
        if face_enabled:
            for i, fmask in enumerate([face_mask, face_mask_2, face_mask_3], 1):
                if fmask is None:
                    continue
                if isinstance(fmask, torch.Tensor) and fmask.max() < 0.01:
                    # Zero mask from Mask Batch Split when fewer than 3 faces present
                    continue
                label = "face" if i == 1 else f"face {i}"
                face_passes.append((label, fmask))

        regions = []
        for label, fmask in face_passes:
            regions.append((label, True, fmask, face_denoise, face_prompt, True))
        regions += [
            ("hands",         hands_enabled, hands_mask, hands_denoise, hands_prompt, False),
            ("body/clothing", body_enabled,  body_mask,  body_denoise,  body_prompt,  False),
        ]

        ran = []
        for name, enabled, mask, denoise, region_prompt, is_face in regions:
            if not enabled:
                debug_lines.append(f"{name}: disabled")
                continue
            if mask is None:
                msg = f"{name}: ⚠ no mask — skipped"
                debug_lines.append(msg)
                print(f"[🐸 Detailer]  {msg}")
                continue

            # ── Eye colour auto-lock (face passes only) ───────────────────
            actual_prompt = region_prompt
            if is_face and auto_eye_color:
                m2d       = _normalise_mask_2d(mask, H, W)
                color_tag = _sample_face_eye_color(result, m2d, padding)
                if color_tag:
                    actual_prompt = (f"{color_tag}, {region_prompt}".strip(", ")
                                     if region_prompt else color_tag)
                    print(f"[🐸 Detailer]  {name}: auto eye colour → {color_tag}")
                    debug_lines.append(f"{name}: auto eye colour = {color_tag}")
                else:
                    debug_lines.append(f"{name}: auto eye colour = uncertain (skipped)")

            has_prompt = bool(actual_prompt and actual_prompt.strip())
            msg = (f"{name}: denoise={denoise}  upscale={upscale_to}"
                   + (f"  prompt='{actual_prompt[:40]}…'" if has_prompt else "  no region prompt"))
            debug_lines.append(msg)
            print(f"[🐸 Detailer]  {msg}")

            region_positive = _append_region_prompt(positive, clip, actual_prompt)

            result = _inpaint_region(
                result, mask, model, region_positive, negative, vae,
                seed, steps, cfg, sampler_name, scheduler, denoise,
                padding=padding, upscale_to=upscale_to, feather=feather,
                max_upscale=max_upscale_ratio, min_region_px=min_region_px,
                resize_mode=resize_mode, antialias=antialias,
            )
            ran.append(name)

        summary = ("Ran: " + ", ".join(ran)) if ran else (
            "⚠ PASSTHROUGH — wire a MASK into face_mask / hands_mask / body_mask."
        )
        debug_lines.append(summary)
        print(f"[🐸 Detailer]  {summary}")

        return (result, "\n".join(debug_lines))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS      = {"FrogDetailer": FrogDetailer}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogDetailer": "🐸 Detailer"}
