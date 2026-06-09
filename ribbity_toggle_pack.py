"""
🐸-Pack — Ribbity Toggle Pack
Bundles merge-source toggles into a single ANIMA_TOGGLES wire.
The companion JS (ribbity_toggle_pack.js) handles group bypass in the canvas.
"""


class RibbityTogglePack:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "tagger":    ("BOOLEAN", {"default": False}),
                "raffle":  ("BOOLEAN", {"default": False}),
                "florence2": ("BOOLEAN", {"default": False}),
                "scene":     ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES  = ("ANIMA_TOGGLES",)
    RETURN_NAMES  = ("toggle_pack",)
    FUNCTION      = "pack"
    CATEGORY      = "🐸 Node Pack/Utility"

    def pack(self, tagger, raffle, florence2, scene):
        return ({
            "tagger":    tagger,
            "raffle":  raffle,
            "florence2": florence2,
            "scene":     scene,
        },)


NODE_CLASS_MAPPINGS        = {"FrogTogglePack": RibbityTogglePack}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogTogglePack": "🐸 Toggle Pack"}
