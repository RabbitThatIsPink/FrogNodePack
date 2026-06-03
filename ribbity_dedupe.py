"""
🐸-Pack — Ribbity Dedupe
Single input, single output.
Removes duplicate tags from a comma-separated prompt string.
Comparison is case-insensitive and underscore-normalised ("Blue_Eyes" == "blue eyes").
First occurrence wins; order is preserved.
"""

import re


def _normalise(tag: str) -> str:
    return tag.lower().strip().replace("_", " ")


def _split_tags(text: str) -> list[str]:
    """Split on commas, respecting parenthesis depth."""
    if not text or not text.strip():
        return []
    tags: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            token = "".join(current).strip()
            if token:
                tags.append(token)
            current = []
        else:
            current.append(ch)
    token = "".join(current).strip()
    if token:
        tags.append(token)
    return tags


class RibbityDedupe:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Comma-separated tags to deduplicate.",
                }),
            }
        }

    RETURN_TYPES  = ("STRING",)
    RETURN_NAMES  = ("deduped",)
    FUNCTION      = "dedupe"
    CATEGORY      = "🐸 Node Pack"

    def dedupe(self, text: str):
        tags = _split_tags(text or "")
        seen: set[str] = set()
        result: list[str] = []
        for tag in tags:
            key = _normalise(tag)
            if key not in seen:
                seen.add(key)
                result.append(tag)
        return (", ".join(result),)


NODE_CLASS_MAPPINGS        = {"FrogDedupe": RibbityDedupe}
NODE_DISPLAY_NAME_MAPPINGS = {"FrogDedupe": "🐸 Dedupe"}
