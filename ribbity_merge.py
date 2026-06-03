"""
🐸-Pack — Ribbity Merge
Joins up to 10 string inputs with a configurable separator (default ", ").
Inputs grow dynamically — connect Input_1 and Input_2 appears, and so on.
Empty / disconnected inputs are silently skipped.
Dynamic input visibility is driven by web/frog_merge.js.
"""


class RibbityMerge:

    MAX_INPUTS = 10

    @classmethod
    def INPUT_TYPES(cls):
        optional = {}
        for i in range(1, cls.MAX_INPUTS + 1):
            optional[f"input_{i}"] = ("STRING", {
                "forceInput": True,
                "tooltip": f"String input {i}.",
            })
        return {
            "required": {
                "separator": ("STRING", {
                    "default": ", ",
                    "multiline": False,
                    "tooltip": "String placed between each joined input.",
                }),
            },
            "optional": optional,
        }

    RETURN_TYPES  = ("STRING",)
    RETURN_NAMES  = ("merged",)
    FUNCTION      = "merge"
    CATEGORY      = "🐸 Node Pack"

    def merge(self, separator=", ", **kwargs):
        parts = []
        for i in range(1, self.MAX_INPUTS + 1):
            val = kwargs.get(f"input_{i}")
            if val and isinstance(val, str) and val.strip():
                parts.append(val.strip().rstrip(separator.strip()).strip())
        merged = separator.join(parts)
        return (merged,)


NODE_CLASS_MAPPINGS        = {"FrogMerge": RibbityMerge}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogMerge": "🐸 Merge"}
