"""
🐸 Image Picker — sits between KSampler and a Save node.

Capture run  : receives the image batch → saves temp frames → displays thumbnails
               → BLOCKS the execution thread (time.sleep loop) until the user acts.
               ComfyUI's queue naturally waits because execution has not finished.
               No second prompt is ever submitted; no queue draining is needed.

Proceed      : user clicks Proceed → JS POSTs selection to /frog_picker/proceed
               → sets selected in state → sleep loop exits → selected frames
               return to downstream nodes → execution completes normally.

Cancel       : JS POSTs to /frog_picker/cancel → sets cancelled flag → sleep loop
               exits → raises InterruptProcessingException → execution aborted.
"""
from __future__ import annotations

import os
import time
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
# Per-node runtime state  { node_id: {paths, selected, cancelled} }
# ---------------------------------------------------------------------------
_state: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Temp-file helpers
# ---------------------------------------------------------------------------

def _temp_dir(node_id: str) -> Path:
    base = (
        Path(folder_paths.get_temp_directory())
        if folder_paths is not None
        else ROOT / "data" / "tmp"
    )
    d = base / "frog_picker" / str(node_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_frames(images, node_id: str) -> tuple[list[str], list[dict]]:
    """Write batch frames as temp PNGs; return (abs_paths, ui_dicts)."""
    if PilImage is None:
        return [], []
    d = _temp_dir(node_id)
    for old in d.glob("frame_*.png"):
        old.unlink(missing_ok=True)
    paths, ui = [], []
    for i, frame in enumerate(images):
        arr = frame.cpu().numpy() if hasattr(frame, "cpu") else frame
        arr = (arr.clip(0, 1) * 255).astype(np.uint8)
        fname = f"frame_{i:04d}.png"
        PilImage.fromarray(arr).save(str(d / fname), format="PNG")
        paths.append(str(d / fname))
        ui.append({
            "filename": fname,
            "subfolder": f"frog_picker/{node_id}",
            "type": "temp",
        })
    return paths, ui


def _load_frames(paths: list[str], indices: list[int]):
    """Load selected frames from disk; return stacked tensor or None."""
    import torch
    frames = []
    for idx in indices:
        if 0 <= idx < len(paths) and os.path.exists(paths[idx]):
            arr = (np.array(PilImage.open(paths[idx]).convert("RGB"), dtype=np.float32)
                   / 255.0)
            frames.append(torch.from_numpy(arr).unsqueeze(0))
    return torch.cat(frames, dim=0) if frames else None


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class FrogImagePicker:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "hold_queue": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Legacy setting — the blocking approach always pauses the queue "
                        "naturally. Kept for workflow compatibility."
                    ),
                }),
            },
            "optional": {
                # Not present when the node is cached / upstream is bypassed.
                "images": ("IMAGE",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES  = ("IMAGE",)
    RETURN_NAMES  = ("selected",)
    OUTPUT_NODE   = True
    FUNCTION      = "pick"
    CATEGORY      = "🐸 Node Pack"

    def pick(self, hold_queue=True, images=None, unique_id=None):
        import torch
        import comfy.model_management as _mm

        node_id = str(unique_id or "0")

        # No images supplied — return empty tensor.
        if images is None:
            empty = torch.zeros((0, 1, 1, 3), dtype=torch.float32)
            return {"ui": {"images": []}, "result": (empty,)}

        # Single image — pass through immediately, no user interaction needed.
        if images.shape[0] == 1:
            return {"ui": {"images": []}, "result": (images,)}

        # Save frames to temp dir so the frontend can fetch them via /view.
        paths, ui_images = _save_frames(images, node_id)

        # Initialise per-session state.
        _state[node_id] = {
            "paths":     paths,
            "selected":  None,
            "cancelled": False,
        }

        # Tell the frontend to display thumbnails.
        if _server is not None:
            _server.send_sync("frog_picker.clear",    {"node_id": node_id})
            _server.send_sync("frog_picker.captured", {"node_id": node_id,
                                                       "images": ui_images})

        # ── Block this execution thread until the user picks or cancels ──────
        # aiohttp runs on its own asyncio event loop in a separate thread, so
        # sleeping here does NOT freeze the HTTP server — /frog_picker/* routes
        # remain fully responsive while we wait.
        print(f"[🐸 Image Picker] waiting for user selection (node {node_id})…")
        while node_id in _state:
            st = _state[node_id]
            if st.get("cancelled"):
                _state.pop(node_id, None)
                print(f"[🐸 Image Picker] cancelled (node {node_id}).")
                raise _mm.InterruptProcessingException()
            if st.get("selected") is not None:
                break
            time.sleep(0.1)

        # ── User confirmed — load selected frames and continue downstream ────
        st       = _state.pop(node_id, {})
        selection = st.get("selected") or list(range(len(paths)))
        output   = _load_frames(paths, selection)
        if output is None:
            output = torch.zeros((0, 1, 1, 3), dtype=torch.float32)

        print(f"[🐸 Image Picker] proceeding with {len(selection)} frame(s) "
              f"(node {node_id}).")
        return {"ui": {"images": []}, "result": (output,)}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS        = {"FrogImagePicker": FrogImagePicker}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogImagePicker": "🐸 Image Picker"}


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

if _server is not None and web is not None:
    _r = _server.routes

    @_r.post("/frog_picker/proceed")
    async def _proceed(req: web.Request) -> web.Response:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "bad JSON"}, status=400)

        node_id   = str(data.get("node_id") or "")
        selection = [int(i) for i in (data.get("selection") or [])
                     if str(i).lstrip("-").isdigit()]

        if not node_id:
            return web.json_response({"ok": False, "error": "missing node_id"},
                                     status=400)
        if node_id not in _state:
            return web.json_response({"ok": False, "error": "node not waiting"},
                                     status=400)

        _state[node_id]["selected"]  = selection if selection else None
        _state[node_id]["cancelled"] = False

        return web.json_response({"ok": True})

    @_r.post("/frog_picker/cancel")
    async def _cancel(req: web.Request) -> web.Response:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "bad JSON"}, status=400)

        node_id = str(data.get("node_id") or "")
        if node_id and node_id in _state:
            for p in _state[node_id].get("paths", []):
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass
            _state[node_id]["cancelled"] = True

        return web.json_response({"ok": True})

    print("[🐸 Image Picker] routes registered at /frog_picker/*")
