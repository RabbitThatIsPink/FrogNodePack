"""
RibbityLibraryNode — standalone visual prompt library node.
Self-contained: no dependencies on other custom node packs.
All routes live under /frog_library/  All data lives in data/ inside this pack folder.
"""
from __future__ import annotations

import copy
import csv
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path

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

ROOT         = Path(__file__).parent
DATA_DIR     = ROOT / "data"
IMAGES_DIR   = DATA_DIR / "images"
STORE_PATH   = DATA_DIR / "prompts.json"
SNAPSHOT_DIR = DATA_DIR / "snapshots"

for _d in (DATA_DIR, IMAGES_DIR, SNAPSHOT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()

# Shared state — lets downstream nodes (e.g. Thumbnail Saver) know which
# entry the Library node most recently loaded without needing a wired ID.
_library_state: dict = {"last_id": ""}

_ALLOWED_IMAGE_EXT       = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_MAX_IMAGE_BYTES         = 16 * 1024 * 1024
_THUMBNAIL_MAX_EDGE      = 400
_THUMBNAIL_JPEG_QUALITY  = 80
_EXPORT_THUMB_MAX_EDGE   = 384
_EXPORT_THUMB_JPEG_Q     = 75
_MAX_IMPORT_ZIP_BYTES    = 500 * 1024 * 1024
_MAX_IMPORT_ZIP_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
_MAX_IMPORT_CSV_BYTES    = 50 * 1024 * 1024
_HISTORY_CAP             = 20
_SNAPSHOT_CAP            = 10
_LORAS_PER_ENTRY_CAP     = 10
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# ---------------------------------------------------------------------------
# Store helpers
# ---------------------------------------------------------------------------

_LOAD_CACHE: tuple[float, int, list[dict]] | None = None
_last_known_mtime = 0.0


def _load() -> list[dict]:
    global _LOAD_CACHE
    if not STORE_PATH.exists():
        _LOAD_CACHE = None
        return []
    try:
        st = STORE_PATH.stat()
        mtime, size = st.st_mtime, st.st_size
    except OSError:
        st = None; mtime = size = 0
    if _LOAD_CACHE is not None and st is not None:
        cm, cs, cd = _LOAD_CACHE
        if cm == mtime and cs == size:
            return list(cd)
    try:
        with STORE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        _LOAD_CACHE = None
        return _recover(e)
    except OSError:
        _LOAD_CACHE = None
        return []
    if isinstance(data, list):
        if st: _LOAD_CACHE = (mtime, size, list(data))
        return data
    if isinstance(data, dict) and isinstance(data.get("prompts"), list):
        items = data["prompts"]
        _save(items)
        return items
    _LOAD_CACHE = None
    return []


def _recover(err) -> list[dict]:
    ts = time.strftime("%Y%m%d-%H%M%S")
    q = STORE_PATH.with_name(f"{STORE_PATH.name}.broken-{ts}")
    try:
        STORE_PATH.rename(q)
    except OSError:
        return []
    if not SNAPSHOT_DIR.exists():
        return []
    snaps = sorted(SNAPSHOT_DIR.glob("*.json"))
    if not snaps:
        return []
    newest = snaps[-1]
    try:
        shutil.copy2(newest, STORE_PATH)
        with STORE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if isinstance(data, list):
        print(f"[🐸 Library] restored from snapshot {newest.name}")
        return data
    if isinstance(data, dict) and isinstance(data.get("prompts"), list):
        items = data["prompts"]
        _save(items)
        return items
    return []


def _save(items: list[dict]) -> None:
    global _last_known_mtime
    tmp = STORE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    tmp.replace(STORE_PATH)
    try:
        _last_known_mtime = STORE_PATH.stat().st_mtime
    except OSError:
        pass


def _snapshot(label: str) -> str:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        return ""
    safe = "".join(c if c.isalnum() else "_" for c in (label or "import"))[:32]
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = SNAPSHOT_DIR / f"{ts}-{safe}.json"
    try:
        shutil.copy2(STORE_PATH, out)
    except OSError as e:
        print(f"[🐸 Library] snapshot failed: {e}")
        return ""
    try:
        snaps = sorted(SNAPSHOT_DIR.glob("*.json"))
        for old in snaps[:-_SNAPSHOT_CAP]:
            try: old.unlink()
            except OSError: pass
    except OSError:
        pass
    return out.name


def _safe_id(v: str) -> str | None:
    return v if v and _ID_RE.match(v) else None


def _slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", (name or "").strip().lower())
    return s.strip("_")[:64]


def _unique_id(base: str, existing: set[str]) -> str:
    if not base:
        return uuid.uuid4().hex[:12]
    if base not in existing:
        return base
    n = 2
    trunk = base[:60]
    while True:
        cand = f"{trunk}_{n}"
        if cand not in existing:
            return cand
        n += 1


def _parse_tags(value) -> list[str]:
    if value is None:
        return []
    parts = value.split(",") if isinstance(value, str) else list(value)
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        t = str(p).strip()
        if not t:
            continue
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


def _parse_loras(value) -> list[dict]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except Exception:
            return []
    else:
        data = value
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for raw in data[:_LORAS_PER_ENTRY_CAP]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        try:
            sm = float(raw.get("strength_model", raw.get("strength", 1.0)) or 0.0)
        except Exception:
            sm = 1.0
        try:
            sc = float(raw.get("strength_clip", raw.get("strength", sm)) or 0.0)
        except Exception:
            sc = sm
        sm = max(-2.0, min(2.0, sm))
        sc = max(-2.0, min(2.0, sc))
        out.append({
            "name": name,
            "strength_model": sm,
            "strength_clip": sc,
            "triggers": str(raw.get("triggers") or "").strip(),
            "enabled": bool(raw.get("enabled", True)),
        })
    return out


def _image_path_for(pid: str) -> Path | None:
    for ext in _ALLOWED_IMAGE_EXT:
        p = IMAGES_DIR / f"{pid}{ext}"
        if p.exists():
            return p
    return None


def _delete_image(pid: str) -> None:
    for ext in _ALLOWED_IMAGE_EXT:
        p = IMAGES_DIR / f"{pid}{ext}"
        if p.exists():
            try: p.unlink()
            except OSError: pass


def _save_thumbnail_bytes(pid: str, data: bytes) -> str | None:
    try:
        from PIL import Image
    except ImportError as e:
        print(f"[🐸 Library] PIL unavailable: {e}")
        return None
    try:
        pil = Image.open(io.BytesIO(data))
        pil.load()
    except Exception as e:
        print(f"[🐸 Library] failed to decode image for {pid!r}: {e} ({len(data)} bytes)")
        return None
    return _save_thumbnail_pil(pid, pil)


def _save_image_bytes_raw(pid: str, data: bytes, hint_ext: str = ".jpg") -> str | None:
    """Write image bytes directly to IMAGES_DIR without re-encoding.
    Used during ZIP import — thumbnails are already correctly sized/formatted.
    Extension is detected from magic bytes; hint_ext is the fallback."""
    if not data:
        return None
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        ext = ".png"
    elif data[:2] == b'\xff\xd8':
        ext = ".jpg"
    elif data[:4] == b'RIFF' and len(data) > 12 and data[8:12] == b'WEBP':
        ext = ".webp"
    else:
        ext = hint_ext
    _delete_image(pid)
    out = IMAGES_DIR / f"{pid}{ext}"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return ext
    except OSError as e:
        print(f"[🐸 Library] failed to write image for {pid!r}: {e}")
        return None


def _save_thumbnail_pil(pid: str, pil) -> str | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        pil.thumbnail((_THUMBNAIL_MAX_EDGE, _THUMBNAIL_MAX_EDGE))
        has_alpha = pil.mode in ("RGBA", "LA") or (pil.mode == "P" and "transparency" in pil.info)
        _delete_image(pid)
        if has_alpha:
            if pil.mode != "RGBA":
                pil = pil.convert("RGBA")
            pil.save(IMAGES_DIR / f"{pid}.png", format="PNG", optimize=True)
            return ".png"
        if pil.mode != "RGB":
            pil = pil.convert("RGB")
        pil.save(IMAGES_DIR / f"{pid}.jpg", format="JPEG",
                 quality=_THUMBNAIL_JPEG_QUALITY, optimize=True, progressive=True)
        return ".jpg"
    except Exception as e:
        print(f"[🐸 Library] thumbnail save failed for {pid!r}: {e}")
        return None


def _now() -> float:
    return time.time()


def _touch(item: dict, *, created: bool) -> None:
    now = _now()
    if created or "created_at" not in item:
        item.setdefault("created_at", now)
    item["updated_at"] = now


def _push_history(item: dict) -> None:
    history = list(item.get("history") or [])
    snap: dict = {
        "ts": _now(),
        "name": item.get("name", ""),
        "text": item.get("text", ""),
        "tags": list(item.get("tags") or []),
    }
    if item.get("loras"):
        snap["loras"] = [dict(l) for l in item["loras"]]
    history.append(snap)
    item["history"] = history[-_HISTORY_CAP:]


def _maybe_push_history(item: dict, new_name: str, new_text: str,
                         new_tags: list, new_neg: str = "",
                         new_loras: list | None = None) -> None:
    if (item.get("name", "") == new_name
            and item.get("text", "") == new_text
            and item.get("negative", "") == new_neg
            and list(item.get("tags") or []) == list(new_tags or [])
            and list(item.get("loras") or []) == list(new_loras or [])):
        return
    _push_history(item)


def _notify() -> None:
    try:
        PromptServer.instance.send_sync("frog_library.updated", {})
    except Exception:
        pass


def _apply_loras(model, clip, loras: list[dict], strength_scale: float = 1.0):
    """Apply a list of LoRA entries to model+clip. Returns (model, clip, status_list)."""
    import comfy.utils
    import comfy.sd
    status: list[str] = []
    for entry in loras:
        if not entry.get("enabled", True):
            continue
        name = entry.get("name", "").strip()
        if not name:
            continue
        sm = entry.get("strength_model", 1.0) * strength_scale
        sc = entry.get("strength_clip",  1.0) * strength_scale
        try:
            if folder_paths is None:
                raise RuntimeError("folder_paths unavailable")
            path = folder_paths.get_full_path("loras", name)
            if not path:
                status.append(f"!{name}(missing)")
                continue
            lora = comfy.utils.load_torch_file(path, safe_load=True)
            model, clip = comfy.sd.load_lora_for_models(model, clip, lora, sm, sc)
            status.append(f"+{name}")
        except Exception as e:
            status.append(f"!{name}:{e}")
    return model, clip, status


def _start_watcher() -> None:
    global _last_known_mtime
    try:
        _last_known_mtime = STORE_PATH.stat().st_mtime if STORE_PATH.exists() else 0.0
    except OSError:
        _last_known_mtime = 0.0

    def loop():
        global _last_known_mtime
        pending = 0.0
        while True:
            time.sleep(2)
            try:
                try:
                    mtime = STORE_PATH.stat().st_mtime if STORE_PATH.exists() else 0.0
                except OSError:
                    continue
                if mtime == _last_known_mtime:
                    continue
                if pending != mtime:
                    pending = mtime
                    continue
                _last_known_mtime = mtime
                _notify()
            except Exception as e:
                print(f"[🐸 Library] watcher error: {e!r}")

    t = threading.Thread(target=loop, daemon=True, name="frog-library-watcher")
    t.start()


if "unittest" not in sys.modules and not os.environ.get("FROG_LIBRARY_NO_WATCHER"):
    _start_watcher()

# ---------------------------------------------------------------------------
# Node state — tag chip persistence across ComfyUI restarts (file-backed)
# ---------------------------------------------------------------------------

_NODE_STATE_PATH = DATA_DIR / "node_state.json"
_node_state: dict[str, dict] = {}


def _load_node_state() -> None:
    global _node_state
    if not _NODE_STATE_PATH.exists():
        return
    try:
        with _NODE_STATE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _node_state = data
    except Exception as e:
        print(f"[🐸 Library] could not load node_state.json: {e}")


def _save_node_state() -> None:
    try:
        tmp = _NODE_STATE_PATH.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(_node_state, f, indent=2, ensure_ascii=False)
        tmp.replace(_NODE_STATE_PATH)
    except Exception as e:
        print(f"[🐸 Library] could not save node_state.json: {e}")


_load_node_state()

# ---------------------------------------------------------------------------
# ComfyUI node class
# ---------------------------------------------------------------------------

class RibbityLibrary:
    DESCRIPTION = (
        "Visual prompt picker. Browse the gallery, click tiles to select "
        "one or many entries. The joined prompt text is emitted as STRING output."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt_id": ("STRING", {
                    "default": "", "multiline": False,
                    "tooltip": "Comma-separated entry IDs driven by the gallery widget.",
                }),
                "separator": ("STRING", {
                    "default": ", ", "multiline": False,
                    "tooltip": "Separator between joined entries.",
                }),
            },
            "optional": {
                "model": ("MODEL", {
                    "tooltip": "Wire to enable LoRA application from selected entries."}),
                "clip": ("CLIP", {
                    "tooltip": "Required alongside MODEL for LoRA application."}),
                "positive_passthrough": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Extra positive text combined with the library entry text.",
                }),
                "negative_passthrough": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Extra negative text combined with the library entry negative.",
                }),
                "strength_scale": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05,
                    "tooltip": "Multiplier applied to every LoRA strength. 0 = disable all LoRAs."}),
                "prompt_id_input": ("STRING", {
                    "forceInput": True,
                    "tooltip": "External STRING override for prompt_id.",
                }),
            },
        }

    RETURN_TYPES  = ("MODEL", "CLIP", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES  = ("model", "clip", "positive", "negative", "name", "id")
    FUNCTION      = "load_prompt"
    CATEGORY      = "🐸 Node Pack"

    @staticmethod
    def _split_ids(prompt_id: str) -> list[str]:
        return [p.strip() for p in (prompt_id or "").split(",") if p.strip()]

    @classmethod
    def IS_CHANGED(cls, prompt_id, separator=", ", positive_passthrough=None,
                   negative_passthrough=None, model=None, clip=None,
                   strength_scale=1.0, prompt_id_input=None):
        if prompt_id_input and prompt_id_input.strip():
            prompt_id = prompt_id_input
        ids = cls._split_ids(prompt_id)
        # IS_CHANGED is called on every queue run even when the node is cached,
        # so this is the reliable place to keep _library_state current for
        # downstream nodes (e.g. Thumbnail Saver) that read from it.
        _library_state["last_id"] = ids[0] if ids else ""
        lora_aware = model is not None and clip is not None
        with _lock:
            items = {i.get("id"): i for i in _load()}
        parts = []
        for pid in ids:
            entry = items.get(pid)
            if entry is None:
                parts.append(f"miss:{pid}")
            elif lora_aware:
                loras = entry.get("loras") or []
                sig = "|".join(
                    f"{l.get('name','')}:{l.get('strength_model',1):g}:"
                    f"{l.get('strength_clip',1):g}:{int(l.get('enabled',True))}"
                    for l in loras)
                parts.append(f"{entry.get('text','')}::{entry.get('negative','')}::{sig}")
            else:
                parts.append(f"{entry.get('text','')}::{entry.get('negative','')}")
        return f"{separator}::{strength_scale:g}::{'@@'.join(parts)}"

    def load_prompt(self, prompt_id: str, separator: str = ", ",
                    positive_passthrough=None, negative_passthrough=None,
                    model=None, clip=None, strength_scale: float = 1.0,
                    prompt_id_input=None):
        if prompt_id_input and prompt_id_input.strip():
            prompt_id = prompt_id_input
        ids = self._split_ids(prompt_id)
        # Publish the first resolved ID so downstream nodes (e.g. Thumbnail
        # Saver) can pick it up without needing an explicit wired connection.
        _library_state["last_id"] = ids[0] if ids else ""
        with _lock:
            items = {i.get("id"): i for i in _load()}
        pos, neg, entries, missing = [], [], [], []
        for pid in ids:
            entry = items.get(pid)
            if entry is None:
                missing.append(pid)
                continue
            entries.append(entry)
            if entry.get("text"):     pos.append(entry["text"])
            if entry.get("negative"): neg.append(entry["negative"])
        if missing:
            print(f"[🐸 Library] missing id(s): {missing}")

        model_out, clip_out = model, clip
        if model is not None and clip is not None and entries:
            try:
                patched_m, patched_c = model, clip
                for entry in entries:
                    loras = [l for l in (entry.get("loras") or []) if l.get("enabled", True)]
                    if not loras:
                        continue
                    patched_m, patched_c, status = _apply_loras(
                        patched_m, patched_c, loras, strength_scale)
                    print(f"[🐸 Library] LoRAs for {entry.get('name','?')}: {' '.join(status)}")
                model_out, clip_out = patched_m, patched_c
            except Exception as e:
                print(f"[🐸 Library] LoRA application failed: {e}")

        # Combine library text with optional passthrough strings.
        # Passthrough comes first so character/subject tags from the library
        # append naturally after the base quality/style text.
        lib_pos = separator.join(pos)
        lib_neg = separator.join(neg)

        def _combine(passthrough, lib_text):
            a = (passthrough or "").strip()
            b = (lib_text or "").strip()
            if a and b:  return a + separator + b
            return a or b

        name_out = entries[0].get("name", "") if len(entries) == 1 else ""
        id_out   = ids[0] if ids else ""
        return (model_out, clip_out,
                _combine(positive_passthrough, lib_pos),
                _combine(negative_passthrough, lib_neg),
                name_out,
                id_out)


NODE_CLASS_MAPPINGS        = {"FrogLibrary": RibbityLibrary}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogLibrary": "🐸 Library"}

# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

if _server is not None and web is not None:
    routes = _server.routes

    # --- list ---------------------------------------------------------------
    @routes.get("/frog_library/list")
    async def _list(req):
        with _lock:
            items = _load()
        result = []
        for item in items:
            entry = dict(item)
            entry["has_image"] = _image_path_for(entry.get("id", "")) is not None
            result.append(entry)
        return web.json_response({"prompts": result})

    # --- upsert -------------------------------------------------------------
    @routes.post("/frog_library/upsert")
    async def _upsert(req):
        reader = await req.multipart()
        fields: dict = {}
        image_data: bytes | None = None
        image_name: str = ""
        async for part in reader:
            if part.name == "image":
                image_data = await part.read()
                image_name = part.filename or ""
            else:
                fields[part.name] = (await part.read()).decode("utf-8", errors="replace")
        pid      = _safe_id((fields.get("id") or "").strip())
        name     = (fields.get("name") or "").strip()
        text     = (fields.get("text") or "").strip()
        negative = (fields.get("negative") or "").strip()
        tags     = _parse_tags(fields.get("tags", ""))
        notes    = (fields.get("notes") or "").strip()
        loras_raw = fields.get("loras")
        loras    = _parse_loras(loras_raw) if loras_raw is not None else None
        clear_img = fields.get("clear_image", "").strip() == "1"

        try:
            rating = int(fields.get("rating") or 0)
            rating = max(0, min(5, rating))
        except Exception:
            rating = 0

        if not name:
            return web.json_response({"error": "name required"}, status=400)

        with _lock:
            items = _load()
            existing_ids = {i.get("id") for i in items}
            if pid and pid not in existing_ids:
                # new entry with explicit id
                entry = {"id": pid}
                items.append(entry)
                created = True
            elif pid:
                entry = next((i for i in items if i.get("id") == pid), None)
                if entry is None:
                    entry = {"id": pid}
                    items.append(entry)
                    created = True
                else:
                    created = False
            else:
                pid = _unique_id(_slugify(name), existing_ids)
                entry = {"id": pid}
                items.append(entry)
                created = True

            _maybe_push_history(entry, name, text, tags, negative,
                                  loras if loras is not None else entry.get("loras"))
            entry.update({"name": name, "text": text, "negative": negative,
                           "tags": tags, "notes": notes, "rating": rating})
            if loras is not None:
                entry["loras"] = loras
            _touch(entry, created=created)

            if clear_img:
                _delete_image(pid)
            if image_data:
                _save_thumbnail_bytes(pid, image_data)
            entry["has_image"] = _image_path_for(pid) is not None

            _save(items)

        _notify()
        return web.json_response({"id": pid, "ok": True})

    # --- delete -------------------------------------------------------------
    @routes.post("/frog_library/delete")
    async def _delete(req):
        body = await req.json()
        pid = _safe_id((body.get("id") or "").strip())
        if not pid:
            return web.json_response({"error": "invalid id"}, status=400)
        with _lock:
            items = _load()
            items = [i for i in items if i.get("id") != pid]
            _save(items)
        _delete_image(pid)
        _notify()
        return web.json_response({"ok": True})

    # --- image --------------------------------------------------------------
    @routes.get("/frog_library/image/{pid}")
    async def _image(req):
        pid = req.match_info["pid"]
        if not _safe_id(pid):
            raise web.HTTPNotFound()
        path = _image_path_for(pid)
        if not path:
            raise web.HTTPNotFound()
        ct = "image/png" if path.suffix == ".png" else "image/jpeg"
        return web.Response(body=path.read_bytes(), content_type=ct)

    # --- tags ---------------------------------------------------------------
    @routes.get("/frog_library/tags")
    async def _tags(req):
        with _lock:
            items = _load()
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            for t in (item.get("tags") or []):
                k = t.lower()
                if k not in seen:
                    seen.add(k)
                    out.append(t)
        out.sort(key=str.lower)
        return web.json_response({"tags": out})

    # --- loras --------------------------------------------------------------
    @routes.get("/frog_library/loras")
    async def _loras(req):
        if folder_paths is None:
            return web.json_response({"loras": []})
        try:
            paths = folder_paths.get_filename_list("loras")
            return web.json_response({"loras": sorted(paths)})
        except Exception:
            return web.json_response({"loras": []})

    # --- bulk_delete --------------------------------------------------------
    @routes.post("/frog_library/bulk_delete")
    async def _bulk_delete(req):
        body = await req.json()
        ids = set(body.get("ids") or [])
        if not ids:
            return web.json_response({"ok": True, "deleted": 0})
        with _lock:
            items = _load()
            before = len(items)
            items = [i for i in items if i.get("id") not in ids]
            _save(items)
        for pid in ids:
            _delete_image(pid)
        _notify()
        return web.json_response({"ok": True, "deleted": before - len(items)})

    # --- duplicate ----------------------------------------------------------
    @routes.post("/frog_library/duplicate")
    async def _duplicate(req):
        body = await req.json()
        pid = _safe_id((body.get("id") or "").strip())
        new_name = (body.get("name") or "").strip()
        if not pid:
            return web.json_response({"error": "invalid id"}, status=400)
        with _lock:
            items = _load()
            src = next((i for i in items if i.get("id") == pid), None)
            if src is None:
                return web.json_response({"error": "not found"}, status=404)
            existing_ids = {i.get("id") for i in items}
            new_id = _unique_id(_slugify(new_name or src.get("name", "copy")), existing_ids)
            dup = copy.deepcopy(src)
            dup["id"] = new_id
            dup["name"] = new_name or f"{src.get('name','')} (copy)"
            dup.pop("history", None)
            _touch(dup, created=True)
            items.append(dup)
            _save(items)
        # Copy thumbnail if present
        src_img = _image_path_for(pid)
        if src_img:
            try:
                shutil.copy2(src_img, IMAGES_DIR / f"{new_id}{src_img.suffix}")
            except OSError:
                pass
        _notify()
        return web.json_response({"id": new_id, "ok": True})

    # --- reorder ------------------------------------------------------------
    @routes.post("/frog_library/reorder")
    async def _reorder(req):
        body = await req.json()
        ids: list[str] = body.get("ids") or []
        with _lock:
            items = _load()
            by_id = {i.get("id"): i for i in items}
            ordered = [by_id[pid] for pid in ids if pid in by_id]
            rest = [i for i in items if i.get("id") not in set(ids)]
            for idx, item in enumerate(ordered):
                item["order"] = idx
            _save(ordered + rest)
        return web.json_response({"ok": True})

    # --- history ------------------------------------------------------------
    @routes.get("/frog_library/history/{pid}")
    async def _history(req):
        pid = req.match_info["pid"]
        if not _safe_id(pid):
            raise web.HTTPNotFound()
        with _lock:
            items = _load()
        entry = next((i for i in items if i.get("id") == pid), None)
        if entry is None:
            raise web.HTTPNotFound()
        return web.json_response({"history": list(reversed(entry.get("history") or []))})

    # --- revert -------------------------------------------------------------
    @routes.post("/frog_library/revert")
    async def _revert(req):
        body = await req.json()
        pid = _safe_id((body.get("id") or "").strip())
        ts = body.get("ts")
        if not pid or ts is None:
            return web.json_response({"error": "id and ts required"}, status=400)
        with _lock:
            items = _load()
            entry = next((i for i in items if i.get("id") == pid), None)
            if entry is None:
                return web.json_response({"error": "not found"}, status=404)
            snap = next((h for h in (entry.get("history") or []) if h.get("ts") == ts), None)
            if snap is None:
                return web.json_response({"error": "snapshot not found"}, status=404)
            _push_history(entry)
            entry["name"] = snap.get("name", entry["name"])
            entry["text"] = snap.get("text", entry.get("text", ""))
            entry["tags"] = snap.get("tags", entry.get("tags", []))
            if "loras" in snap:
                entry["loras"] = snap["loras"]
            _touch(entry, created=False)
            _save(items)
        _notify()
        return web.json_response({"ok": True})

    # --- validate -----------------------------------------------------------
    @routes.get("/frog_library/validate")
    async def _validate(req):
        with _lock:
            items = _load()
        no_name  = [i["id"] for i in items if not i.get("name")]
        no_text  = [i["id"] for i in items if not i.get("text")]
        no_image = [i["id"] for i in items if not _image_path_for(i.get("id",""))]
        return web.json_response({
            "ok": True,
            "total": len(items),
            "no_name": no_name,
            "no_text": no_text,
            "no_image": no_image,
        })

    # --- fix_orphans --------------------------------------------------------
    @routes.post("/frog_library/fix_orphans")
    async def _fix_orphans(req):
        with _lock:
            items = _load()
        ids = {i.get("id") for i in items if i.get("id")}
        removed = 0
        for p in list(IMAGES_DIR.iterdir()):
            stem = p.stem
            if stem not in ids:
                try: p.unlink(); removed += 1
                except OSError: pass
        return web.json_response({"ok": True, "orphans_removed": removed})

    # --- restore_snapshot ---------------------------------------------------
    @routes.post("/frog_library/restore_snapshot")
    async def _restore_snapshot(req):
        body = await req.json()
        name = (body.get("name") or "").strip()
        # If no name supplied, restore the newest snapshot.
        if not name:
            snaps = sorted(SNAPSHOT_DIR.glob("*.json"))
            if not snaps:
                return web.json_response({"error": "no snapshots"}, status=404)
            name = snaps[-1].name
        if "/" in name or "\\" in name or ".." in name:
            return web.json_response({"error": "invalid name"}, status=400)
        src = SNAPSHOT_DIR / name
        if not src.is_file():
            return web.json_response({"error": "not found"}, status=404)
        _snapshot("pre_undo")
        with _lock:
            shutil.copy2(src, STORE_PATH)
            items = _load()
        _notify()
        return web.json_response({"ok": True, "restored_from": name, "entries": len(items)})

    # --- export (zip) -------------------------------------------------------
    @routes.post("/frog_library/export")
    async def _export(req):
        body = await req.json()
        ids_filter = set(body.get("ids") or [])
        with _lock:
            items = _load()
        if ids_filter:
            items = [i for i in items if i.get("id") in ids_filter]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            manifest = {"format": "prompt_library_v1", "prompts": []}
            for item in items:
                entry = {k: v for k, v in item.items() if k != "history"}
                pid = item.get("id", "")
                img = _image_path_for(pid)
                if img:
                    try:
                        from PIL import Image as PILImage
                        pil = PILImage.open(img)
                        pil.thumbnail((_EXPORT_THUMB_MAX_EDGE, _EXPORT_THUMB_MAX_EDGE))
                        ibuf = io.BytesIO()
                        fmt = "PNG" if img.suffix == ".png" else "JPEG"
                        kw = {} if fmt == "PNG" else {"quality": _EXPORT_THUMB_JPEG_Q,
                                                       "optimize": True}
                        if pil.mode not in ("RGB", "RGBA", "L"):
                            pil = pil.convert("RGB")
                        pil.save(ibuf, format=fmt, **kw)
                        zf.writestr(f"images/{pid}{img.suffix}", ibuf.getvalue())
                        entry["_image"] = f"images/{pid}{img.suffix}"
                    except Exception:
                        pass
                manifest["prompts"].append(entry)
            zf.writestr("prompts.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        buf.seek(0)
        resp = web.Response(body=buf.read(), content_type="application/zip")
        resp.headers["Content-Disposition"] = 'attachment; filename="rln_export.zip"'
        resp.headers["X-GrimmRibbity-Count"] = str(len(items))
        resp.headers["X-Ribbity-Count"] = str(len(items))
        return resp

    # --- import_csv ---------------------------------------------------------
    @routes.post("/frog_library/import_csv")
    async def _import_csv(req):
        reader = await req.multipart()
        csv_chunks: list[bytes] = []
        mode = "add_only"
        async for part in reader:
            if part.name == "file":
                while True:
                    chunk = await part.read_chunk(65536)
                    if not chunk:
                        break
                    csv_chunks.append(chunk)
                    if sum(len(c) for c in csv_chunks) > _MAX_IMPORT_CSV_BYTES:
                        break
            elif part.name == "mode":
                mode = (await part.read()).decode("utf-8", errors="replace").strip()
        file_data = b"".join(csv_chunks)
        if len(file_data) > _MAX_IMPORT_CSV_BYTES:
            return web.json_response({"error": "CSV too large"}, status=413)
        _snapshot("pre_csv_import")
        text_io = io.StringIO(file_data.decode("utf-8", errors="replace"))
        dialect = csv.Sniffer().sniff(text_io.read(4096))
        text_io.seek(0)
        rows = list(csv.DictReader(text_io, dialect=dialect))
        with _lock:
            items = _load()
            by_id = {i.get("id"): i for i in items}
            existing_ids = set(by_id)
            added = updated = skipped = 0
            errors: list[str] = []
            for row in rows:
                name = (row.get("name") or row.get("Name") or "").strip()
                text = (row.get("text") or row.get("prompt") or row.get("Prompt") or "").strip()
                if not name and not text:
                    skipped += 1
                    continue
                pid = _safe_id((row.get("id") or "").strip())
                if not pid:
                    pid = _unique_id(_slugify(name or text[:32]), existing_ids)
                if pid in by_id:
                    if mode == "add_only":
                        skipped += 1
                        continue
                    entry = by_id[pid]
                    _maybe_push_history(entry, name, text, _parse_tags(row.get("tags","")))
                    entry.update({
                        "name": name or entry.get("name",""),
                        "text": text or entry.get("text",""),
                        "negative": row.get("negative","").strip(),
                        "tags": _parse_tags(row.get("tags","")),
                    })
                    _touch(entry, created=False)
                    updated += 1
                else:
                    entry = {
                        "id": pid, "name": name, "text": text,
                        "negative": row.get("negative","").strip(),
                        "tags": _parse_tags(row.get("tags","")),
                    }
                    _touch(entry, created=True)
                    items.append(entry)
                    by_id[pid] = entry
                    existing_ids.add(pid)
                    added += 1
            _save(items)
        _notify()
        return web.json_response({"ok": True, "added": added, "updated": updated,
                                   "skipped": skipped, "errors": errors})

    # --- import_zip ---------------------------------------------------------
    @routes.post("/frog_library/import_zip")
    async def _import_zip(req):
        reader = await req.multipart()
        zip_chunks: list[bytes] = []
        mode = "add_only"
        async for part in reader:
            if part.name == "file":
                while True:
                    chunk = await part.read_chunk(65536)
                    if not chunk:
                        break
                    zip_chunks.append(chunk)
                    if sum(len(c) for c in zip_chunks) > _MAX_IMPORT_ZIP_BYTES:
                        break
            elif part.name == "mode":
                mode = (await part.read()).decode("utf-8", errors="replace").strip()
        zip_data = b"".join(zip_chunks)
        if len(zip_data) > _MAX_IMPORT_ZIP_BYTES:
            return web.json_response({"error": "ZIP too large"}, status=413)
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_data))
        except zipfile.BadZipFile:
            return web.json_response({"error": "not a valid ZIP"}, status=400)
        total_uncompressed = sum(i.file_size for i in zf.infolist())
        if total_uncompressed > _MAX_IMPORT_ZIP_UNCOMPRESSED:
            return web.json_response({"error": "ZIP expands too large"}, status=413)
        try:
            manifest_data = zf.read("prompts.json")
            manifest = json.loads(manifest_data)
        except Exception:
            return web.json_response({"error": "missing or invalid prompts.json"}, status=400)
        new_items = manifest.get("prompts") if isinstance(manifest, dict) else manifest
        if not isinstance(new_items, list):
            return web.json_response({"error": "invalid manifest format"}, status=400)

        # Build a lookup: entry_id → zip path, covering both the legacy
        # "_image" manifest field AND the bare images/{id}.ext naming that
        # GrimmRibbity uses (no _image field in the manifest).
        zip_names = zf.namelist()
        zip_image_lookup: dict[str, str] = {}
        for zname in zip_names:
            if zname.endswith("/"):
                continue
            p = Path(zname)
            if p.suffix.lower() in _ALLOWED_IMAGE_EXT:
                zip_image_lookup[p.stem] = zname   # stem (= entry id) → zip path

        print(f"[🐸 Library] import_zip: {len(new_items)} entries, "
              f"{len(zip_image_lookup)} images in zip")

        _snapshot("pre_zip_import")

        # ── Phase 1: update the JSON store (lock held only for data, not I/O) ─
        pending_images: list[tuple[str, str]] = []  # (pid, zip_path)
        with _lock:
            items = _load()
            by_id = {i.get("id"): i for i in items}
            existing_ids = set(by_id)
            added = updated = skipped = 0
            for entry in new_items:
                if not isinstance(entry, dict): continue
                pid = _safe_id((entry.get("id") or "").strip())
                name = (entry.get("name") or "").strip()
                if not pid:
                    pid = _unique_id(_slugify(name or "entry"), existing_ids)
                    entry["id"] = pid
                img_path = entry.pop("_image", None)
                if pid in by_id:
                    if mode == "add_only":
                        skipped += 1
                    else:
                        tgt = by_id[pid]
                        tgt.update({k: v for k, v in entry.items()
                                     if k not in ("id", "history", "created_at")})
                        _touch(tgt, created=False)
                        updated += 1
                else:
                    entry["id"] = pid
                    _touch(entry, created=True)
                    items.append(entry)
                    by_id[pid] = entry
                    existing_ids.add(pid)
                    added += 1
                # Queue thumbnail save — prefer explicit _image, else id-based lookup
                zip_path = img_path or zip_image_lookup.get(pid)
                if zip_path:
                    pending_images.append((pid, zip_path))
            _save(items)

        # ── Phase 2: write thumbnails outside the lock ────────────────────────
        print(f"[🐸 Library] writing {len(pending_images)} thumbnails to {IMAGES_DIR}")
        saved = errors = skipped_existing = 0
        for pid, zip_path in pending_images:
            if _image_path_for(pid):
                skipped_existing += 1
                continue
            try:
                img_bytes = zf.read(zip_path)
                hint = Path(zip_path).suffix or ".jpg"
                result = _save_image_bytes_raw(pid, img_bytes, hint)
                if result:
                    saved += 1
                else:
                    errors += 1
                    print(f"[🐸 Library] save returned None for {pid!r}")
            except Exception as e:
                errors += 1
                print(f"[🐸 Library] thumbnail error {pid!r}: {e}")
        print(f"[🐸 Library] thumbnails: {saved} saved, {skipped_existing} already existed, "
              f"{errors} errors")

        _notify()
        return web.json_response({"ok": True, "added": added, "updated": updated,
                                   "skipped": skipped, "thumbnails_saved": saved})

    # --- node_state (tag persistence) ---------------------------------------
    @routes.get("/frog_library/node_state")
    async def _node_state_get(req):
        node_id = req.rel_url.query.get("node_id", "anon")
        state = _node_state.get(node_id, {})
        return web.json_response({"activeTags": state.get("activeTags", [])})

    @routes.post("/frog_library/node_state")
    async def _node_state_set(req):
        body = await req.json()
        node_id = str(body.get("node_id") or "anon")
        tags = body.get("activeTags")
        if isinstance(tags, list):
            _node_state[node_id] = {"activeTags": [str(t) for t in tags]}
            _save_node_state()
        return web.json_response({"ok": True})

    # --- scan_loras ---------------------------------------------------------
    @routes.post("/frog_library/scan_loras")
    async def _scan_loras(req):
        if folder_paths is None:
            return web.json_response({"loras": [], "errors": []})
        try:
            paths = folder_paths.get_filename_list("loras")
            return web.json_response({"loras": sorted(paths), "errors": []})
        except Exception as e:
            return web.json_response({"loras": [], "errors": [str(e)]})

    print("[🐸 Library] HTTP routes registered at /frog_library/*")
