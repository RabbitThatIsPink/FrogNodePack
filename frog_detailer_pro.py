"""
FrogNodePack — Detailer Pro

Two-pass regional detailer built specifically for ANIMA (anime/illustration,
non-SDXL models). No ControlNet dependency.

What makes it different from 🐸 Detailer:

  TWO-PASS PER REGION
    Pass 1 (fix)    — higher denoise, corrects anatomy and structure
    Pass 2 (refine) — low denoise on the already-fixed result, sharpens detail
                      without breaking what pass 1 corrected

  PER-REGION NEGATIVE PROMPTS
    Each region (face / hands / body) appends region-specific anatomy terms
    to the negative conditioning. Defaults target the most common ANIMA
    failure modes: cross-eyes, extra fingers, bad anatomy per body part.

  MASK DILATION
    Expands each mask outward N pixels before cropping so the model sees
    enough surrounding context. Body parts especially need this.

  POST-DECODE SHARPENING
    Unsharp mask applied to the decoded result before compositing back.
    Counters VAE encode/decode softness.

  AUTO EYE COLOUR LOCK
    Samples the dominant eye colour per face mask from the source image
    and prepends the Danbooru colour tag to each face pass independently.
    Multi-character safe — each mask is sampled separately.

  UP TO THREE FACE MASKS
    face_mask / face_mask_2 / face_mask_3 for separate character passes.
    Zero masks from 🐸 Mask Batch Split are skipped automatically.
"""

import colorsys
import torch
import torch.nn.functional as F
import comfy.sample
import comfy.samplers
import comfy.utils
import latent_preview

from .frog_detailer import (
    _normalise_mask_2d,
    _sample_face_eye_color,
    _append_region_prompt,
    _feather_mask,
    _interp,
)

_SCHEDULERS = list(comfy.samplers.KSampler.SCHEDULERS)
_SAMPLERS   = list(comfy.samplers.KSampler.SAMPLERS)

# ── Per-region prompt defaults ────────────────────────────────────────────────

_FACE_POS  = "detailed face, detailed eyes, symmetrical eyes, sharp iris, clean linework, high quality"
_FACE_NEG  = "asymmetrical eyes, crossed eyes, heterochromia, bad face, fused face, poorly drawn face, extra eyes, missing eyes, off-model face, nipples, breast, areola, genitals, body parts"
_HANDS_POS = "detailed hands, five fingers, correct finger anatomy, clean fingernails, no extra fingers"
_HANDS_NEG = "extra fingers, fused fingers, malformed hands, too many fingers, missing fingers, bad hands, mutated hands, six fingers, four fingers, nipples, breast, areola, nipple, genitals, penis, vagina, nude body parts, body"
_BODY_POS  = "detailed body, correct anatomy, clean linework, high quality"
_BODY_NEG  = "bad anatomy, malformed, extra limbs, missing limbs, fused body parts, distorted anatomy, poorly drawn body"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dilate_mask(mask_2d: torch.Tensor, pixels: int) -> torch.Tensor:
    """Morphological dilation via max-pool. mask_2d: [H, W] → [H, W]."""
    if pixels <= 0:
        return mask_2d
    ks = pixels * 2 + 1
    m  = mask_2d.unsqueeze(0).unsqueeze(0)
    return F.max_pool2d(m, kernel_size=ks, stride=1, padding=pixels) \
             .squeeze(0).squeeze(0).clamp(0.0, 1.0)


def _face_quality_score(image_nhwc: torch.Tensor, mask_2d: torch.Tensor, padding: int) -> float:
    """
    Measure face region sharpness using mean Sobel gradient magnitude.
    Higher value = sharper / more detailed face.
    Returns float ≥ 0.  Typical well-drawn ANIMA range: 0.02–0.08.
    """
    H, W = image_nhwc.shape[1], image_nhwc.shape[2]
    hot  = mask_2d.gt(0.05).nonzero(as_tuple=False)
    if len(hot) == 0:
        return 0.0

    y1 = max(0, int(hot[:, 0].min()) - padding)
    y2 = min(H, int(hot[:, 0].max()) + padding + 1)
    x1 = max(0, int(hot[:, 1].min()) - padding)
    x2 = min(W, int(hot[:, 1].max()) + padding + 1)

    crop = image_nhwc[0, y1:y2, x1:x2, :3]                # [cH, cW, 3]
    gray = (0.299 * crop[:, :, 0]
            + 0.587 * crop[:, :, 1]
            + 0.114 * crop[:, :, 2])                        # [cH, cW]
    gray = gray.unsqueeze(0).unsqueeze(0)                   # [1, 1, cH, cW]

    dev = image_nhwc.device
    kx = torch.tensor([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]],
                       dtype=torch.float32, device=dev).unsqueeze(0).unsqueeze(0)
    ky = torch.tensor([[-1, -2, -1], [0, 0, 0], [1, 2, 1]],
                       dtype=torch.float32, device=dev).unsqueeze(0).unsqueeze(0)

    gx = F.conv2d(gray, kx, padding=1)
    gy = F.conv2d(gray, ky, padding=1)
    return float((gx ** 2 + gy ** 2).sqrt().mean())


def _unsharp(image_nhwc: torch.Tensor, strength: float) -> torch.Tensor:
    """Unsharp mask sharpening in pixel space. image_nhwc: [1, H, W, 3]."""
    if strength <= 0.0:
        return image_nhwc
    t      = image_nhwc.permute(0, 3, 1, 2)          # [1, 3, H, W]
    ks     = 5
    sigma  = 1.0
    coords = torch.arange(ks, dtype=torch.float32, device=t.device) - ks // 2
    gauss  = torch.exp(-coords ** 2 / (2.0 * sigma ** 2))
    gauss  = gauss / gauss.sum()
    kernel = (gauss.unsqueeze(0) * gauss.unsqueeze(1)) \
                .unsqueeze(0).unsqueeze(0) \
                .expand(3, 1, ks, ks).contiguous()
    blurred   = F.conv2d(t, kernel, padding=ks // 2, groups=3)
    sharpened = (t + strength * (t - blurred)).clamp(0.0, 1.0)
    return sharpened.permute(0, 2, 3, 1)


def _inpaint_region(
    image, mask, model, positive, negative, vae,
    seed, steps, cfg, sampler_name, scheduler, denoise,
    padding, upscale_to, feather,
    max_upscale, min_region_px,
    resize_mode, antialias,
    mask_dilation, sharpen,
):
    """
    Crop → dilate → upscale → encode → sample → decode → downscale →
    sharpen → feathered composite.
    Returns [1, H, W, 3] float32.
    """
    H, W = image.shape[1], image.shape[2]

    # ── Normalise mask ────────────────────────────────────────────────────
    if mask.dim() == 2:
        mask = mask.unsqueeze(0)
    mask = mask[:1].float()
    if mask.shape[1] != H or mask.shape[2] != W:
        mask = F.interpolate(
            mask.unsqueeze(1), size=(H, W),
            mode="bilinear", align_corners=False,
        ).squeeze(1)
    mask_2d = mask[0]

    # ── Dilation ──────────────────────────────────────────────────────────
    if mask_dilation > 0:
        mask_2d = _dilate_mask(mask_2d, mask_dilation)

    # ── Bounding box ──────────────────────────────────────────────────────
    hot = mask_2d.gt(0.05).nonzero(as_tuple=False)
    if len(hot) == 0:
        return image

    y1 = max(0, int(hot[:, 0].min()) - padding)
    y2 = min(H, int(hot[:, 0].max()) + padding + 1)
    x1 = max(0, int(hot[:, 1].min()) - padding)
    x2 = min(W, int(hot[:, 1].max()) + padding + 1)
    cH, cW = y2 - y1, x2 - x1

    # ── Minimum region guard ──────────────────────────────────────────────
    if min_region_px > 0 and min(cH, cW) < min_region_px:
        print(f"[🐸 Detailer Pro]  ⚠ {cW}×{cH}px < min_region_px ({min_region_px}) — skipped")
        return image

    # ── Upscale crop ──────────────────────────────────────────────────────
    natural_scale = upscale_to / min(cH, cW)
    scale = min(max(1.0, natural_scale), max_upscale)
    tH = ((max(int(round(cH * scale)), 8) + 7) // 8) * 8
    tW = ((max(int(round(cW * scale)), 8) + 7) // 8) * 8

    crop_img  = image[:, y1:y2, x1:x2, :]
    crop_mask = mask_2d[y1:y2, x1:x2]

    if tH != cH or tW != cW:
        crop_up = _interp(
            crop_img.permute(0, 3, 1, 2), (tH, tW), resize_mode, antialias,
        ).permute(0, 2, 3, 1).clamp(0.0, 1.0)
    else:
        crop_up = crop_img

    # ── Encode ────────────────────────────────────────────────────────────
    latent = vae.encode(crop_up[:, :, :, :3])
    latent = comfy.sample.fix_empty_latent_channels(model, latent)

    # ── Sample ────────────────────────────────────────────────────────────
    noise    = comfy.sample.prepare_noise(latent, seed)
    callback = latent_preview.prepare_callback(model, steps)

    model_sampling = model.get_model_object("model_sampling")
    total_steps    = steps if denoise >= 1.0 else max(int(steps / denoise), steps + 1)

    if scheduler == "beta57":
        sigmas = comfy.samplers.beta_scheduler(model_sampling, total_steps, alpha=0.5, beta=0.7)
    else:
        sigmas = comfy.samplers.calculate_sigmas(model_sampling, scheduler, total_steps)

    sigmas  = sigmas[-(steps + 1):].to(latent.device)
    sampler = comfy.samplers.sampler_object(sampler_name)

    samples = comfy.sample.sample_custom(
        model, noise, cfg, sampler, sigmas,
        positive, negative, latent,
        callback     = callback,
        disable_pbar = not comfy.utils.PROGRESS_BAR_ENABLED,
        seed         = seed,
    )

    # ── Decode ────────────────────────────────────────────────────────────
    decoded = vae.decode(samples)
    while decoded.dim() > 4:
        decoded = decoded.squeeze(0)
    if decoded.dim() == 3:
        decoded = decoded.unsqueeze(0)
    decoded = decoded.float()

    if decoded.shape[1] != tH or decoded.shape[2] != tW:
        decoded = _interp(
            decoded.permute(0, 3, 1, 2), (tH, tW), resize_mode, antialias,
        ).permute(0, 2, 3, 1)

    if tH != cH or tW != cW:
        decoded = _interp(
            decoded.permute(0, 3, 1, 2), (cH, cW), resize_mode, antialias,
        ).permute(0, 2, 3, 1)

    decoded = decoded.clamp(0.0, 1.0)

    # ── Sharpen ───────────────────────────────────────────────────────────
    if sharpen > 0.0:
        decoded = _unsharp(decoded, sharpen)

    # ── Feathered composite ───────────────────────────────────────────────
    crop_mask_f = _feather_mask(crop_mask, feather)
    alpha       = crop_mask_f.unsqueeze(0).unsqueeze(-1).expand_as(crop_img)
    blended     = crop_img * (1.0 - alpha) + decoded * alpha

    result = image.clone()
    result[:, y1:y2, x1:x2, :] = blended
    return result


# ── Node ──────────────────────────────────────────────────────────────────────

class FrogDetailerPro:
    """
    🐸 Detailer Pro

    Two-pass regional inpainting for ANIMA (anime/illustration models).

    Each enabled region runs:
      Pass 1 — fix    (higher denoise) : corrects anatomy, structure, proportions
      Pass 2 — refine (low denoise)    : sharpens detail on the already-fixed result

    Per-region negatives, mask dilation, and unsharp sharpening are included.
    Auto eye colour locks detected colour per face pass to prevent drift.

    Wire: 🐸 Florence2+SAM Masker → [🐸 Mask Batch Split →] 🐸 Detailer Pro
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # ── Sampling ───────────────────────────────────────────────
                "image":        ("IMAGE",),
                "seed":         ("INT",   {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps":        ("INT",   {"default": 12, "min": 1, "max": 150,
                                           "tooltip": "ANIMA: 8–15 is sufficient."}),
                "cfg":          ("FLOAT", {"default": 2.0, "min": 0.0, "max": 30.0, "step": 0.1,
                                           "tooltip": "ANIMA: 1.5–3.0 with er_sde."}),
                "sampler_name": (_SAMPLERS,   {"default": "er_sde"}),
                "scheduler":    (_SCHEDULERS, {"default": "beta57"}),

                # ── Crop / resize ──────────────────────────────────────────
                "upscale_to":        ([512, 768, 1024, 1536], {"default": 512}),
                "padding":           ("INT",   {"default": 32, "min": 0, "max": 256, "step": 8}),
                "feather":           ("INT",   {"default": 8,  "min": 0, "max": 128, "step": 4}),
                "max_upscale_ratio": ("FLOAT", {"default": 4.0, "min": 1.0, "max": 16.0, "step": 0.5,
                                                "tooltip": "Hard cap on crop scale factor. Prevents tiny regions being generated from scratch."}),
                "min_region_px":     ("INT",   {"default": 48, "min": 0, "max": 512, "step": 8,
                                                "tooltip": "Skip regions whose shorter dimension is below this. Set 0 to disable."}),
                "resize_mode":  (["bicubic", "bilinear", "area", "nearest"], {"default": "bicubic"}),
                "antialias":    ("BOOLEAN", {"default": True,
                                             "tooltip": "Antialiasing for bicubic/bilinear. No effect on area/nearest."}),

                # ── Pre-upscale ────────────────────────────────────────────
                "pre_upscale": ("FLOAT", {"default": 1.0, "min": 1.0, "max": 4.0, "step": 0.25,
                                           "tooltip":
                                               "Upscale the full image by this factor before detailing,\n"
                                               "then downscale back to original resolution after all passes.\n"
                                               "Makes small features (nipples, small hands) large enough\n"
                                               "for the model to refine rather than hallucinate.\n"
                                               "1.0 = off.  2.0 recommended for body features."}),

                # ── Quality ────────────────────────────────────────────────
                "mask_dilation": ("INT",   {"default": 6,   "min": 0, "max": 64, "step": 2,
                                            "tooltip": "Expand each mask outward N pixels before cropping. Gives the model more context."}),
                "sharpen":       ("FLOAT", {"default": 0.4, "min": 0.0, "max": 3.0, "step": 0.1,
                                            "tooltip": "Unsharp mask strength applied after decode. Counters VAE softness. 0 = off."}),

                # ── Two-pass ───────────────────────────────────────────────
                "two_pass":       ("BOOLEAN", {"default": True,
                                               "tooltip":
                                                   "Run two inpaint passes per region.\n"
                                                   "Pass 1 (fix)    — main denoise, corrects structure.\n"
                                                   "Pass 2 (refine) — refine_denoise, sharpens detail."}),
                "refine_denoise": ("FLOAT",   {"default": 0.20, "min": 0.0, "max": 1.0, "step": 0.01,
                                               "tooltip": "Denoise for the refinement pass. Typically 0.15–0.25."}),

                # ── Face ───────────────────────────────────────────────────
                "face_enabled":   ("BOOLEAN", {"default": True}),
                "face_denoise":   ("FLOAT",   {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01}),
                "auto_eye_color": ("BOOLEAN", {"default": True,
                                               "tooltip": "Detect dominant eye colour per face mask and prepend it to face conditioning."}),
                "face_skip_threshold": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 0.20, "step": 0.001,
                                                   "tooltip":
                                                       "Skip a face pass if its sharpness score ≥ this value.\n"
                                                       "0.0 = always process (disabled).\n"
                                                       "Run once with 0.0, read the console 'quality score' lines,\n"
                                                       "then set threshold just below the score of faces you want kept.\n"
                                                       "Typical well-drawn ANIMA face: 0.030–0.070.\n"
                                                       "Broken/blurry face: 0.005–0.020."}),
                "face_prompt":    ("STRING",  {"default": _FACE_POS,  "multiline": True}),
                "face_negative":  ("STRING",  {"default": _FACE_NEG,  "multiline": True}),

                # ── Hands ──────────────────────────────────────────────────
                "hands_enabled":  ("BOOLEAN", {"default": True}),
                "hands_denoise":  ("FLOAT",   {"default": 0.50, "min": 0.0, "max": 1.0, "step": 0.01}),
                "hands_prompt":   ("STRING",  {"default": _HANDS_POS, "multiline": True}),
                "hands_negative": ("STRING",  {"default": _HANDS_NEG, "multiline": True}),

                # ── Body ───────────────────────────────────────────────────
                "body_enabled":   ("BOOLEAN", {"default": True}),
                "body_denoise":   ("FLOAT",   {"default": 0.40, "min": 0.0, "max": 1.0, "step": 0.01}),
                "body_prompt":    ("STRING",  {"default": _BODY_POS,  "multiline": True}),
                "body_negative":  ("STRING",  {"default": _BODY_NEG,  "multiline": True}),
            },
            "optional": {
                # ── Model inputs ───────────────────────────────────────────
                "basic_pipe": ("BASIC_PIPE", {
                    "tooltip": "Provide model/clip/vae/positive/negative as a pipe. Overrides individual inputs.",
                }),
                "model":    ("MODEL",),
                "clip":     ("CLIP",),
                "vae":      ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),

                # ── Masks ──────────────────────────────────────────────────
                "face_mask":   ("MASK", {"tooltip": "Face mask. Wire from 🐸 Florence2+SAM Masker or 🐸 Mask Batch Split."}),
                "face_mask_2": ("MASK", {"tooltip": "Second character face mask."}),
                "face_mask_3": ("MASK", {"tooltip": "Third character face mask."}),
                "hands_mask":  ("MASK",),
                "body_mask":   ("MASK",),
            },
        }

    RETURN_TYPES  = ("IMAGE", "STRING")
    RETURN_NAMES  = ("image", "debug")
    FUNCTION      = "detail"
    CATEGORY      = "🐸 Node Pack"

    # ─────────────────────────────────────────────────────────────────────

    def detail(
        self, image, seed, steps, cfg, sampler_name, scheduler,
        upscale_to, padding, feather,
        max_upscale_ratio, min_region_px,
        resize_mode, antialias,
        pre_upscale,
        mask_dilation, sharpen,
        two_pass, refine_denoise,
        face_enabled,  face_denoise,  auto_eye_color,  face_skip_threshold,
        face_prompt,  face_negative,
        hands_enabled, hands_denoise, hands_prompt,  hands_negative,
        body_enabled,  body_denoise,  body_prompt,   body_negative,
        basic_pipe=None, model=None, clip=None, vae=None,
        positive=None, negative=None,
        face_mask=None, face_mask_2=None, face_mask_3=None,
        hands_mask=None, body_mask=None,
    ):
        upscale_to = int(upscale_to)

        # ── Unpack pipe ───────────────────────────────────────────────────
        if basic_pipe is not None:
            model, clip, vae, positive, negative = basic_pipe

        if model is None or vae is None or positive is None or negative is None:
            raise ValueError("🐸 Detailer Pro: model, vae, positive and negative are required "
                             "(connect basic_pipe or individual inputs).")

        result         = image.clone().float()
        H, W           = result.shape[1], result.shape[2]
        original_image = result.clone()          # kept at original resolution for quality scoring
        debug_lines    = []

        # ── Pre-upscale full image ────────────────────────────────────────
        original_hw = (H, W)
        if pre_upscale > 1.0:
            tH = int(H * pre_upscale)
            tW = int(W * pre_upscale)
            result = _interp(
                result.permute(0, 3, 1, 2), (tH, tW), resize_mode, antialias,
            ).permute(0, 2, 3, 1).clamp(0.0, 1.0)
            H, W = result.shape[1], result.shape[2]
            debug_lines.append(f"pre-upscale {pre_upscale}×: {original_hw[1]}×{original_hw[0]} → {tW}×{tH}")
            print(f"[🐸 Detailer Pro]  Pre-upscale {pre_upscale}×: {original_hw[1]}×{original_hw[0]} → {tW}×{tH}")

        # ── Shared kwargs for _inpaint_region ─────────────────────────────
        region_kw = dict(
            vae=vae, seed=seed, steps=steps, cfg=cfg,
            sampler_name=sampler_name, scheduler=scheduler,
            padding=padding, upscale_to=upscale_to, feather=feather,
            max_upscale=max_upscale_ratio, min_region_px=min_region_px,
            resize_mode=resize_mode, antialias=antialias,
            mask_dilation=mask_dilation, sharpen=sharpen,
        )

        # ── Build face passes (up to 3 masks) ────────────────────────────
        face_passes = []
        if face_enabled:
            for i, fmask in enumerate([face_mask, face_mask_2, face_mask_3], 1):
                if fmask is None:
                    continue
                if isinstance(fmask, torch.Tensor) and fmask.max() < 0.01:
                    continue
                label = "face" if i == 1 else f"face {i}"
                face_passes.append((label, fmask))

        # ── Region list ───────────────────────────────────────────────────
        # (label, enabled, mask, denoise, pos_text, neg_text, is_face)
        regions = []
        for label, fmask in face_passes:
            regions.append((label, True, fmask, face_denoise, face_prompt, face_negative, True))
        regions += [
            ("hands", hands_enabled, hands_mask, hands_denoise, hands_prompt, hands_negative, False),
            ("body",  body_enabled,  body_mask,  body_denoise,  body_prompt,  body_negative,  False),
        ]

        ran = []
        for name, enabled, mask, denoise, pos_text, neg_text, is_face in regions:

            if not enabled:
                debug_lines.append(f"{name}: disabled")
                continue
            if mask is None:
                debug_lines.append(f"{name}: ⚠ no mask — skipped")
                continue

            # ── Face quality gate ─────────────────────────────────────────
            if is_face and face_skip_threshold > 0.0:
                orig_H, orig_W = original_image.shape[1], original_image.shape[2]
                m2d_orig = _normalise_mask_2d(mask, orig_H, orig_W)
                q_score  = _face_quality_score(original_image, m2d_orig, padding)
                print(f"[🐸 Detailer Pro]  {name}: quality score = {q_score:.5f}"
                      f"  (threshold = {face_skip_threshold:.3f})")
                debug_lines.append(f"{name}: quality score = {q_score:.5f}")
                if q_score >= face_skip_threshold:
                    debug_lines.append(
                        f"{name}: ✓ quality {q_score:.5f} ≥ {face_skip_threshold:.3f} — skipped (face looks good)"
                    )
                    print(f"[🐸 Detailer Pro]  {name}: ✓ above threshold — SKIPPED")
                    continue

            # ── Eye colour injection ──────────────────────────────────────
            actual_pos = pos_text
            if is_face and auto_eye_color:
                m2d       = _normalise_mask_2d(mask, H, W)
                color_tag = _sample_face_eye_color(result, m2d, padding)
                if color_tag:
                    actual_pos = f"{color_tag}, {pos_text}".strip(", ") if pos_text else color_tag
                    debug_lines.append(f"{name}: eye colour = {color_tag}")
                    print(f"[🐸 Detailer Pro]  {name}: auto eye colour → {color_tag}")
                else:
                    debug_lines.append(f"{name}: eye colour = uncertain")

            # ── Build conditioning ────────────────────────────────────────
            reg_positive = _append_region_prompt(positive, clip, actual_pos)
            reg_negative = _append_region_prompt(negative, clip, neg_text)

            debug_lines.append(
                f"{name}: denoise={denoise}"
                + (f"  pos='{actual_pos[:50]}…'" if actual_pos else "")
                + (f"  neg='{neg_text[:40]}…'"   if neg_text   else "")
            )
            print(f"[🐸 Detailer Pro]  {name}: pass 1 (fix)  denoise={denoise}")

            # ── Pass 1 — fix ──────────────────────────────────────────────
            result = _inpaint_region(
                result, mask, model, reg_positive, reg_negative,
                denoise=denoise, **region_kw,
            )

            # ── Pass 2 — refine ───────────────────────────────────────────
            if two_pass and refine_denoise > 0.0:
                print(f"[🐸 Detailer Pro]  {name}: pass 2 (refine)  denoise={refine_denoise}")
                result = _inpaint_region(
                    result, mask, model, reg_positive, reg_negative,
                    denoise=refine_denoise,
                    **{**region_kw, "seed": seed + 1, "sharpen": 0.0},
                )
                debug_lines.append(f"{name}: pass 2 refine  denoise={refine_denoise}")

            ran.append(name)

        if not ran:
            debug_lines.append("⚠ No regions processed — check masks and enabled toggles.")

        # ── Post-downscale back to original resolution ────────────────────
        if pre_upscale > 1.0:
            oH, oW = original_hw
            result = _interp(
                result.permute(0, 3, 1, 2), (oH, oW), resize_mode, antialias,
            ).permute(0, 2, 3, 1).clamp(0.0, 1.0)
            debug_lines.append(f"post-downscale: back to {oW}×{oH}")
            print(f"[🐸 Detailer Pro]  Post-downscale back to {oW}×{oH}")

        debug = "\n".join(debug_lines)
        print(f"[🐸 Detailer Pro]  Done. Processed: {', '.join(ran) if ran else 'none'}")
        return (result, debug)


# ── Registration ──────────────────────────────────────────────────────────────

NODE_CLASS_MAPPINGS        = {"FrogDetailerPro": FrogDetailerPro}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogDetailerPro": "🐸 Detailer Pro"}
