"""
FrogNodePack — Mask Batch Split

Splits a batched MASK tensor ([N, H, W]) into up to three individual masks.

Intended use: wire the output of 🐸 Florence2+SAM Masker (in "separate" mode)
into this node, then route mask_1 → face_mask, mask_2 → face_mask_2,
mask_3 → face_mask_3 on 🐸 Detailer.

If the batch contains fewer than 3 masks, the unused output slots return a
zero (black) mask.  🐸 Detailer will automatically skip zero masks.
"""

import torch


class FrogMaskBatchSplit:
    """
    Split a batched mask into up to three individual masks.

    Connect the "mask" output of 🐸 Florence2+SAM Masker (separate mode) here.
    mask_1 → face_mask
    mask_2 → face_mask_2
    mask_3 → face_mask_3
    Unused slots are zero and are skipped by 🐸 Detailer automatically.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mask_batch": ("MASK", {
                    "tooltip":
                        "Batched mask [N, H, W] from 🐸 Florence2+SAM Masker in 'separate' mode.\n"
                        "Each slice becomes one output mask.",
                }),
            }
        }

    RETURN_TYPES  = ("MASK",   "MASK",   "MASK")
    RETURN_NAMES  = ("mask_1", "mask_2", "mask_3")
    FUNCTION      = "split"
    CATEGORY      = "🐸 Node Pack"

    def split(self, mask_batch: torch.Tensor):
        # Normalise: [H,W] → [1,H,W] ; [1,H,W] stays ; [N,H,W] stays
        if mask_batch.dim() == 2:
            mask_batch = mask_batch.unsqueeze(0)

        N, H, W = mask_batch.shape

        def _get(i: int) -> torch.Tensor:
            if i < N:
                return mask_batch[i : i + 1].float()            # [1, H, W]
            return torch.zeros(1, H, W, dtype=torch.float32)   # empty slot

        m1, m2, m3 = _get(0), _get(1), _get(2)

        dbg_parts = [f"batch_size={N}"]
        for idx, m in enumerate([m1, m2, m3], 1):
            cov = float(m.mean()) * 100.0
            dbg_parts.append(f"mask_{idx}: {'active' if cov > 0.01 else 'empty'}  ({cov:.1f}%)")
        print(f"[🐸 MaskBatchSplit]  {' | '.join(dbg_parts)}")

        return (m1, m2, m3)


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────

NODE_CLASS_MAPPINGS        = {"FrogMaskBatchSplit": FrogMaskBatchSplit}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogMaskBatchSplit": "🐸 Mask Batch Split"}
