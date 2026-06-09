"""
FrogNodePack — Florence2 + SAM Masker

Two-stage precision masker with three independent region outputs:

  Stage 1 — Florence2 (phrase grounding / open-vocabulary detection):
    Given a text prompt, find bounding boxes for that subject in the image.

  Stage 2 — SAM (Segment Anything Model):
    Use each bounding box as a prompt to SAM so it segments the precise
    pixel boundary rather than just returning a rectangle.

  Florence2 and SAM are each loaded ONCE and shared across all three
  region passes (face / hands / body) — no redundant GPU work.

Outputs:
  face_mask   — wire into 🐸 Detailer  face_mask  (or 🐸 Mask Batch Split for multi-char)
  hands_mask  — wire into 🐸 Detailer  hands_mask
  body_mask   — wire into 🐸 Detailer  body_mask

SAM is OPTIONAL — three scenarios all work:
  • Impact Pack installed   → connect SAM_MODEL from its SAMLoader node
  • segment_anything pip    → leave sam_model disconnected; loaded automatically
  • Neither available       → Florence2 <REFERRING_EXPRESSION_SEGMENTATION>
                              is tried first, then rectangular bbox fallback

Face mask_mode "separate" outputs [N,H,W] batch — wire into 🐸 Mask Batch Split
to get individual face masks for multi-character eye colour isolation.
"""

import torch
import torch.nn.functional as F
import numpy as np
from PIL import Image, ImageDraw


# ─────────────────────────────────────────────────────────────────────────────
# Node
# ─────────────────────────────────────────────────────────────────────────────

class FrogFloSAMMasker:
    """
    Detect and segment three regions in one pass using Florence2 + SAM.

    Florence2 and SAM are initialised once and shared across all three
    region detections — no redundant model loading per-prompt.

    face_mask  → 🐸 Detailer face_mask  (or → 🐸 Mask Batch Split for multi-char)
    hands_mask → 🐸 Detailer hands_mask
    body_mask  → 🐸 Detailer body_mask

    Leave any prompt blank to skip that region (returns a zero mask).
    """

    @classmethod
    def INPUT_TYPES(cls):
        _mode_face = (["union", "largest", "separate"], {
            "default": "union",
            "tooltip":
                "union    — merge all detected faces into one mask.\n"
                "largest  — keep only the biggest face.\n"
                "separate — one mask per detected face as [N,H,W] batch.\n"
                "           Wire into 🐸 Mask Batch Split for multi-character\n"
                "           eye-colour isolation.",
        })
        _mode_2 = (["union", "largest"], {
            "default": "union",
            "tooltip":
                "union   — merge all detected regions into one mask.\n"
                "largest — keep only the biggest region.",
        })
        return {
            "required": {
                "image":           ("IMAGE",),
                "florence2_model": ("FL2MODEL", {
                    "tooltip": "Load with Florence2ModelLoader from comfyui-florence2.",
                }),
                "face_prompt":     ("STRING", {
                    "default": "face", "multiline": False,
                    "tooltip": "What to detect for the face mask. Leave blank to skip.",
                }),
                "face_mask_mode":  _mode_face,
                "hands_prompt":    ("STRING", {
                    "default": "hands", "multiline": False,
                    "tooltip": "What to detect for the hands mask. Leave blank to skip.",
                }),
                "hands_mask_mode": _mode_2,
                "body_prompt":     ("STRING", {
                    "default": "breasts, torso, midriff", "multiline": False,
                    "tooltip": "What to detect for the body mask. Leave blank to skip.",
                }),
                "body_mask_mode":  _mode_2,
                "confidence": ("FLOAT", {
                    "default": 0.30, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Minimum detection confidence. Lower = more boxes.",
                }),
            },
            "optional": {
                "sam_model": ("SAM_MODEL", {
                    "tooltip":
                        "Optional. Connect 🐸 SAM Loader or Impact Pack SAMLoader.\n"
                        "Leave disconnected to use Florence2 native segmentation.",
                }),
                "expand_bbox": ("INT", {
                    "default": 12, "min": 0, "max": 256, "step": 4,
                    "tooltip": "Expand each Florence2 bounding box by N pixels before SAM.",
                }),
                "max_detections": ("INT", {
                    "default": 6, "min": 1, "max": 32,
                    "tooltip": "Cap how many bounding boxes are processed per region.",
                }),
            },
        }

    RETURN_TYPES  = ("MASK",       "MASK",        "MASK",       "STRING")
    RETURN_NAMES  = ("face_mask",  "hands_mask",  "body_mask",  "debug")
    FUNCTION      = "detect_and_segment"
    CATEGORY      = "🐸 Node Pack"

    # ─────────────────────────────────────────────────────────────────────────

    def detect_and_segment(
        self, image, florence2_model,
        face_prompt,  face_mask_mode,
        hands_prompt, hands_mask_mode,
        body_prompt,  body_mask_mode,
        confidence=0.30,
        sam_model=None, expand_bbox=12, max_detections=6,
    ):
        # [1, H, W, 3] float32 → numpy uint8 RGB
        frame      = image[0].cpu().float().numpy()
        img_np     = (frame * 255.0).clip(0, 255).astype(np.uint8)
        H, W       = img_np.shape[:2]
        img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).float() / 255.0

        dbg = [f"Image: {W}×{H}  SAM: {'connected' if sam_model is not None else 'not connected'}"]

        # ── Unpack Florence2 once ─────────────────────────────────────────
        unpacked = _flo_unpack(florence2_model, dbg)
        if unpacked is None:
            zero = torch.zeros(1, H, W, dtype=torch.float32)
            return (zero, zero, zero, "\n".join(dbg))

        # ── Build SAM predictor once, set image once ──────────────────────
        predictor = None
        if sam_model is not None:
            predictor = _make_predictor(sam_model, dbg)
            if predictor is not None:
                try:
                    predictor.set_image(img_np)
                    dbg.append("SAM: image set — shared across all regions")
                except Exception as e:
                    dbg.append(f"SAM set_image failed: {e}  →  Florence2 fallback")
                    predictor = None

        # ── Detect each region ────────────────────────────────────────────
        kw = dict(
            unpacked=unpacked, predictor=predictor,
            img_np=img_np, img_tensor=img_tensor,
            max_detections=max_detections, expand_bbox=expand_bbox,
            W=W, H=H, dbg=dbg,
        )

        face_mask  = _detect_region(prompt=face_prompt,  mask_mode=face_mask_mode,  label="face",  **kw)
        hands_mask = _detect_region(prompt=hands_prompt, mask_mode=hands_mask_mode, label="hands", **kw)
        body_mask  = _detect_region(prompt=body_prompt,  mask_mode=body_mask_mode,  label="body",  **kw)

        return (face_mask, hands_mask, body_mask, "\n".join(dbg))


# ─────────────────────────────────────────────────────────────────────────────
# Per-region detection
# ─────────────────────────────────────────────────────────────────────────────

def _detect_region(unpacked, predictor, img_np, img_tensor,
                   prompt, mask_mode, label,
                   max_detections, expand_bbox, W, H, dbg):
    """
    Run detection for one prompt using pre-loaded Florence2 + SAM.
    Returns a MASK tensor:  [1,H,W] for union/largest,  [N,H,W] for separate.
    Returns a zero [1,H,W] if prompt is blank or nothing is detected.
    """
    if not prompt or not prompt.strip():
        dbg.append(f"{label}: prompt empty — skipped")
        return torch.zeros(1, H, W, dtype=torch.float32)

    patcher, processor, dtype = unpacked
    model       = patcher.model
    load_device = patcher.load_device

    # ── Try Florence2 native segmentation (only when SAM unavailable) ────
    if predictor is None:
        masks = _seg_masks_raw(model, processor, dtype, load_device,
                               img_tensor, prompt, W, H, dbg)
        if masks:
            masks = masks[:max_detections]
            dbg.append(f"{label}: native seg → {len(masks)} mask(s)")
            return _finalise(masks, mask_mode, H, W)
        dbg.append(f"{label}: native seg found nothing — trying bbox…")

    # ── Florence2 → bounding boxes ────────────────────────────────────────
    bboxes = _boxes_raw(model, processor, dtype, load_device,
                        img_tensor, prompt, W, H, dbg)
    bboxes = bboxes[:max_detections]

    if not bboxes:
        dbg.append(f"{label}: ⚠ no detections → zero mask")
        return torch.zeros(1, H, W, dtype=torch.float32)

    dbg.append(f"{label}: {len(bboxes)} box(es) to segment")

    # ── SAM predict or rect fallback ──────────────────────────────────────
    if predictor is not None:
        masks = _sam_predict_boxes(predictor, bboxes, expand_bbox, W, H, dbg, label)
    else:
        dbg.append(f"{label}: SAM not connected — rectangular bbox masks")
        masks = _rect_masks(bboxes, W, H)

    if not masks:
        dbg.append(f"{label}: ⚠ no masks produced → zero mask")
        return torch.zeros(1, H, W, dtype=torch.float32)

    result = _finalise(masks, mask_mode, H, W)
    cov    = float(result.float().mean()) * 100.0
    dbg.append(f"{label}: mode={mask_mode}  masks={len(masks)}  coverage={cov:.1f}%")
    return result


def _finalise(masks, mask_mode, H, W):
    """Apply mask_mode and return the correctly shaped tensor."""
    if mask_mode == "separate":
        return torch.stack(masks)           # [N, H, W]
    combined = _merge(masks, mask_mode)
    return combined.unsqueeze(0)            # [1, H, W]


# ─────────────────────────────────────────────────────────────────────────────
# Mask merge helper
# ─────────────────────────────────────────────────────────────────────────────

def _merge(masks, mode):
    stacked = torch.stack(masks)            # [N, H, W]
    if mode == "largest":
        best_i = int(stacked.sum(dim=(1, 2)).argmax())
        return stacked[best_i]
    return stacked.max(dim=0).values        # union


# ─────────────────────────────────────────────────────────────────────────────
# Florence2 helpers  (pre-loaded — no _flo_unpack calls inside)
# ─────────────────────────────────────────────────────────────────────────────

def _flo_unpack(flo_model, dbg):
    """Unpack the FL2MODEL dict. Returns (patcher, processor, dtype) or None."""
    try:
        import comfy.model_management as mm
        patcher   = flo_model['patcher']
        processor = flo_model['processor']
        dtype     = flo_model['dtype']
        mm.load_model_gpu(patcher)
        return patcher, processor, dtype
    except Exception as e:
        dbg.append(f"⚠ Florence2 unpack failed: {e}")
        return None


def _flo_generate(model, processor, dtype, load_device, img_tensor_chw, prompt_text, dbg):
    """Run one Florence2 generate pass. Returns decoded string or None."""
    try:
        inputs  = processor(text=prompt_text, images=img_tensor_chw.unsqueeze(0))
        gen_ids = model.generate(
            input_ids    = inputs["input_ids"].to(load_device),
            pixel_values = inputs["pixel_values"].to(dtype=dtype, device=load_device),
            max_new_tokens = 1024,
            num_beams      = 3,
            do_sample      = False,
        )
        return processor.batch_decode(gen_ids, skip_special_tokens=False)[0]
    except Exception as e:
        dbg.append(f"Florence2 generate error: {e}")
        return None


def _seg_masks_raw(model, processor, dtype, load_device, img_tensor, prompt, W, H, dbg):
    """
    <REFERRING_EXPRESSION_SEGMENTATION> → rasterised polygon masks.
    Accepts pre-loaded model components — no _flo_unpack call.
    """
    task        = "<REFERRING_EXPRESSION_SEGMENTATION>"
    prompt_text = f"{task} {prompt}"

    raw = _flo_generate(model, processor, dtype, load_device, img_tensor, prompt_text, dbg)
    if raw is None:
        return []

    try:
        parsed      = processor.post_process_generation(raw, task=task, image_size=(W, H))
        predictions = parsed.get(task, {})
        all_polys   = predictions.get("polygons", [])

        if not all_polys:
            return []

        masks = []
        for poly_variants in all_polys:
            det_mask = Image.new("L", (W, H), 0)
            draw     = ImageDraw.Draw(det_mask)
            for flat_poly in poly_variants:
                pts = _flat_to_pts(flat_poly, W, H)
                if len(pts) >= 3:
                    draw.polygon(pts, fill=255)
            arr = np.array(det_mask, dtype=np.float32) / 255.0
            if arr.max() > 0:
                masks.append(torch.from_numpy(arr))

        return masks

    except Exception as e:
        dbg.append(f"Florence2 RES post-process error: {e}")
        return []


def _boxes_raw(model, processor, dtype, load_device, img_tensor, prompt, W, H, dbg):
    """
    Florence2 → bounding boxes.
    Tries phrase grounding first, then OD label-filter.
    Accepts pre-loaded model components — no _flo_unpack call.
    """
    # ── Strategy 1: phrase grounding ─────────────────────────────────────
    task1 = "<CAPTION_TO_PHRASE_GROUNDING>"
    raw1  = _flo_generate(model, processor, dtype, load_device,
                          img_tensor, f"{task1} {prompt}", dbg)
    if raw1 is not None:
        try:
            parsed    = processor.post_process_generation(raw1, task=task1, image_size=(W, H))
            result    = parsed.get(task1, {})
            raw_boxes = result.get("bboxes", [])
            labels    = result.get("labels", [])
            if raw_boxes:
                dbg.append(f"  grounding: {len(raw_boxes)} box(es)  labels={labels[:6]}")
                return [_ints(b) for b in raw_boxes]
            dbg.append("  grounding: no boxes → trying OD…")
        except Exception as e:
            dbg.append(f"  grounding post-process error: {e}")

    # ── Strategy 2: open detection, filter by label ───────────────────────
    task2 = "<OD>"
    raw2  = _flo_generate(model, processor, dtype, load_device, img_tensor, task2, dbg)
    if raw2 is not None:
        try:
            parsed    = processor.post_process_generation(raw2, task=task2, image_size=(W, H))
            result    = parsed.get(task2, {})
            raw_boxes = result.get("bboxes", [])
            labels    = result.get("labels", [])
            prompt_l  = prompt.lower().strip()
            filtered  = [_ints(b) for b, lbl in zip(raw_boxes, labels)
                         if _labels_match(prompt_l, lbl)]
            dbg.append(
                f"  OD: {len(raw_boxes)} total → {len(filtered)} matched '{prompt}' "
                f"[seen: {sorted(set(labels))[:8]}]"
            )
            return filtered
        except Exception as e:
            dbg.append(f"  OD post-process error: {e}")

    return []


# ─────────────────────────────────────────────────────────────────────────────
# SAM helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sam_predict_boxes(predictor, bboxes, expand_px, W, H, dbg, label=""):
    """
    Predict masks for a list of bounding boxes using an already-set predictor.
    set_image() must have been called before this.
    """
    masks_out = []
    for i, (x1, y1, x2, y2) in enumerate(bboxes):
        x1e = max(0, x1 - expand_px);  y1e = max(0, y1 - expand_px)
        x2e = min(W, x2 + expand_px);  y2e = min(H, y2 + expand_px)
        box = np.array([x1e, y1e, x2e, y2e], dtype=np.float32)

        try:
            masks, scores, _ = predictor.predict(box=box, multimask_output=True)
            best   = int(np.argmax(scores))
            mask_t = torch.from_numpy(masks[best].astype(np.float32))
            masks_out.append(mask_t)
            dbg.append(
                f"  {label} SAM box {i} [{x1},{y1},{x2},{y2}]"
                f"+{expand_px}px → score={scores[best]:.3f}"
            )
        except Exception as e:
            dbg.append(f"  {label} SAM box {i} predict failed: {e}  →  rect fallback")
            m = torch.zeros(H, W, dtype=torch.float32)
            m[y1e:y2e, x1e:x2e] = 1.0
            masks_out.append(m)

    return masks_out


def _make_predictor(sam_model, dbg):
    """
    Wrap sam_model in a predictor.
    Accepts raw model or (model, 'sam1'/'sam2') tuple from 🐸 SAM Loader.
    """
    version_hint = None
    if isinstance(sam_model, tuple) and len(sam_model) == 2 and isinstance(sam_model[1], str):
        sam_model, version_hint = sam_model
        dbg.append(f"SAM: version hint = {version_hint}")

    if version_hint == "sam2":
        pred = _try_sam2(sam_model, dbg)
        if pred is not None:
            return pred
        dbg.append("SAM2 failed, trying SAM1 as fallback…")
        return _try_sam1(sam_model, dbg)

    pred = _try_sam1(sam_model, dbg)
    if pred is not None:
        return pred
    return _try_sam2(sam_model, dbg)


def _try_sam1(sam_model, dbg):
    import importlib
    for mod_path, cls_name in [
        ("segment_anything_hq", "SamPredictor"),
        ("segment_anything",    "SamPredictor"),
        ("segment_anything2",   "SamPredictor"),
    ]:
        try:
            m   = importlib.import_module(mod_path)
            cls = getattr(m, cls_name)
            dbg.append(f"SAM: using {mod_path}.{cls_name}")
            return cls(sam_model)
        except ImportError:
            continue
        except Exception as e:
            dbg.append(f"SAM1 ({mod_path}) init error: {e}")

    try:
        import impact.impact_pack as ip
        if hasattr(ip, "SAMPredictor"):
            dbg.append("SAM: using impact.impact_pack.SAMPredictor")
            return ip.SAMPredictor(sam_model)
    except Exception:
        pass

    return None


def _try_sam2(sam_model, dbg):
    import importlib
    for mod_path, cls_name in [
        ("sam2.sam2_image_predictor", "SAM2ImagePredictor"),
        ("sam2",                      "SAM2ImagePredictor"),
    ]:
        try:
            m   = importlib.import_module(mod_path)
            cls = getattr(m, cls_name)
            dbg.append(f"SAM: using {mod_path}.{cls_name}")
            return cls(sam_model)
        except ImportError:
            continue
        except Exception as e:
            dbg.append(f"SAM2 ({mod_path}) init error: {e}")
    return None


def _rect_masks(bboxes, W, H):
    out = []
    for (x1, y1, x2, y2) in bboxes:
        m = torch.zeros(H, W, dtype=torch.float32)
        m[max(0, y1):min(H, y2), max(0, x1):min(W, x2)] = 1.0
        out.append(m)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

def _flat_to_pts(flat_poly, W, H):
    if not flat_poly:
        return []
    if isinstance(flat_poly[0], (list, tuple)):
        pts = [(float(p[0]), float(p[1])) for p in flat_poly]
    else:
        pts = [(float(flat_poly[i]), float(flat_poly[i+1]))
               for i in range(0, len(flat_poly) - 1, 2)]
    return [(max(0, min(W-1, int(x))), max(0, min(H-1, int(y)))) for x, y in pts]


def _ints(bbox):
    return [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]


def _labels_match(prompt_lower, label):
    lbl = label.lower()
    return (prompt_lower in lbl) or (lbl in prompt_lower)


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────

NODE_CLASS_MAPPINGS        = {"FrogFloSAMMasker": FrogFloSAMMasker}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogFloSAMMasker": "🐸 Florence2+SAM Masker"}
