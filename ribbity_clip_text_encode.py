import comfy.sd

# ---------------------------------------------------------------------------
# 🐸-Pack — Ribbity CLIP Text Encode
# One CLIP input, two text inputs, two conditioning outputs.
# Also passes positive and negative text through as strings so the
# save node can read exactly what was encoded — no graph tracing needed.
# ---------------------------------------------------------------------------

class RibbityCLIPTextEncode:
    # Last encoded strings — read by save node at save time
    _last_positive = ""
    _last_negative = ""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip":     ("CLIP",),
                "positive": ("STRING", {
                    "multiline": True,
                    "placeholder": "Positive prompt…",
                    "default": "",
                }),
                "negative": ("STRING", {
                    "multiline": True,
                    "placeholder": "Negative prompt…",
                    "default": "",
                }),
            }
        }

    RETURN_TYPES  = ("CONDITIONING", "CONDITIONING", "STRING", "STRING")
    RETURN_NAMES  = ("Positive", "Negative", "positive_text", "negative_text")
    FUNCTION      = "encode"
    CATEGORY      = "🐸 Node Pack"

    def encode(self, clip, positive, negative):
        pos_tokens = clip.tokenize(positive)
        pos_cond   = clip.encode_from_tokens_scheduled(pos_tokens)

        neg_tokens = clip.tokenize(negative)
        neg_cond   = clip.encode_from_tokens_scheduled(neg_tokens)

        RibbityCLIPTextEncode._last_positive = positive
        RibbityCLIPTextEncode._last_negative = negative
        return (pos_cond, neg_cond, positive, negative)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "FrogCLIPTextEncode": RibbityCLIPTextEncode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogCLIPTextEncode": "🐸 CLIP Text Encode",
}
