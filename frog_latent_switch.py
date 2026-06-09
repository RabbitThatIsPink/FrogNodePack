"""
FrogNodePack — Smart Latent Switch

Two LATENT inputs: a required primary and an optional override.
If the override is connected, it wins. Otherwise the primary is used.

Use case: wire your 🐸 LLM Latent Selector into the override slot.
When it's disconnected, the node falls back to your manual Empty Latent.
No selector widget needed — the wiring IS the switch.
"""


class FrogLatentSwitch:
    """
    Passes latent_override through if connected; otherwise passes latent_primary.
    Connecting / disconnecting the override slot is all that's needed to switch.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent_primary": ("LATENT", {
                    "tooltip": "Default latent — used when no override is connected.",
                }),
            },
            "optional": {
                "latent_override": ("LATENT", {
                    "tooltip": "When connected, this latent is used instead of the primary. "
                               "Wire your LLM Latent Selector here.",
                }),
            },
        }

    RETURN_TYPES    = ("LATENT",)
    RETURN_NAMES    = ("latent",)
    FUNCTION        = "switch"
    CATEGORY        = "🐸 Node Pack"
    OUTPUT_TOOLTIPS = ("The active latent — override if connected, primary otherwise.",)

    def switch(self, latent_primary, latent_override=None):
        if latent_override is not None:
            return (latent_override,)
        return (latent_primary,)


# ─────────────────────────────────────────────
#  REGISTRATION
# ─────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "FrogLatentSwitch": FrogLatentSwitch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogLatentSwitch": "🐸 Smart Latent Switch",
}
