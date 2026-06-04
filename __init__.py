from .ribbity_loader import (
    NODE_CLASS_MAPPINGS        as _loader_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _loader_names,
)
from .ribbity_ksampler import (
    NODE_CLASS_MAPPINGS        as _ksampler_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _ksampler_names,
)
from .ribbity_clip_text_encode import (
    NODE_CLASS_MAPPINGS        as _clip_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _clip_names,
)
from .ribbity_empty_latent import (
    NODE_CLASS_MAPPINGS        as _latent_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _latent_names,
)
from .ribbity_save import (
    NODE_CLASS_MAPPINGS        as _save_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _save_names,
)
from .ribbity_log_reader import (
    NODE_CLASS_MAPPINGS        as _log_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _log_names,
)
from .ribbity_sorter import (
    NODE_CLASS_MAPPINGS        as _sorter_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _sorter_names,
)
from .ribbity_toggle_pack import (
    NODE_CLASS_MAPPINGS        as _toggle_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _toggle_names,
)
from .ribbity_prompt_merge import (
    NODE_CLASS_MAPPINGS        as _merge_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _merge_names,
)
from .ribbity_library import (
    NODE_CLASS_MAPPINGS        as _library_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _library_names,
)
from .ribbity_wildcards import (
    NODE_CLASS_MAPPINGS        as _wc_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _wc_names,
)
from .ribbity_merge import (
    NODE_CLASS_MAPPINGS        as _merge2_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _merge2_names,
)
from .ribbity_dedupe import (
    NODE_CLASS_MAPPINGS        as _dedupe_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _dedupe_names,
)
from .ribbity_save_thumbnail import (
    NODE_CLASS_MAPPINGS        as _savethumb_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _savethumb_names,
)
from .ribbity_image_picker import (
    NODE_CLASS_MAPPINGS        as _picker_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _picker_names,
)

NODE_CLASS_MAPPINGS = {
    **_loader_classes,
    **_ksampler_classes,
    **_clip_classes,
    **_latent_classes,
    **_save_classes,
    **_log_classes,
    **_sorter_classes,
    **_library_classes,
    **_wc_classes,
    **_toggle_classes,
    **_merge_classes,
    **_merge2_classes,
    **_dedupe_classes,
    **_savethumb_classes,
    **_picker_classes,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **_loader_names,
    **_ksampler_names,
    **_clip_names,
    **_latent_names,
    **_save_names,
    **_log_names,
    **_sorter_names,
    **_library_names,
    **_wc_names,
    **_toggle_names,
    **_merge_names,
    **_merge2_names,
    **_dedupe_names,
    **_savethumb_names,
    **_picker_names,
}

# Serve frontend JS ONLY from ./web. Without this, ComfyUI auto-discovers and
# globs .js files across the whole pack — which would double-load any stray
# copy in Backup/ and collide extension registrations (comfy.FrogLibrary).
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]