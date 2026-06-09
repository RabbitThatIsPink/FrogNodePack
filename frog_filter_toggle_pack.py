"""
🐸-Pack — Filter Toggle Pack

Bundles category-filter switches into a single TAG_FILTER_TOGGLES wire
for use with 🐸 Tag Filter.

character_traits — strip hair colour/style, eye colour, skin tone, body
                   descriptors detected by the tagger.
expressions      — strip facial expression / emotion tags (smile, blush, etc.).
fantasy_traits   — strip fantasy / non-human body features: animal ears,
                   tails, horns, wings, halo, fangs, claws, etc.
clothes          — strip clothing, footwear, legwear, and accessory tags.
furry            — strip anthro / furry-specific tags: body fur, snout,
                   paw pads, species markings, etc.  Disable to keep furry
                   detail tags when generating for that style.
overlay_text     — strip Florence2 descriptions of visible text / signs /
                   writing in the image ("text reading...", "a sign saying...").
                   Disable when Anima generates legible text you want to keep.
"""


class FrogFilterTogglePack:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "character_traits": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Remove character physical descriptors:\n"
                        "hair colour/style, eye colour, skin tone, body type."
                    ),
                }),
                "expressions": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Remove facial expression and emotion tags:\n"
                        "smile, blush, cry, laugh, pout, wink, etc."
                    ),
                }),
                "fantasy_traits": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Remove non-human / fantasy body features:\n"
                        "animal ears, tails, horns, wings, halo, fangs, claws, etc."
                    ),
                }),
                "clothes": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Remove clothing, footwear, legwear, and accessory tags."
                    ),
                }),
                "furry": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Remove anthro / furry-specific tags:\n"
                        "body fur, snout, muzzle, paw pads, species markings,\n"
                        "fur colour/pattern, whiskers, wet fur, etc.\n"
                        "Disable when generating furry-style content that\n"
                        "should retain these descriptors."
                    ),
                }),
                "overlay_text": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Remove Florence2 descriptions of visible text / signs /\n"
                        "writing detected in the image.\n"
                        "e.g. 'text reading OPEN', 'a sign saying Sale 50% off'\n\n"
                        "Disable when Anima generates legible text you want\n"
                        "to preserve in the output prompt."
                    ),
                }),
            }
        }

    RETURN_TYPES  = ("TAG_FILTER_TOGGLES",)
    RETURN_NAMES  = ("toggle_pack",)
    FUNCTION      = "pack"
    CATEGORY      = "🐸 Node Pack/Utility"

    def pack(self, character_traits: bool, expressions: bool,
             fantasy_traits: bool, clothes: bool, furry: bool,
             overlay_text: bool):
        return ({
            "character_traits": character_traits,
            "expressions":      expressions,
            "fantasy_traits":   fantasy_traits,
            "clothes":          clothes,
            "furry":            furry,
            "overlay_text":     overlay_text,
        },)


NODE_CLASS_MAPPINGS        = {"FrogFilterTogglePack": FrogFilterTogglePack}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogFilterTogglePack": "🐸 Frog Exclude Toggle"}
