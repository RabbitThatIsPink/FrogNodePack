"""
🐸 Node Pack — Library save nodes with thumbnail support.

  FrogThumbnailSaver      — wire an IMAGE + a library entry ID to write /
                            overwrite that entry's thumbnail in one queue step.

  FrogSaveAndThumbnail    — create or update a full library entry (name, text,
                            negative, tags) AND save its thumbnail in a single
                            atomic transaction.  Equivalent to GrimmRibbity's
                            PromptLibrarySave + PromptLibraryThumbnailSaver
                            fused into one node.

Both nodes write into the same data/ folder used by the 🐸 Library node, so
changes appear in the gallery immediately after the queue finishes.
"""
from __future__ import annotations

import numpy as np

from .ribbity_library import (
    _lock,
    _load,
    _safe_id,
    _slugify,
    _unique_id,
    _parse_tags,
    _save_thumbnail_pil,
    _touch,
    _maybe_push_history,
    _notify,
    _save,
)

# ---------------------------------------------------------------------------
# Internal helper — ComfyUI IMAGE tensor  →  PIL Image (first frame)
# ---------------------------------------------------------------------------

def _tensor_to_pil(tensor):
    """Convert a ComfyUI IMAGE tensor (B, H, W, C) float32 [0-1] to a PIL RGB image."""
    from PIL import Image  # noqa: PLC0415 — PIL is always available in ComfyUI
    frame = tensor[0].cpu().numpy()          # (H, W, C) float32
    frame = (frame * 255.0).clip(0, 255).astype(np.uint8)
    return Image.fromarray(frame, mode="RGB")


# ---------------------------------------------------------------------------
# 🐸 Thumbnail Saver
# ---------------------------------------------------------------------------

class FrogThumbnailSaverNode:
    """Update the thumbnail of an existing library entry.

    Wire the IMAGE to save and the Library node's 'id' output.
    The entry's name, text, and tags are not changed — only the artwork.
    IMAGE passes through so the node can sit mid-chain.
    """

    DESCRIPTION = (
        "Save or replace the thumbnail for a 🐸 Library entry.  Wire an "
        "IMAGE in and connect the Library node's 'id' output to prompt_id.  "
        "Only the artwork is updated; name, text, and tags are left untouched.  "
        "IMAGE passes through unchanged."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {
                    "tooltip": "Image to save as the entry's thumbnail. "
                               "The first frame of a batch is used unless "
                               "frame_index is set.",
                }),
                "prompt_id": ("STRING", {
                    "default": "", "multiline": False,
                    "tooltip": "ID of the library entry to update. "
                               "Auto-populated by the 🐸 Library gallery widget.",
                }),
            },
            "optional": {
                "frame_index": ("INT", {
                    "default": 1, "min": 1, "max": 4096,
                    "tooltip": "When the IMAGE is a batch, which frame to "
                               "use as the thumbnail (1-based).",
                }),
                "enabled": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Must be True for a thumbnail to be saved. "
                               "The 🐸 Library 'Queue ▶▶' button sets this "
                               "automatically for each run — leave it False "
                               "so regular queue runs never overwrite thumbnails.",
                }),
            },
        }

    RETURN_TYPES  = ("IMAGE", "STRING")
    RETURN_NAMES  = ("image", "id")
    OUTPUT_TOOLTIPS = (
        "The input image, passed through unchanged.",
        "The entry ID whose thumbnail was updated, or empty if skipped.",
    )
    FUNCTION      = "save_thumbnail"
    CATEGORY      = "🐸 Node Pack"
    OUTPUT_NODE   = True

    def save_thumbnail(self, image, prompt_id: str = "", enabled: bool = False, frame_index=1):
        if not enabled:
            print("[🐸 Thumbnail Saver] skipping — use Library Queue ▶▶ to save thumbnails.")
            return (image, "")

        # Optional INT inputs arrive as "" when not connected — coerce safely.
        try:
            frame_index = int(frame_index)
        except (ValueError, TypeError):
            frame_index = 1

        pid = (prompt_id or "").strip()
        if not pid:
            print("[🐸 Thumbnail Saver] prompt_id is empty — skipping.")
            return (image, "")
        if not _safe_id(pid):
            print(f"[🐸 Thumbnail Saver] invalid id {pid!r} — skipping.")
            return (image, "")

        with _lock:
            items = _load()
        entry = next((i for i in items if i.get("id") == pid), None)
        if entry is None:
            print(f"[🐸 Thumbnail Saver] no entry with id={pid!r} — skipping.")
            return (image, "")

        # Pick the requested frame (1-based, clamped to batch size).
        idx = max(0, min(frame_index - 1, image.shape[0] - 1))
        from PIL import Image as PILImage
        frame = image[idx]
        if hasattr(frame, "cpu"):
            frame = frame.cpu().numpy()
        arr = (frame.clip(0, 1) * 255).astype(np.uint8)
        pil = PILImage.fromarray(arr, mode="RGB")

        ext = _save_thumbnail_pil(pid, pil)

        # Bump updated_at so the watcher fires and the gallery refreshes.
        entry_name = ""
        with _lock:
            items = _load()
            entry = next((i for i in items if i.get("id") == pid), None)
            if entry is not None:
                entry_name = entry.get("name", "")
                _touch(entry, created=False)
                _save(items)

        _notify()
        print(f"[🐸 Thumbnail Saver] wrote thumbnail id={pid!r} "
              f"name={entry_name!r} ext={ext}")
        return (image, pid)


# ---------------------------------------------------------------------------
# 🐸 Save + Thumbnail
# ---------------------------------------------------------------------------

class FrogSaveAndThumbnailNode:
    """Create or update a library entry AND save its thumbnail in one queue step.

    Combines the roles of a "save prompt" node and a thumbnail writer.
    Everything happens inside a single lock acquire so the gallery always
    sees the new entry with its artwork — never one without the other.

    Lookup priority (same as the Library node):
      1. prompt_id (if provided and valid) → update that specific entry
      2. overwrite_by_name=True           → update the most-recently-changed
                                             entry whose name matches
      3. Otherwise                        → create a new entry
    """

    DESCRIPTION = (
        "Save a 🐸 Library entry AND its thumbnail in one node. "
        "Wire text + an IMAGE in, fill in name + tags, optionally wire a "
        "negative string.  On Queue the entry is created or updated and "
        "the thumbnail is written atomically, so the gallery always shows "
        "the correct artwork.  The saved text and entry ID are passed through."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {
                    "default": "", "multiline": False,
                    "tooltip": "Display name shown on tiles. Required.",
                }),
                "text": ("STRING", {
                    "default": "", "multiline": True,
                    "tooltip": "Positive prompt text to store. "
                               "An empty value raises an error so an "
                               "unwired input doesn't silently save a "
                               "blank entry.",
                }),
                "thumbnail": ("IMAGE", {
                    "tooltip": "Image to save as the entry's thumbnail. "
                               "The first frame of a batch is used.",
                }),
                "tags": ("STRING", {
                    "default": "", "multiline": False,
                    "tooltip": "Comma-separated tags. "
                               "Use 'category:value' (e.g. style:cyberpunk) "
                               "to enable category-grouped filter chips.",
                }),
                "overwrite_by_name": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "When prompt_id is unset and an entry with "
                               "this name already exists, update it instead "
                               "of creating a new one.  When several entries "
                               "share the name the most-recently-updated one "
                               "wins.",
                }),
            },
            "optional": {
                "negative": ("STRING", {
                    "default": "", "multiline": True,
                    "tooltip": "Optional negative prompt stored alongside "
                               "this entry and emitted on the Library "
                               "node's 'negative' output.",
                }),
                "prompt_id": ("STRING", {
                    "default": "", "multiline": False,
                    "tooltip": "Override the auto-derived ID. "
                               "Must match [A-Za-z0-9_-]{1,64}. "
                               "Leave blank to generate from 'name'. "
                               "Takes priority over overwrite_by_name.",
                }),
            },
        }

    RETURN_TYPES  = ("STRING", "STRING")
    RETURN_NAMES  = ("text", "id")
    OUTPUT_TOOLTIPS = (
        "The saved prompt text (passthrough of the input).",
        "The entry ID — wire into the Library loader's prompt_id or "
        "back into this node on the next run.",
    )
    FUNCTION      = "save"
    CATEGORY      = "🐸 Node Pack"
    OUTPUT_NODE   = True

    def save(self, name: str, text: str, thumbnail,
             tags: str = "", overwrite_by_name: bool = False,
             negative: str = "", prompt_id: str = ""):

        name = (name or "").strip()
        if not name:
            raise ValueError("🐸 Save + Thumbnail: 'name' is required.")
        if not (text or "").strip():
            raise ValueError(
                "🐸 Save + Thumbnail: 'text' is empty — connect a STRING "
                "source or type something into the text field.")

        prompt_id = (prompt_id or "").strip()
        if prompt_id and not _safe_id(prompt_id):
            raise ValueError(
                f"🐸 Save + Thumbnail: invalid prompt_id {prompt_id!r}. "
                "Must match [A-Za-z0-9_-]{1,64}.")

        parsed_tags = _parse_tags(tags)

        # Single transaction: one lock acquire, one _save, one _notify.
        with _lock:
            items = _load()
            existing = None
            match_path = "new"

            if prompt_id:
                existing = next(
                    (i for i in items if i.get("id") == prompt_id), None)
                match_path = "prompt_id" if existing else "new (id miss)"
            elif overwrite_by_name:
                matches = [i for i in items if i.get("name") == name]
                if matches:
                    existing = max(
                        matches, key=lambda i: i.get("updated_at", 0))
                    match_path = (
                        f"overwrite_by_name (1 of {len(matches)} match(es))"
                        if len(matches) > 1 else "overwrite_by_name")

            created = existing is None
            if created:
                pid = prompt_id or _unique_id(
                    _slugify(name), {i.get("id") for i in items})
                existing = {"id": pid}
                items.append(existing)
            else:
                pid = existing["id"]
                _maybe_push_history(
                    existing,
                    name,
                    text or "",
                    parsed_tags,
                    new_neg=(negative or ""),
                    new_loras=existing.get("loras"),
                )

            existing["name"] = name
            existing["text"] = text or ""
            existing["tags"] = parsed_tags
            if negative or "negative" in existing:
                existing["negative"] = negative or ""
            _touch(existing, created=created)

            # Convert tensor + save thumbnail inside the same lock so the
            # entry and its artwork are always in sync.
            pil = _tensor_to_pil(thumbnail)
            _save_thumbnail_pil(pid, pil)

            _save(items)

        _notify()
        print(f"[🐸 Save+Thumb] id={pid!r} name={name!r} "
              f"via={match_path} tags={parsed_tags}")
        return (text or "", pid)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "FrogThumbnailSaver":    FrogThumbnailSaverNode,
    "FrogSaveAndThumbnail":  FrogSaveAndThumbnailNode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogThumbnailSaver":    "🐸 Thumbnail Saver",
    "FrogSaveAndThumbnail":  "🐸 Save + Thumbnail",
}
