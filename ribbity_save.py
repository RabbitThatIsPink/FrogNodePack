"""
🐸-Pack — Save Nodes
Two nodes:
  • RibbitySaveA1111    — saves with A1111 parameters chunk (no hashing)
  • RibbitySaveHashEmbed — saves with A1111 parameters chunk + SHA256 hashes

Both nodes:
  - Auto-extract metadata from the running workflow
  - Support PNG / JPG / WEBP output
  - Support custom output path
  - Are fully independent of any PromptLibrary system
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

try:
    import folder_paths
except ImportError:
    folder_paths = None

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
HASH_CACHE_PATH = DATA_DIR / "hash_cache.json"

# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

_DATE_TOKEN_MAP = [
    ("yyyy", "%Y"), ("yy", "%y"),
    ("MMMM", "%B"), ("MMM", "%b"), ("MM", "%m"),
    ("dddd", "%A"), ("ddd", "%a"), ("dd", "%d"),
    ("HH", "%H"), ("hh", "%I"), ("mm", "%M"), ("ss", "%S"), ("tt", "%p"),
]
_DATE_TOKEN_RE = re.compile(r"%date:([^%]+)%")


def _expand_filename_tokens(prefix: str, *, now=None) -> str:
    if "%date:" not in prefix:
        return prefix
    if now is None:
        now = time.localtime()

    def _replace(match: re.Match) -> str:
        fmt = match.group(1)
        for src, dst in _DATE_TOKEN_MAP:
            fmt = fmt.replace(src, dst)
        try:
            return time.strftime(fmt, now)
        except (ValueError, TypeError):
            return match.group(0)

    return _DATE_TOKEN_RE.sub(_replace, prefix)


# ---------------------------------------------------------------------------
# Hash cache (Hash Embed node only)
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_HASH_CACHE_MAX_ENTRIES = 4096


def _load_hash_cache() -> dict:
    if not HASH_CACHE_PATH.exists():
        return {}
    try:
        with HASH_CACHE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_hash_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if len(cache) > _HASH_CACHE_MAX_ENTRIES:
        keep = list(cache.items())[-_HASH_CACHE_MAX_ENTRIES:]
        cache = dict(keep)
    tmp = HASH_CACHE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)
    tmp.replace(HASH_CACHE_PATH)


def _file_signature(path: str) -> str | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return f"{st.st_size}|{int(st.st_mtime)}"


def _compute_sha256(path: str) -> str:
    try:
        import comfy.model_management as _mm
        check_interrupt = _mm.throw_exception_if_processing_interrupted
    except (ImportError, ModuleNotFoundError, AttributeError):
        check_interrupt = None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if check_interrupt is not None:
                check_interrupt()
            h.update(chunk)
    return h.hexdigest()


def get_cached_sha256(label: str, full_path: str) -> str | None:
    sig = _file_signature(full_path)
    if sig is None:
        return None
    key = f"{label}|{sig}"
    with _cache_lock:
        cache = _load_hash_cache()
        if key in cache:
            return cache[key]
    sha = _compute_sha256(full_path)
    with _cache_lock:
        cache = _load_hash_cache()
        cache[key] = sha
        _save_hash_cache(cache)
    return sha


# ---------------------------------------------------------------------------
# Model / LoRA folder scanning
# ---------------------------------------------------------------------------

_MODEL_FOLDERS = ("checkpoints", "diffusion_models", "unet")
_LORA_FOLDER   = "loras"
_NONE_LABEL    = "(none)"
_PREFIX_SEP    = "::"


def _list_models_in_folder(folder: str) -> list[str]:
    if folder_paths is None:
        return []
    try:
        return folder_paths.get_filename_list(folder)
    except Exception:
        return []


def list_all_model_choices() -> list[str]:
    seen_paths:  set[str] = set()
    seen_labels: set[str] = set()
    out: list[str] = [_NONE_LABEL]
    for folder in _MODEL_FOLDERS:
        for name in _list_models_in_folder(folder):
            full = None
            if folder_paths is not None:
                try:
                    full = folder_paths.get_full_path(folder, name)
                except Exception:
                    full = None
            key = os.path.realpath(full) if full else f"{folder}::{name}"
            if key in seen_paths:
                continue
            label = f"{folder}{_PREFIX_SEP}{name}"
            if label in seen_labels:
                continue
            seen_paths.add(key)
            seen_labels.add(label)
            out.append(label)
    return out


def resolve_model_path(label: str) -> tuple[str, str] | None:
    if not label or label == _NONE_LABEL or _PREFIX_SEP not in label:
        return None
    folder, name = label.split(_PREFIX_SEP, 1)
    if folder_paths is None:
        return None
    try:
        full = folder_paths.get_full_path(folder, name)
    except Exception:
        return None
    if not full or not os.path.isfile(full):
        return None
    return name, full


def resolve_lora_path(name: str) -> str | None:
    if not name or name == _NONE_LABEL:
        return None
    if folder_paths is None:
        return None
    try:
        full = folder_paths.get_full_path(_LORA_FOLDER, name)
    except Exception:
        return None
    return full if full and os.path.isfile(full) else None


# ---------------------------------------------------------------------------
# Workflow introspection
# ---------------------------------------------------------------------------

_MODEL_LOADER_TYPES = {
    "CheckpointLoaderSimple": ("ckpt_name", "checkpoints"),
    "CheckpointLoader":       ("ckpt_name", "checkpoints"),
    "UNETLoader":             ("unet_name", "diffusion_models"),
    "DiffusionModelLoader":   ("model_name", "diffusion_models"),
    "RibbityLoader":          ("diffusion_model", "diffusion_models"),
    "FrogLoader":             ("diffusion_model", "diffusion_models"),
}

# Library nodes that apply LoRAs internally from stored entries.
# Maps class_type → path to that pack's prompts.json relative to custom_nodes/.
_LIBRARY_NODE_STORES = {
    "FrogLibrary":       ROOT / "data" / "prompts.json",
    "RibbityLibraryNode": ROOT.parent / "RibbityLibraryNode" / "data" / "prompts.json",
    "PromptLibrary":      ROOT.parent / "Ribbity_Node_Suite" / "data" / "prompts.json",
    "PromptLibraryStyle": ROOT.parent / "Ribbity_Node_Suite" / "data" / "prompts.json",
}


def _load_library_loras(class_type: str, prompt_id: str,
                         strength_scale: float = 1.0) -> list[tuple[str, float]]:
    """Return [(lora_name, effective_strength)] for all enabled LoRAs attached
    to the selected library entries, scaled by strength_scale."""
    store_path = _LIBRARY_NODE_STORES.get(class_type)
    if not store_path or not store_path.exists():
        return []
    try:
        with store_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        items = data["prompts"] if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
    except Exception:
        return []

    by_id = {item.get("id"): item for item in items if isinstance(item, dict)}
    ids   = [p.strip() for p in (prompt_id or "").split(",") if p.strip()]
    out: list[tuple[str, float]] = []
    for pid in ids:
        entry = by_id.get(pid)
        if not entry:
            continue
        for lora in (entry.get("loras") or []):
            if not lora.get("enabled", True):
                continue
            name = (lora.get("name") or "").strip()
            if not name:
                continue
            sm = float(lora.get("strength_model", 1.0)) * strength_scale
            out.append((name, sm))
    return out
_LORA_LOADER_TYPES = {
    "LoraLoader":          ("lora_name", "strength_model"),
    "LoraLoaderModelOnly": ("lora_name", "strength_model"),
}
_RGTHREE_POWER_LORA_TYPE = "Power Lora Loader (rgthree)"
_RGTHREE_LORA_STACK_TYPE = "Lora Loader Stack (rgthree)"
_KSAMPLER_TYPES = {
    "KSampler", "KSamplerAdvanced",
    "SamplerCustom", "SamplerCustomAdvanced",
    "KSampler (Efficient)", "KSampler SDXL (Eff.)", "KSampler Adv. (Efficient)",
    "RibbityKSampler",
    "FrogKSampler",
}
_TEXT_ENCODE_TYPES = {
    "CLIPTextEncode", "CLIPTextEncodeSDXL",
    "BNK_CLIPTextEncodeAdvanced",
    "ImpactWildcardEncode",
    "RibbityCLIPTextEncode",
    "FrogCLIPTextEncode",
}
_MODEL_PASSTHROUGH_TYPES = {
    "ModelSamplingDiscrete", "ModelSamplingSD3", "ModelSamplingFlux",
    "FreeU", "FreeU_V2", "PerturbedAttentionGuidance",
    "RescaleCFG", "PerpNeg",
}
_SAMPLER_PARAM_KEYS = ("seed", "steps", "cfg", "sampler_name", "scheduler", "noise_seed")
_TEXT_LINK_MAX_DEPTH = 4


def _link_source(value):
    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], (str, int)):
        return str(value[0])
    return None


def _walk_model_chain(prompt: dict, start_node_id: str | None):
    loras: list[tuple[str, float]] = []
    seen:  set[str] = set()
    current = start_node_id
    while current and current in prompt and current not in seen:
        seen.add(current)
        node   = prompt.get(current) or {}
        ctype  = node.get("class_type")
        inputs = node.get("inputs") or {}

        if ctype in _LORA_LOADER_TYPES:
            name_key, strength_key = _LORA_LOADER_TYPES[ctype]
            lname = inputs.get(name_key)
            try:
                strength = float(inputs.get(strength_key, 1.0))
            except (TypeError, ValueError):
                strength = 1.0
            if isinstance(lname, str) and lname:
                loras.append((lname, strength))
            current = _link_source(inputs.get("model"))
            continue

        if ctype in ("RibbityLoraLoader", "FrogLoraLoader"):
            for i in range(1, 5):
                lname = inputs.get(f"lora_{i}")
                if not isinstance(lname, str) or lname in (None, "None", ""):
                    continue
                try:
                    strength = float(inputs.get(f"strength_{i}", 1.0))
                except (TypeError, ValueError):
                    strength = 1.0
                loras.append((lname, strength))
            current = _link_source(inputs.get("model"))
            continue

        if ctype == _RGTHREE_LORA_STACK_TYPE:
            slot_loras: list[tuple[str, float]] = []
            for i in range(1, 5):
                lname = inputs.get(f"lora_0{i}") or inputs.get(f"lora_{i:02d}")
                if not isinstance(lname, str) or lname in (None, "None", ""):
                    continue
                try:
                    strength = float(inputs.get(f"strength_0{i}", 1.0))
                except (TypeError, ValueError):
                    strength = 1.0
                if strength != 0:
                    slot_loras.append((lname, strength))
            for entry in reversed(slot_loras):
                loras.append(entry)
            current = _link_source(inputs.get("model"))
            continue

        if ctype == _RGTHREE_POWER_LORA_TYPE:
            slots = []
            for key, value in inputs.items():
                if not key.startswith("lora_") or not isinstance(value, dict):
                    continue
                try:
                    idx = int(key.split("_", 1)[1])
                except ValueError:
                    continue
                if not value.get("on", True):
                    continue
                lname = value.get("lora")
                if not isinstance(lname, str) or not lname:
                    continue
                try:
                    strength = float(value.get("strength", 1.0))
                except (TypeError, ValueError):
                    strength = 1.0
                slots.append((idx, lname, strength))
            for _, lname, strength in sorted(slots, reverse=True):
                loras.append((lname, strength))
            current = _link_source(inputs.get("model"))
            continue

        if ctype in _LIBRARY_NODE_STORES:
            pid = inputs.get("prompt_id", "")
            if isinstance(pid, str) and pid.strip():
                try:
                    ss = float(inputs.get("strength_scale", 1.0))
                except (TypeError, ValueError):
                    ss = 1.0
                for entry in reversed(_load_library_loras(ctype, pid, ss)):
                    loras.append(entry)
            current = _link_source(inputs.get("model"))
            continue

        if ctype in _MODEL_LOADER_TYPES:
            name_key, folder = _MODEL_LOADER_TYPES[ctype]
            mname = inputs.get(name_key)
            if isinstance(mname, str) and mname:
                return f"{folder}{_PREFIX_SEP}{mname}", list(reversed(loras))
            return None, list(reversed(loras))

        if ctype in _MODEL_PASSTHROUGH_TYPES:
            current = _link_source(inputs.get("model"))
            continue

        current = _link_source(inputs.get("model"))
    return None, list(reversed(loras))


_FROG_CLIP_TYPES = {"RibbityCLIPTextEncode", "FrogCLIPTextEncode"}


def _resolve_text_link(prompt: dict, link_value, depth: int = 0) -> str:
    if depth > _TEXT_LINK_MAX_DEPTH:
        return ""
    src = _link_source(link_value)
    if not src or src not in prompt:
        return ""
    node   = prompt[src] or {}
    ctype  = node.get("class_type") or ""
    inputs = node.get("inputs") or {}

    # Our combined CLIP node:
    # Output slots: 0=Positive cond, 1=Negative cond, 2=positive_text, 3=negative_text
    # Slots 2 and 3 are the exact strings that were encoded — use those directly.
    if ctype in _FROG_CLIP_TYPES:
        output_idx = link_value[1] if isinstance(link_value, list) and len(link_value) >= 2 else 0
        # Map conditioning slot to text slot (0->2, 1->3) or read text slot directly
        if output_idx in (0, 2):
            key = "positive"
        else:
            key = "negative"
        v = inputs.get(key)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, list):
            resolved = _resolve_text_link(prompt, v, depth + 1)
            if resolved:
                return resolved
        return ""

    if ctype in _TEXT_ENCODE_TYPES:
        for key in ("text", "text_g", "text_l", "positive", "negative"):
            v = inputs.get(key)
            if isinstance(v, str) and v.strip():
                return v
            if isinstance(v, list):
                resolved = _resolve_text_link(prompt, v, depth + 1)
                if resolved:
                    return resolved

    for key in ("text", "prompt", "string", "value", "string_input", "input_tags", "sorted_prompt", "output", "resolved_text", "merged_prompt"):
        v = inputs.get(key)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, list):
            resolved = _resolve_text_link(prompt, v, depth + 1)
            if resolved:
                return resolved
    return ""


def _resolve_literal(prompt: dict, value, *, candidate_keys: tuple = (), max_hops: int = 4):
    visited: set[str] = set()
    cur = value
    for _ in range(max_hops):
        if not isinstance(cur, list) or len(cur) != 2:
            break
        src_id = str(cur[0])
        if src_id in visited:
            return None
        visited.add(src_id)
        src = prompt.get(src_id)
        if not isinstance(src, dict):
            return None
        src_in = src.get("inputs") or {}
        keys = list(candidate_keys) or list(src_in.keys())
        for k in keys:
            if k not in src_in:
                continue
            v = src_in[k]
            if not isinstance(v, list):
                return v
        next_step = None
        for k in (candidate_keys or src_in.keys()):
            v = src_in.get(k)
            if isinstance(v, list) and len(v) == 2:
                next_step = v
                break
        if next_step is None:
            return None
        cur = next_step
    return None


def _find_primary_sampler(prompt: dict) -> tuple[str | None, dict | None]:
    candidates = [(nid, n) for nid, n in prompt.items()
                  if (n or {}).get("class_type") in _KSAMPLER_TYPES]
    if not candidates:
        return None, None

    def _sort_key(pair):
        nid, _ = pair
        try:
            return (0, int(nid))
        except ValueError:
            return (1, nid)

    candidates.sort(key=_sort_key)
    return candidates[-1]


def extract_workflow_metadata(prompt: dict | None) -> dict:
    if not isinstance(prompt, dict) or not prompt:
        return {}

    out: dict = {}
    _RESOLVE_KEYS: dict[str, tuple] = {
        "seed":         ("seed", "value", "int", "noise_seed"),
        "noise_seed":   ("noise_seed", "seed", "value", "int"),
        "steps":        ("steps", "value", "int"),
        "cfg":          ("cfg", "value", "float", "number"),
        "sampler_name": ("sampler_name", "value", "string"),
        "scheduler":    ("scheduler", "value", "string"),
    }

    sampler_id, sampler = _find_primary_sampler(prompt)
    if sampler is not None:
        s_in = sampler.get("inputs") or {}
        for key in _SAMPLER_PARAM_KEYS:
            if key not in s_in:
                continue
            raw = s_in[key]
            if isinstance(raw, list):
                resolved = _resolve_literal(prompt, raw,
                                            candidate_keys=_RESOLVE_KEYS.get(key, (key,)))
                if resolved is not None and not isinstance(resolved, list):
                    out[key] = resolved
            else:
                out[key] = raw

        inputs = sampler.get("inputs") or {}
        model_link = inputs.get("model")
        pos_link   = inputs.get("positive")
        neg_link   = inputs.get("negative")

        model_label, loras = _walk_model_chain(prompt, _link_source(model_link))
        if model_label:
            out["model_label"] = model_label
        if loras:
            out["loras"] = loras

        pos = _resolve_text_link(prompt, pos_link)
        neg = _resolve_text_link(prompt, neg_link)
        if pos:
            out["positive"] = pos
        if neg:
            out["negative"] = neg

    if "model_label" not in out:
        for nid, n in prompt.items():
            ctype = (n or {}).get("class_type")
            if ctype in _MODEL_LOADER_TYPES:
                name_key, folder = _MODEL_LOADER_TYPES[ctype]
                mname = (n.get("inputs") or {}).get(name_key)
                if isinstance(mname, str) and mname:
                    out["model_label"] = f"{folder}{_PREFIX_SEP}{mname}"
                    break

    if "seed" in out and not isinstance(out["seed"], int):
        try:
            out["seed"] = int(out["seed"])
        except (TypeError, ValueError):
            out.pop("seed", None)
    if "noise_seed" in out and "seed" not in out:
        try:
            out["seed"] = int(out["noise_seed"])
        except (TypeError, ValueError):
            pass
        out.pop("noise_seed", None)
    if "steps" in out and not isinstance(out["steps"], int):
        try:
            out["steps"] = int(out["steps"])
        except (TypeError, ValueError):
            out.pop("steps", None)
    if "cfg" in out:
        try:
            out["cfg"] = float(out["cfg"])
        except (TypeError, ValueError):
            out.pop("cfg", None)

    return out


# ---------------------------------------------------------------------------
# Metadata string builder
# ---------------------------------------------------------------------------

_LATIN1_FALLBACKS = {
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "--",
    "\u2015": "--", "\u2018": "'", "\u2019": "'", "\u201a": ",",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2026": "...",
}


def _to_latin1_safe(s: str) -> str:
    if s is None:
        return s
    out = s.translate({ord(k): v for k, v in _LATIN1_FALLBACKS.items()})
    try:
        out.encode("latin-1")
        return out
    except UnicodeEncodeError:
        return out.encode("latin-1", errors="replace").decode("latin-1")


def _strip_ext(name: str) -> str:
    return os.path.splitext(os.path.basename(name))[0]


def build_a1111_parameters(
    *,
    positive: str,
    negative: str,
    width: int,
    height: int,
    steps,
    sampler_name,
    scheduler,
    cfg,
    seed,
    model_name,
    model_sha256=None,
    loras=None,       # list of (name, sha256_or_None, strength)
) -> str:
    parts: list[str] = []
    parts.append((positive or "").strip())
    if negative and negative.strip():
        parts.append(f"Negative prompt: {negative.strip()}")

    fields: list[str] = []
    if steps is not None:
        fields.append(f"Steps: {int(steps)}")
    if sampler_name:
        sampler = sampler_name
        if scheduler and scheduler != "normal":
            sampler = f"{sampler_name} {scheduler}"
        fields.append(f"Sampler: {sampler}")
    if cfg is not None:
        fields.append(f"CFG scale: {cfg:g}")
    if seed is not None:
        fields.append(f"Seed: {int(seed)}")
    fields.append(f"Size: {int(width)}x{int(height)}")

    if model_sha256:
        fields.append(f"Model hash: {model_sha256[:10]}")
    if model_name:
        fields.append(f"Model: {_strip_ext(model_name)}")

    hashes: dict = {}
    if model_sha256:
        hashes["model"] = model_sha256[:10]
    for lname, lsha, _strength in (loras or []):
        if lsha:
            hashes[f"lora:{_strip_ext(lname)}"] = lsha[:10]
    if hashes:
        fields.append(f"Hashes: {json.dumps(hashes, separators=(',', ':'))}")

    if loras:
        lora_tokens = " ".join(f"<lora:{_strip_ext(n)}:{s:g}>" for n, _, s in loras)
        if lora_tokens:
            parts[0] = f"{parts[0]} {lora_tokens}".strip()

    if fields:
        parts.append(", ".join(fields))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Shared save logic
# ---------------------------------------------------------------------------

def _resolve_output_dir(filename_prefix: str, output_path: str, images):
    default_output = folder_paths.get_output_directory() if folder_paths else "output"
    custom = (output_path or "").strip()
    if custom:
        resolved = os.path.expanduser(custom)
        if not os.path.isabs(resolved):
            resolved = os.path.join(default_output, resolved)
        os.makedirs(resolved, exist_ok=True)
        output_dir = resolved
    else:
        output_dir = default_output

    if folder_paths is not None and not custom:
        full_prefix, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, output_dir, images.shape[2], images.shape[1]
        )
    else:
        base = os.path.basename(filename_prefix) or "image"
        existing = []
        try:
            for f in os.listdir(output_dir):
                if f.startswith(base + "_") and f.endswith(".png"):
                    try:
                        existing.append(int(f[len(base) + 1:].split("_")[0]))
                    except ValueError:
                        pass
        except FileNotFoundError:
            pass
        counter = (max(existing) + 1) if existing else 0
        full_prefix, filename, subfolder = output_dir, base, ""

    return full_prefix, filename, counter, subfolder, custom


def _save_frames(images, params_str, full_prefix, filename, counter, subfolder,
                 custom, image_format, show_preview, prompt, extra_pnginfo,
                 append_counter=True):
    from PIL import Image, PngImagePlugin
    import numpy as np

    try:
        import comfy.model_management as _mm
        check_interrupt = _mm.throw_exception_if_processing_interrupted
    except (ImportError, ModuleNotFoundError, AttributeError):
        check_interrupt = None

    prompt_text = json.dumps(prompt) if prompt is not None else None
    extra_text: list[tuple[str, str]] = []
    if extra_pnginfo is not None:
        for k, v in extra_pnginfo.items():
            extra_text.append((k, json.dumps(v)))

    results = []
    batch_size = len(images)
    _fmt = image_format.upper().replace("JPEG", "JPG")

    for frame_idx, frame in enumerate(images):
        if check_interrupt is not None:
            check_interrupt()

        arr = frame
        if hasattr(arr, "cpu"):
            arr = arr.cpu().numpy()
        arr = (arr.clip(0, 1) * 255).astype(np.uint8)
        pil = Image.fromarray(arr)

        if append_counter:
            if batch_size <= 1:
                file_name = f"{filename}_{counter:05d}_.png"
            else:
                file_name = f"{filename}_{counter:05d}_{frame_idx:02d}_.png"
        else:
            if batch_size <= 1:
                file_name = f"{filename}.png"
            else:
                file_name = f"{filename}_{frame_idx:02d}.png"

        ext = ".jpg" if _fmt == "JPG" else f".{_fmt.lower()}"
        if file_name.endswith(".png") and ext != ".png":
            file_name = file_name[:-4] + ext
        counter += 1

        full_path = os.path.join(full_prefix, file_name)

        if _fmt == "PNG":
            png_info = PngImagePlugin.PngInfo()
            png_info.add_text("parameters", _to_latin1_safe(params_str))
            if prompt_text is not None:
                png_info.add_text("prompt", prompt_text)
            for k, v in extra_text:
                png_info.add_text(k, v)
            pil.save(full_path, format="PNG", pnginfo=png_info, compress_level=4)
        elif _fmt == "JPG":
            pil.convert("RGB").save(full_path, format="JPEG", quality=95, optimize=True)
        elif _fmt == "WEBP":
            pil.save(full_path, format="WEBP", quality=95, method=6)

        preview_type      = "output"
        preview_subfolder = subfolder
        preview_filename  = file_name

        if custom and folder_paths is not None:
            try:
                import shutil as _shutil
                _temp_dir = folder_paths.get_temp_directory()
                os.makedirs(_temp_dir, exist_ok=True)
                _temp_path = os.path.join(_temp_dir, file_name)
                _shutil.copy2(full_path, _temp_path)
                preview_type      = "temp"
                preview_subfolder = ""
                preview_filename  = file_name
            except Exception as _pe:
                print(f"[🐸-Pack Save] preview copy failed: {_pe}")

        if show_preview:
            results.append({
                "filename":  preview_filename,
                "subfolder": preview_subfolder,
                "type":      preview_type,
            })

    return results


# ---------------------------------------------------------------------------
# Node 1 — 🐸 Save: A1111
# Writes A1111 parameters chunk. No SHA256 hashing.
# ---------------------------------------------------------------------------

_AUTO_LABEL = "(auto-detect from workflow)"


class RibbitySaveA1111:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images":          ("IMAGE",),
                "filename_prefix": ("STRING", {
                    "default": "RibbityPack",
                    "tooltip": "Prefix for saved files. Supports %date:yyyy-MM-dd% tokens.",
                }),
                "image_format": (["PNG", "JPG", "WEBP"], {"default": "PNG"}),
            },
            "optional": {
                "output_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Leave blank for ComfyUI/output",
                }),
                "show_preview":    ("BOOLEAN", {"default": True}),
                "positive_text":   ("STRING", {"forceInput": True}),
                "negative_text":   ("STRING", {"forceInput": True}),
            },
            "hidden": {
                "prompt":       "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES  = ("INT", "STRING")
    RETURN_NAMES  = ("seed", "debug")
    OUTPUT_NODE   = True
    FUNCTION      = "save"
    CATEGORY      = "🐸 Node Pack"

    def save(self, images, filename_prefix, image_format,
             output_path="", show_preview=True,
             positive_text=None, negative_text=None,
             prompt=None, extra_pnginfo=None):

        filename_prefix = _expand_filename_tokens(filename_prefix or "RibbityPack")
        meta = extract_workflow_metadata(prompt)

        model_label    = meta.get("model_label")
        model_resolved = resolve_model_path(model_label) if model_label else None
        model_name     = model_resolved[0] if model_resolved else None

        loras_raw = meta.get("loras", [])
        # A1111 node: no hashing — sha256 is None for all
        loras = [(lname, None, float(strength)) for lname, strength in loras_raw]

        seed = meta.get("seed")

        sample = images[0]
        h = int(sample.shape[-3]) if hasattr(sample, "shape") else 0
        w = int(sample.shape[-2]) if hasattr(sample, "shape") else 0

        params = build_a1111_parameters(
            positive=positive_text or meta.get("positive", ""),
            negative=negative_text or meta.get("negative", ""),
            width=w, height=h,
            steps=meta.get("steps"),
            sampler_name=meta.get("sampler_name"),
            scheduler=meta.get("scheduler"),
            cfg=meta.get("cfg"),
            seed=seed,
            model_name=model_name,
            model_sha256=None,
            loras=loras,
        )

        full_prefix, filename, counter, subfolder, custom = _resolve_output_dir(
            filename_prefix, output_path, images
        )

        results = _save_frames(
            images, params, full_prefix, filename, counter, subfolder,
            custom, image_format, show_preview, prompt, extra_pnginfo
        )

        # DEBUG — remove this block when done
        debug_lines = [
            "node=RibbitySaveA1111",
            "model=" + str(model_name),
            "seed=" + str(seed),
            "steps=" + str(meta.get("steps")),
            "cfg=" + str(meta.get("cfg")),
            "sampler=" + str(meta.get("sampler_name")),
            "scheduler=" + str(meta.get("scheduler")),
            "loras=" + str([(n, s) for n, _, s in loras]),
            "format=" + image_format,
        ]
        debug = "\n".join(debug_lines)
        # END DEBUG

        return {"ui": {"images": results}, "result": (int(seed) if seed is not None else 0, debug)}


# ---------------------------------------------------------------------------
# Node 2 — 🐸 Save: Hash Embed
# Same as A1111 but computes SHA256 for model + auto-detected LoRAs.
# ---------------------------------------------------------------------------

class RibbitySaveHashEmbed:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images":          ("IMAGE",),
                "filename_prefix": ("STRING", {
                    "default": "RibbityPack",
                    "tooltip": "Prefix for saved files. Supports %date:yyyy-MM-dd% tokens.",
                }),
                "image_format": (["PNG", "JPG", "WEBP"], {"default": "PNG"}),
            },
            "optional": {
                "output_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Leave blank for ComfyUI/output",
                }),
                "show_preview":    ("BOOLEAN", {"default": True}),
                "append_counter":  ("BOOLEAN", {"default": True,
                    "tooltip": "Append a zero-padded counter to the filename. "
                               "Disable to overwrite the same file each run."}),
                "positive_text":   ("STRING", {"forceInput": True}),
                "negative_text":   ("STRING", {"forceInput": True}),
            },
            "hidden": {
                "prompt":        "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES  = ("INT", "STRING")
    RETURN_NAMES  = ("seed", "debug")
    OUTPUT_NODE   = True
    FUNCTION      = "save"
    CATEGORY      = "🐸 Node Pack"

    def save(self, images, filename_prefix, image_format,
             output_path="", show_preview=True, append_counter=True,
             positive_text=None, negative_text=None,
             prompt=None, extra_pnginfo=None):

        filename_prefix = _expand_filename_tokens(filename_prefix or "RibbityPack")
        meta = extract_workflow_metadata(prompt)

        model_label    = meta.get("model_label")
        model_resolved = resolve_model_path(model_label) if model_label else None
        model_name     = model_resolved[0] if model_resolved else None
        model_sha      = (get_cached_sha256(model_label, model_resolved[1])
                          if model_resolved else None)

        loras: list[tuple[str, str | None, float]] = []
        for lname, strength in meta.get("loras", []):
            full = resolve_lora_path(lname)
            # Always include the LoRA — if the file can't be found we still
            # emit the <lora:...> token; we just can't supply a hash.
            sha = get_cached_sha256(lname, full) if full else None
            loras.append((lname, sha, float(strength)))

        seed = meta.get("seed")

        sample = images[0]
        h = int(sample.shape[-3]) if hasattr(sample, "shape") else 0
        w = int(sample.shape[-2]) if hasattr(sample, "shape") else 0

        params = build_a1111_parameters(
            positive=positive_text or meta.get("positive", ""),
            negative=negative_text or meta.get("negative", ""),
            width=w, height=h,
            steps=meta.get("steps"),
            sampler_name=meta.get("sampler_name"),
            scheduler=meta.get("scheduler"),
            cfg=meta.get("cfg"),
            seed=seed,
            model_name=model_name,
            model_sha256=model_sha,
            loras=loras,
        )

        full_prefix, filename, counter, subfolder, custom = _resolve_output_dir(
            filename_prefix, output_path, images
        )

        results = _save_frames(
            images, params, full_prefix, filename, counter, subfolder,
            custom, image_format, show_preview, prompt, extra_pnginfo,
            append_counter=append_counter
        )

        # DEBUG — remove this block when done
        debug_lines = [
            "node=RibbitySaveHashEmbed",
            "model=" + str(model_name),
            "model_sha=" + str(model_sha[:10] if model_sha else None),
            "seed=" + str(seed),
            "steps=" + str(meta.get("steps")),
            "cfg=" + str(meta.get("cfg")),
            "sampler=" + str(meta.get("sampler_name")),
            "scheduler=" + str(meta.get("scheduler")),
            "loras=" + str([(n, s[:10] if s else None, st) for n, s, st in loras]),
            "format=" + image_format,
        ]
        debug = "\n".join(debug_lines)
        # END DEBUG

        return {"ui": {"images": results}, "result": (int(seed) if seed is not None else 0, debug)}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "FrogSaveA1111":     RibbitySaveA1111,
    "FrogSaveHashEmbed": RibbitySaveHashEmbed,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogSaveA1111":     "🐸 Save: A1111",
    "FrogSaveHashEmbed": "🐸 Save: Hash Embed",
}
