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
from .frog_tag_filter import (
    NODE_CLASS_MAPPINGS        as _tagfilter_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _tagfilter_names,
)
from .frog_filter_toggle_pack import (
    NODE_CLASS_MAPPINGS        as _filtertoggle_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _filtertoggle_names,
)
from .frog_tag_to_description import (
    NODE_CLASS_MAPPINGS        as _t2d_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _t2d_names,
)
from .frog_duo_dupe_check import (
    NODE_CLASS_MAPPINGS        as _dupecheck_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _dupecheck_names,
)
from .frog_llm_prompt_refiner import (
    NODE_CLASS_MAPPINGS        as _refiner_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _refiner_names,
)
from .frog_pixel_upscaler import (
    NODE_CLASS_MAPPINGS        as _upscaler_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _upscaler_names,
)
from .frog_latent_switch import (
    NODE_CLASS_MAPPINGS        as _latentswitch_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _latentswitch_names,
)
from .frog_llm_latent_selector import (
    NODE_CLASS_MAPPINGS        as _llmlatent_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _llmlatent_names,
)
from .frog_detailer import (
    NODE_CLASS_MAPPINGS        as _detailer_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _detailer_names,
)
from .frog_detailer_pro import (
    NODE_CLASS_MAPPINGS        as _detailerpro_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _detailerpro_names,
)
from .frog_flosam_masker import (
    NODE_CLASS_MAPPINGS        as _flosam_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _flosam_names,
)
from .frog_sam_loader import (
    NODE_CLASS_MAPPINGS        as _samloader_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _samloader_names,
)
from .frog_pipe import (
    NODE_CLASS_MAPPINGS        as _pipe_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _pipe_names,
)
from .frog_mask_batch_split import (
    NODE_CLASS_MAPPINGS        as _maskbatch_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _maskbatch_names,
)
from .frog_prompt_processor import (
    NODE_CLASS_MAPPINGS        as _promptprocessor_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _promptprocessor_names,
)
from .frog_checkpoint_library_selector import (
    NODE_CLASS_MAPPINGS        as _ckptlibsel_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _ckptlibsel_names,
)
from .frog_loader_with_library import (
    NODE_CLASS_MAPPINGS        as _loaderwithlib_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _loaderwithlib_names,
)
from .frog_library_by_name import (
    NODE_CLASS_MAPPINGS        as _libbyname_classes,
    NODE_DISPLAY_NAME_MAPPINGS as _libbyname_names,
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
    **_tagfilter_classes,
    **_filtertoggle_classes,
    **_t2d_classes,
    **_dupecheck_classes,
    **_refiner_classes,
    **_upscaler_classes,
    **_latentswitch_classes,
    **_llmlatent_classes,
    **_detailer_classes,
    **_detailerpro_classes,
    **_flosam_classes,
    **_samloader_classes,
    **_pipe_classes,
    **_maskbatch_classes,
    **_promptprocessor_classes,
    **_ckptlibsel_classes,
    **_loaderwithlib_classes,
    **_libbyname_classes,
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
    **_tagfilter_names,
    **_filtertoggle_names,
    **_t2d_names,
    **_dupecheck_names,
    **_refiner_names,
    **_upscaler_names,
    **_latentswitch_names,
    **_llmlatent_names,
    **_detailer_names,
    **_detailerpro_names,
    **_flosam_names,
    **_samloader_names,
    **_pipe_names,
    **_maskbatch_names,
    **_promptprocessor_names,
    **_ckptlibsel_names,
    **_loaderwithlib_names,
    **_libbyname_names,
}

# Serve frontend JS ONLY from ./web. Without this, ComfyUI auto-discovers and
# globs .js files across the whole pack — which would double-load any stray
# copy in Backup/ and collide extension registrations (comfy.FrogLibrary).
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]