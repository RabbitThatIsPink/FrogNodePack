"""
FrogNodePack — Pipe In / Pipe Out

Bundles MODEL + CLIP + VAE + positive CONDITIONING + negative CONDITIONING
into a single BASIC_PIPE connection, then unpacks it wherever needed.

Uses the same "BASIC_PIPE" type and (model, clip, vae, positive, negative)
tuple format as Impact Pack's ToBasicPipe / FromBasicPipe — fully cross-
compatible. You can wire Impact Pack's basic_pipe directly into 🐸 Pipe Out
and vice versa.
"""


class FrogPipeIn:
    """Pack five model/conditioning values into one BASIC_PIPE wire."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model":    ("MODEL",),
                "clip":     ("CLIP",),
                "vae":      ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
            }
        }

    RETURN_TYPES    = ("BASIC_PIPE",)
    RETURN_NAMES    = ("basic_pipe",)
    FUNCTION        = "pack"
    CATEGORY        = "🐸 Node Pack"
    OUTPUT_TOOLTIPS = ("Packed pipe — wire to 🐸 Pipe Out or Impact Pack's FromBasicPipe.",)

    def pack(self, model, clip, vae, positive, negative):
        return ((model, clip, vae, positive, negative),)


class FrogPipeOut:
    """Unpack a BASIC_PIPE back into individual model/conditioning outputs."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "basic_pipe": ("BASIC_PIPE", {
                    "tooltip": "Wire from 🐸 Pipe In or Impact Pack's ToBasicPipe.",
                }),
            }
        }

    RETURN_TYPES    = ("BASIC_PIPE", "MODEL", "CLIP", "VAE", "CONDITIONING", "CONDITIONING")
    RETURN_NAMES    = ("basic_pipe", "model", "clip", "vae", "positive", "negative")
    FUNCTION        = "unpack"
    CATEGORY        = "🐸 Node Pack"
    OUTPUT_TOOLTIPS = (
        "Pass-through pipe — wire to the next node that needs the full pipe.",
        "Checkpoint model.",
        "CLIP encoder.",
        "VAE.",
        "Positive conditioning.",
        "Negative conditioning.",
    )

    def unpack(self, basic_pipe):
        model, clip, vae, positive, negative = basic_pipe
        return (basic_pipe, model, clip, vae, positive, negative)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "FrogPipeIn":  FrogPipeIn,
    "FrogPipeOut": FrogPipeOut,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogPipeIn":  "🐸 Pipe In",
    "FrogPipeOut": "🐸 Pipe Out",
}
