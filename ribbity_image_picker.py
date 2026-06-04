"""
🐸 Image Picker
Sits between KSampler and a Save node.  On the first queue run it captures
the batch, stores frames to disk, and displays thumbnails in the node UI.
The user clicks to select frames, then presses Proceed to queue a second
run that outputs only those frames to the downstream Save node.
Cancel discards the stored batch and resets the node.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

try:
    from aiohttp import web
    from server import PromptServer
    _server = PromptServer.instance
except Exception:
    _server = None
    web = None

try:
    import folder_paths
except ImportError:
    folder_paths = None

try:
    from PIL import Image as PilImage
except ImportError:
    PilImage = None

ROOT = Path(__file__).parent

# ---------------------------------------------------------------------------
# Per-node state  (keyed by unique_id string)
# ---------------------------------------------------------------------------
# {
#   "ready":     bool,       — True after Proceed is clicked
#   "paths":     [str],      — temp PNG paths for the stored batch
#   "selection": [int],      — frame indices chosen by the user
# }
_picker_state: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _temp_dir(node_id: str) -> Path:
    if folder_paths is not None:
        base = Path(folder_paths.get_temp_directory())
    else:
        base = ROOT / "data" / "tmp"
    d = base / "frog_picker" / str(node_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _store_frames(images, node_id: str) -> tuple[list[str], list[dict]]:
    """
    Save each frame as a temp PNG.
    Returns (abs_paths, ui_image_dicts) where ui_image_dicts can be passed
    directly to the ComfyUI "ui.images" response key.
    """
    if PilImage is None:
        return [], []

    d = _temp_dir(node_id)
    for old in d.glob("frame_*.png"):
        old.unlink(missing_ok=True)

    paths: list[str] = []
    ui_images: list[dict] = []

    for i, frame in enumerate(images):
        arr = frame
        if hasattr(arr, "cpu"):
            arr = arr.cpu().numpy()
        arr = (arr.clip(0, 1) * 255).astype(np.uint8)
        pil = PilImage.fromarray(arr)
        fname = f"frame_{i:04d}.png"
        fpath = d / fname
        pil.save(str(fpath), format="PNG")
        paths.append(str(fpath))
        ui_images.append({
            "filename": fname,
            "subfolder": f"frog_picker/{node_id}",
            "type": "temp",
        })

    return paths, ui_images


def _load_frames(paths: list[str], indices: list[int]):
    """Load selected frames from disk, return stacked tensor."""
    import torch
    frames = []
    for idx in indices:
        if 0 <= idx < len(paths) and os.path.exists(paths[idx]):
            arr = np.array(
                PilImage.open(paths[idx]).convert("RGB"),
                dtype=np.float32,
            ) / 255.0
            frames.append(torch.from_numpy(arr).unsqueeze(0))
    if not frames:
        return None
    return torch.cat(frames, dim=0)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class FrogImagePicker:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
            },
            "hidden": {
                "unique_id":    "UNIQUE_ID",
                "prompt":       "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES  = ("IMAGE",)
    RETURN_NAMES  = ("selected",)
    OUTPUT_NODE   = True          # always execute (side-effects: store / emit)
    FUNCTION      = "pick"
    CATEGORY      = "🐸 Node Pack"

    def pick(self, images, unique_id=None, prompt=None, extra_pnginfo=None):
        import torch

        node_id = str(unique_id or "0")
        state   = _picker_state.get(node_id, {})

        # ── Proceed run ──────────────────────────────────────────────────────
        if state.get("ready"):
            selection = state.get("selection") or []
            paths     = state.get("paths", [])

            # Fall back: if user somehow cleared selection, pass every stored frame
            if not selection:
                selection = list(range(len(paths)))

            output = _load_frames(paths, selection)
            if output is None:
                # Nothing loaded (files missing?) — pass original batch through
                output = images

            # Reset: ready for next generation
            _picker_state[node_id] = {"ready": False, "paths": [], "selection": []}

            return {"ui": {"images": []}, "result": (output,)}

        # ── Capture run ──────────────────────────────────────────────────────
        # Store every frame, return empty batch so downstream Save is skipped.
        paths, ui_images = _store_frames(images, node_id)
        _picker_state[node_id] = {
            "ready":     False,
            "paths":     paths,
            "selection": [],
        }

        # An empty (0-frame) IMAGE tells downstream Save nodes to do nothing.
        empty = torch.zeros((0, *images.shape[1:]), dtype=images.dtype)
        return {"ui": {"images": ui_images}, "result": (empty,)}


# ---------------------------------------------------------------------------
# Node registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "FrogImagePicker": FrogImagePicker,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogImagePicker": "🐸 Image Picker",
}


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

if _server is not None and web is not None:
    routes = _server.routes

    @routes.post("/frog_picker/proceed")
    async def _picker_proceed(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "bad JSON"}, status=400)

        node_id   = str(data.get("node_id", ""))
        selection = data.get("selection", [])

        if not node_id:
            return web.json_response({"ok": False, "error": "missing node_id"}, status=400)

        state = _picker_state.get(node_id, {})
        state["selection"] = [int(i) for i in selection if str(i).strip().lstrip("-").isdigit()]
        state["ready"]     = True
        _picker_state[node_id] = state

        return web.json_response({"ok": True})

    @routes.post("/frog_picker/cancel")
    async def _picker_cancel(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "bad JSON"}, status=400)

        node_id = str(data.get("node_id", ""))
        if node_id:
            state = _picker_state.get(node_id, {})
            # Delete temp files
            for p in state.get("paths", []):
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass
            _picker_state[node_id] = {"ready": False, "paths": [], "selection": []}

        return web.json_response({"ok": True})

    print("[🐸 Image Picker] HTTP routes registered at /frog_picker/*")
