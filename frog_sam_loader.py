"""
FrogNodePack — SAM Loader

Loads a SAM 1 or SAM 2 model from ComfyUI/models/sam/ and outputs a
SAM_MODEL that plugs into 🐸 Florence2+SAM Masker (and Impact Pack nodes).

Supported checkpoints
─────────────────────
SAM 1 (segment-anything-hq recommended):
  sam_hq_vit_h.pth   ← recommended  (2.57 GB)
  sam_hq_vit_l.pth
  sam_hq_vit_b.pth
  sam_vit_h_4b8939.pth  (standard SAM, lower boundary quality)

SAM 2 (sam2 package required):
  sam2.1_hiera_large.pt  ← recommended  (898 MB)
  sam2.1_hiera_base+.pt
  sam2.1_hiera_small.pt
  sam2.1_hiera_tiny.pt

Required packages
─────────────────
SAM 1:  pip install segment-anything-hq
        (do NOT also install segment-anything — they conflict)

SAM 2:  git clone https://github.com/facebookresearch/sam2
        cd sam2 && pip install -e .
"""

import os
import importlib

import torch
import folder_paths

# ── Register models/sam/ with ComfyUI ────────────────────────────────────────
_SAM_DIR = os.path.join(folder_paths.models_dir, "sam")
os.makedirs(_SAM_DIR, exist_ok=True)
folder_paths.folder_names_and_paths["sam"] = (
    [_SAM_DIR],
    {".pth", ".pt", ".safetensors"},
)

# ── SAM 2 config name map (Hydra config IDs, no .yaml extension) ─────────────
# Keyed by substrings found in the checkpoint filename.
_SAM2_CONFIGS = {
    # sam2.1 family
    "sam2.1_hiera_large":   "sam2.1/sam2.1_hiera_l",
    "sam2.1_hiera_base+":   "sam2.1/sam2.1_hiera_b+",
    "sam2.1_hiera_base_plus": "sam2.1/sam2.1_hiera_b+",
    "sam2.1_hiera_small":   "sam2.1/sam2.1_hiera_s",
    "sam2.1_hiera_tiny":    "sam2.1/sam2.1_hiera_t",
    # original sam2 family
    "sam2_hiera_large":     "sam2/sam2_hiera_l",
    "sam2_hiera_base+":     "sam2/sam2_hiera_b+",
    "sam2_hiera_base_plus": "sam2/sam2_hiera_b+",
    "sam2_hiera_small":     "sam2/sam2_hiera_s",
    "sam2_hiera_tiny":      "sam2/sam2_hiera_t",
}


# ─────────────────────────────────────────────────────────────────────────────
# Filename helpers
# ─────────────────────────────────────────────────────────────────────────────

def _detect_version(filename: str) -> str:
    """'sam1' or 'sam2' based on filename."""
    f = filename.lower()
    if "sam2" in f or "sam_2" in f:
        return "sam2"
    return "sam1"


def _detect_sam1_arch(filename: str):
    """Return 'vit_h', 'vit_l', 'vit_b', or None if unknown."""
    f = filename.lower()
    for arch in ("vit_h", "vit_l", "vit_b"):
        if arch in f or arch.replace("_", "-") in f:
            return arch
    return None


def _detect_sam2_config(filename: str) -> str:
    """Return the Hydra config ID for this SAM2 checkpoint filename."""
    f = filename.lower().replace(".pt", "")
    for key, cfg in _SAM2_CONFIGS.items():
        if key.lower() in f:
            return cfg
    # Default: large
    return "sam2.1/sam2.1_hiera_l"


# ─────────────────────────────────────────────────────────────────────────────
# Node
# ─────────────────────────────────────────────────────────────────────────────

class FrogSAMLoader:
    """
    Loads SAM 1 (HQ or standard) and SAM 2 checkpoints from models/sam/.

    Version and architecture are auto-detected from the filename.
    Use the override dropdowns only if auto-detection fails.

    Output: SAM_MODEL — wire into 🐸 Florence2+SAM Masker.
    """

    @classmethod
    def INPUT_TYPES(cls):
        model_list = folder_paths.get_filename_list("sam") or ["none"]
        return {
            "required": {
                "model": (model_list, {
                    "tooltip": "Checkpoint file from ComfyUI/models/sam/",
                }),
                "version": (["auto-detect", "SAM 1", "SAM 2"], {
                    "default": "auto-detect",
                    "tooltip":
                        "auto-detect reads the filename.\n"
                        "Override only if the filename doesn't follow the standard naming.",
                }),
                "sam1_arch": (["auto-detect", "vit_h", "vit_l", "vit_b"], {
                    "default": "auto-detect",
                    "tooltip": "SAM 1 only. Ignored for SAM 2.",
                }),
                "device": (["auto", "cuda", "cpu"], {
                    "default": "auto",
                    "tooltip":
                        "auto → CUDA if available, else CPU.\n"
                        "SAM models are large; CPU inference is very slow.",
                }),
            },
        }

    RETURN_TYPES  = ("SAM_MODEL",)
    RETURN_NAMES  = ("sam_model",)
    FUNCTION      = "load"
    CATEGORY      = "🐸 Node Pack"

    @classmethod
    def IS_CHANGED(cls, model, **kwargs):
        """Re-load if the selected checkpoint file changes."""
        path = folder_paths.get_full_path("sam", model)
        if path and os.path.exists(path):
            return os.path.getmtime(path)
        return float("nan")

    # ─────────────────────────────────────────────────────────────────────────

    def load(self, model, version, sam1_arch, device):
        path = folder_paths.get_full_path("sam", model)
        if path is None or not os.path.exists(path):
            raise FileNotFoundError(
                f"[🐸 SAM Loader] '{model}' not found in {_SAM_DIR}"
            )

        # Resolve device
        if device == "auto":
            dev = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            dev = device

        # Resolve version
        ver = _detect_version(model) if version == "auto-detect" else (
            "sam1" if version == "SAM 1" else "sam2"
        )

        if ver == "sam1":
            loaded = _load_sam1(path, model, sam1_arch, dev)
        else:
            loaded = _load_sam2(path, model, dev)

        # Return as (model_object, version_hint) tuple.
        # The version_hint lets 🐸 Florence2+SAM Masker skip the wrapper guessing.
        # The SAM_MODEL type string keeps us compatible with Impact Pack nodes.
        return ((loaded, ver),)


# ─────────────────────────────────────────────────────────────────────────────
# SAM 1 loader
# ─────────────────────────────────────────────────────────────────────────────

def _load_sam1(path: str, filename: str, arch_override: str, device: str):
    try:
        from segment_anything_hq import sam_model_registry
    except ImportError as e:
        raise ImportError(
            f"[🐸 SAM Loader] Failed to import segment_anything_hq: {e}\n"
            "Install: pip install segment-anything-hq"
        ) from e

    # Resolve architecture
    if arch_override != "auto-detect":
        arch = arch_override
    else:
        arch = _detect_sam1_arch(filename)
        if arch is None:
            raise ValueError(
                f"[🐸 SAM Loader] Could not auto-detect SAM 1 arch from '{filename}'.\n"
                "Set sam1_arch manually (vit_h / vit_l / vit_b)."
            )

    if arch not in sam_model_registry:
        raise KeyError(
            f"[🐸 SAM Loader] Architecture '{arch}' not in registry.\n"
            f"Available: {list(sam_model_registry.keys())}"
        )

    print(f"[🐸 SAM Loader] Loading SAM 1 {arch} from {os.path.basename(path)} → {device}")
    model = sam_model_registry[arch](checkpoint=path)
    model.eval()
    model.to(device)
    return model


# ─────────────────────────────────────────────────────────────────────────────
# SAM 2 loader
# ─────────────────────────────────────────────────────────────────────────────

def _load_sam2(path: str, filename: str, device: str):
    try:
        from sam2.build_sam import build_sam2
    except ImportError:
        raise ImportError(
            "[🐸 SAM Loader] SAM 2 requires the sam2 package.\n"
            "Install:\n"
            "  git clone https://github.com/facebookresearch/sam2\n"
            "  cd sam2 && pip install -e ."
        )

    config_name = _detect_sam2_config(filename)
    print(
        f"[🐸 SAM Loader] Loading SAM 2  config={config_name}  "
        f"file={os.path.basename(path)}  device={device}"
    )

    try:
        model = build_sam2(config_name, path, device=device)
    except Exception as e:
        # Hydra config resolution can fail if sam2 wasn't installed with -e .
        # Try to give a helpful message.
        if "config" in str(e).lower() or "hydra" in str(e).lower():
            raise RuntimeError(
                f"[🐸 SAM Loader] SAM 2 config resolution failed: {e}\n\n"
                "This usually means sam2 was not installed with 'pip install -e .'.\n"
                "Fix:\n"
                "  cd <sam2-repo> && pip install -e ."
            ) from e
        raise

    model.eval()
    return model


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────

NODE_CLASS_MAPPINGS        = {"FrogSAMLoader": FrogSAMLoader}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogSAMLoader": "🐸 SAM Loader"}
