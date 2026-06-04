"""
🐸 Image Picker — sits between KSampler and a Save node.

Capture run : receives the image batch → stores frames → shows thumbnails
              → interrupts execution (nothing downstream runs yet).

Proceed run : /frog_picker/proceed builds a minimal prompt and posts it
              to ComfyUI's own /prompt API endpoint (avoids direct queue
              manipulation and works on all ComfyUI builds).

Cancel      : clears stored frames and resets the node.
"""
from __future__ import annotations

import copy
import os
import uuid
from pathlib import Path

import numpy as np

try:
    import aiohttp as _aio
    from aiohttp import web
    from server import PromptServer
    _server = PromptServer.instance
except Exception:
    _server = None
    web = None
    _aio = None

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
# Per-node runtime state  { node_id: {ready, paths, selection} }
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
# Minimal-prompt builder
# ---------------------------------------------------------------------------

def _build_minimal_prompt(full_prompt: dict, picker_id: str) -> dict:
    """
    Return only the Picker + its downstream dependents from full_prompt.
    The Picker's 'images' input is stripped so nothing upstream (KSampler)
    is needed.  Dangling cross-set connections are also removed.
    """
    pid = str(picker_id)

    # Forward adjacency map: source_node_id → [consumer_node_ids]
    fwd: dict[str, list[str]] = {}
    for nid, node in full_prompt.items():
        for val in (node.get("inputs") or {}).values():
            if isinstance(val, list) and len(val) == 2:
                fwd.setdefault(str(val[0]), []).append(str(nid))

    # BFS from Picker to collect downstream nodes
    downstream: set[str] = set()
    q = [pid]
    while q:
        for dep in fwd.get(q.pop(0), []):
            if dep not in downstream:
                downstream.add(dep)
                q.append(dep)

    keep = {pid} | downstream
    minimal: dict = {}
    for nid, node in full_prompt.items():
        nid = str(nid)
        if nid not in keep:
            continue
        nc = copy.deepcopy(node)
        # Strip the upstream image connection from the Picker node
        if nid == pid:
            (nc.get("inputs") or {}).pop("images", None)
        # Remove any remaining links to nodes we're not keeping
        for k, v in list((nc.get("inputs") or {}).items()):
            if isinstance(v, list) and len(v) == 2 and str(v[0]) not in keep:
                del nc["inputs"][k]
        minimal[nid] = nc
    return minimal


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class FrogImagePicker:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                # Not provided on the Proceed run — Picker reads disk frames.
                "images": ("IMAGE",),
            },
            "hidden": {
                "unique_id":     "UNIQUE_ID",
                "prompt":        "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES  = ("IMAGE",)
    RETURN_NAMES  = ("selected",)
    OUTPUT_NODE   = True
    FUNCTION      = "pick"
    CATEGORY      = "🐸 Node Pack"

    def pick(self, images=None, unique_id=None, prompt=None, extra_pnginfo=None):
        import torch

        node_id = str(unique_id or "0")
        st      = _state.get(node_id, {})

        # ── Proceed run ──────────────────────────────────────────────────────
        if st.get("ready"):
            paths     = st.get("paths", [])
            selection = st.get("selection") or list(range(len(paths)))
            output    = _load_frames(paths, selection)
            if output is None:
                output = torch.zeros((0, 1, 1, 3), dtype=torch.float32)
            _state[node_id] = {"ready": False, "paths": [], "selection": []}
            return {"ui": {"images": []}, "result": (output,)}

        # ── Capture run ──────────────────────────────────────────────────────
        if images is None:
            empty = torch.zeros((0, 1, 1, 3), dtype=torch.float32)
            return {"ui": {"images": []}, "result": (empty,)}

        paths, ui_images = _save_frames(images, node_id)
        _state[node_id]  = {"ready": False, "paths": paths, "selection": []}

        # Notify the DOM widget via WebSocket (avoids duplicate image strip)
        if _server is not None:
            _server.send_sync("frog_picker.captured",
                              {"node_id": node_id, "images": ui_images})

        # Interrupt so nothing downstream runs on the capture pass.
        import comfy.model_management as _mm
        raise _mm.InterruptProcessingException()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS        = {"FrogImagePicker": FrogImagePicker}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogImagePicker": "🐸 Image Picker"}


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

if _server is not None and web is not None and _aio is not None:
    _r = _server.routes

    @_r.post("/frog_picker/proceed")
    async def _proceed(req: web.Request) -> web.Response:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "bad JSON"}, status=400)

        node_id     = str(data.get("node_id") or "")
        selection   = [int(i) for i in (data.get("selection") or [])
                       if str(i).lstrip("-").isdigit()]
        full_prompt = data.get("prompt") or {}
        client_id   = str(data.get("client_id") or "")

        if not node_id:
            return web.json_response({"ok": False, "error": "missing node_id"}, status=400)

        # Mark node as ready so the Proceed run returns the selected frames.
        st = _state.get(node_id, {})
        st["selection"] = selection
        st["ready"]     = True
        _state[node_id] = st

        queued = False
        if full_prompt:
            try:
                minimal = _build_minimal_prompt(full_prompt, node_id)
                # Route through ComfyUI's own /prompt endpoint — it handles all
                # internal queue formats correctly across standard + Desktop builds.
                port    = req.url.port or 8188
                payload = {"prompt": minimal, "client_id": client_id}
                async with _aio.ClientSession() as session:
                    async with session.post(
                        f"http://127.0.0.1:{port}/prompt", json=payload
                    ) as r:
                        if r.status == 200:
                            queued = True
                        else:
                            text = await r.text()
                            print(f"[🐸 Image Picker] /prompt returned {r.status}: {text}")
            except Exception as e:
                print(f"[🐸 Image Picker] proceed error: {e}")

        return web.json_response({"ok": True, "queued": queued})

    @_r.post("/frog_picker/cancel")
    async def _cancel(req: web.Request) -> web.Response:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "bad JSON"}, status=400)

        node_id = str(data.get("node_id") or "")
        if node_id:
            for p in _state.get(node_id, {}).get("paths", []):
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass
            _state[node_id] = {"ready": False, "paths": [], "selection": []}

        return web.json_response({"ok": True})

    print("[🐸 Image Picker] routes registered at /frog_picker/*")
