"""
🐸-Pack — Tag Filter

Combines a Florence2 natural-language caption and a WD14 gelbooru tag
string, then strips unwanted content before the result reaches the text encoder.

Output order:  Florence2 caption first, WD14 tags second.

Both tagger inputs are optional — wire whichever taggers you use.

Filtering sources
─────────────────
1. Exclude list   — manual patterns typed in the node widget.
2. Filter Toggle Pack (optional wire) — category switches:
     • character_traits  strips hair, eye, skin, body descriptors.
                         Works on both WD14 tags AND Florence2 natural language.
     • expressions       strips facial expression / emotion descriptors.
     • clothes           strips clothing, footwear, legwear, accessory tags.
                         Works on both WD14 tags AND Florence2 natural language.
     • fantasy_traits    strips non-human / fantasy body features and
                         creature race classifications.

NL stripping (Florence2)
────────────────────────
Florence2 outputs full sentences.  The filter detects and removes
character-describing phrases from within those sentences, leaving
only scene / environment content.

  "a woman with long, flowing orange hair and blue eyes wearing a red dress
   standing on a rooftop overlooking a city at night"
  →
  "a woman standing on a rooftop overlooking a city at night"

Exclude list rules (WD14 / tag-style)
──────────────────────────────────────
• One entry per line  OR  comma-separated — both work.
• Case-insensitive; underscores == spaces.
• * wildcard:  rating:* · *background* · nude
"""

from __future__ import annotations

import fnmatch
import json
import os
import re

# ---------------------------------------------------------------------------
# User-defined vocabulary extensions
# Loaded from data/vocab_extensions.json at import time and updated live
# when the FrogVocabExtender node executes.
# ---------------------------------------------------------------------------

_USER_ALWAYS_WORDS:   set[str] = set()   # no toggle — always filtered
_USER_FANTASY_WORDS:  set[str] = set()   # fantasy_traits toggle
_USER_CHAR_WORDS:     set[str] = set()   # character_traits toggle
_USER_OVERLAY_WORDS:  set[str] = set()   # overlay_text toggle


def _vocab_path() -> str:
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "vocab_extensions.json")


def _parse_vocab_text(text: str) -> list[str]:
    """Split a multi-line / comma-separated widget string into normalised words."""
    out: list[str] = []
    for line in (text or "").splitlines():
        for part in line.split(","):
            w = part.strip().lower().replace("_", " ")
            if w:
                out.append(w)
    return out


def _load_user_vocab() -> None:
    path = _vocab_path()
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        _USER_ALWAYS_WORDS.clear()
        _USER_ALWAYS_WORDS.update(data.get("always", []))
        _USER_FANTASY_WORDS.clear()
        _USER_FANTASY_WORDS.update(data.get("fantasy", []))
        _USER_CHAR_WORDS.clear()
        _USER_CHAR_WORDS.update(data.get("character_traits", []))
        _USER_OVERLAY_WORDS.clear()
        _USER_OVERLAY_WORDS.update(data.get("overlay_text", []))
    except Exception as exc:
        print(f"[🐸 Vocab Extender] failed to load vocab_extensions.json: {exc}")


def _save_user_vocab(always: list[str], fantasy: list[str],
                     character_traits: list[str], overlay_text: list[str]) -> None:
    path = _vocab_path()
    data = {
        "always":           always,
        "fantasy":          fantasy,
        "character_traits": character_traits,
        "overlay_text":     overlay_text,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    # Reload in-memory sets immediately
    _load_user_vocab()


_load_user_vocab()   # populate sets on module import


# Import the Sorter's tag sets so both nodes stay in sync.
try:
    from .ribbity_sorter import _CHARACTER_TAGS  as _SORTER_CHARACTER_TAGS
    from .ribbity_sorter import _EXPRESSION_TAGS as _SORTER_EXPRESSION_TAGS
except Exception:
    _SORTER_CHARACTER_TAGS  = set()
    _SORTER_EXPRESSION_TAGS = set()


# ---------------------------------------------------------------------------
# Fantasy / non-human body features  (fantasy_traits toggle)
# ---------------------------------------------------------------------------

_FANTASY_TAGS = {
    # Ears
    "animal ears", "cat ears", "dog ears", "wolf ears", "fox ears",
    "bunny ears", "rabbit ears", "bear ears", "deer ears", "mouse ears",
    "elf ears", "pointy ears", "long ears", "floppy ears",
    "dragon ears", "demon ears", "oni ears",
    # Tails
    "tail", "cat tail", "dog tail", "wolf tail", "fox tail", "bunny tail",
    "rabbit tail", "deer tail", "lion tail", "tiger tail", "bear tail",
    "dragon tail", "demon tail", "devil tail", "scorpion tail",
    "fluffy tail", "long tail", "short tail", "multiple tails",
    "red tail", "blue tail", "black tail", "white tail", "brown tail",
    "multiple fox tails",
    # Horns
    "horns", "horn", "demon horns", "devil horns", "oni horns",
    "dragon horns", "ram horns", "bull horns", "goat horns",
    "antlers", "single horn", "unicorn horn",
    "skin-covered horns", "bone horns", "curved horns", "spiral horns",
    # Wings
    "wings", "wing", "angel wings", "demon wings", "devil wings",
    "dragon wings", "bat wings", "bird wings", "feathered wings",
    "mechanical wings", "insect wings", "fairy wings",
    # Halo / divine
    "halo", "holy halo", "broken halo", "angel halo",
    # Fangs / claws / scales
    "fangs", "fang", "sharp teeth", "vampire fangs",
    "claws", "claw", "sharp claws", "dragon claws",
    "scales", "dragon scales", "fish scales",
    "fur", "feathers",
    # Fantasy creature races / classifications
    # (WD14 often applies these as direct character-type tags)
    "oni", "red oni", "blue oni", "green oni", "oni girl", "oni boy",
    "demon", "demon girl", "demon boy", "half demon",
    "devil", "devil girl", "devil boy", "half devil",
    "succubus", "incubus",
    "vampire", "vampiress", "half vampire", "dhampir",
    "undead", "zombie", "skeleton", "lich",
    "orc", "goblin", "troll", "ogre", "gnome",
    "elf", "dark elf", "high elf", "wood elf", "half elf",
    "angel", "fallen angel", "half angel",
    "fairy", "faerie", "pixie", "sprite",
    "dragon girl", "dragon boy", "dragonkin", "half dragon",
    "naga", "lamia", "gorgon", "medusa",
    "centaur", "minotaur", "satyr", "faun",
    "kitsune", "tanuki", "tengu", "yokai",
    "harpy", "siren", "mermaid", "merman", "merfolk",
    "slime girl", "slime boy",
    "ghost", "spirit", "wraith",
    "beastman", "beast ears", "beast tail",
    # Other fantasy appendages
    "tentacles", "tentacle",
    "slime", "slime body",
    "multiple arms", "extra arms", "multiple eyes", "extra eyes",
    "third eye", "cyclops",
}

# Single-word fantasy terms for word-level compound-tag matching.
# Catches "skin-covered_horns" (→ "horns"), "red_tail" (→ "tail"),
# "demon_girl" (→ "demon"), "red_oni" (→ "oni"), etc.
_FANTASY_WORDS = frozenset({
    "horns", "horn", "tail", "tails", "ears", "ear",
    "wings", "wing", "fang", "fangs",
    # NOTE: "claw" (singular) omitted — catches "claw_foot_bathtub" as a
    # false positive.  "claws" (plural) is kept; compound tags like
    # "dragon_claw" are still caught via "dragon" in this set.
    "claws",
    "halo", "tentacle", "tentacles", "scale", "scales",
    # Creature types — singular and plural both present so that compound tags
    # like "dark_elves", "forest_demons", "shadow_dragons" are all caught.
    "oni", "onis",
    "demon", "demons", "devil", "devils",
    "vampire", "vampires", "undead",
    "zombie", "zombies", "skeleton", "skeletons",
    "kitsune", "kitsunes", "yokai", "yokais",
    "lich", "liches",
    "succubus", "succubi", "incubus", "incubi",
    "naga", "nagas", "lamia", "lamias",
    "elf", "elves",
    "angel", "angels", "fairy", "fairies", "faerie", "faeries",
    "orc", "orcs", "goblin", "goblins",
    "dragon", "dragons",
    "witch", "witches",
    "werewolf", "werewolves",
})


# ---------------------------------------------------------------------------
# Furry / anthro tag set  (furry toggle)
# ---------------------------------------------------------------------------
# Distinct from fantasy_traits — covers anthropomorphic animal content.
# Disable this toggle when generating furry-style art that needs these tags.

_FURRY_TAGS = {
    # Species / race classifications
    "furry", "furry female", "furry male", "furry other",
    "anthro", "anthro female", "anthro male",
    "wolf girl", "wolf boy",
    "cat girl", "cat boy", "neko", "neko girl", "neko boy",
    "fox girl", "fox boy",
    "dog girl", "dog boy",
    "rabbit girl", "rabbit boy",
    "bear girl", "bear boy",
    "deer girl", "deer boy",
    "mouse girl", "mouse boy",
    "horse girl", "horse boy",
    "raccoon girl", "raccoon boy",
    "tiger girl", "tiger boy",
    "lion girl", "lion boy",
    "squirrel girl", "squirrel boy",
    # Fur — body covering & colour/pattern
    "body fur",
    "white fur", "grey fur", "gray fur", "brown fur", "black fur",
    "orange fur", "red fur", "tan fur", "cream fur", "golden fur",
    "blue fur", "purple fur", "green fur", "pink fur",
    "spotted fur", "striped fur", "tabby", "calico",
    "two-tone fur", "multicolored fur",
    "fluffy fur", "short fur", "long fur", "thick fur", "soft fur",
    "wet fur", "dripping fur",
    "fur pattern", "fur markings",
    # Distinctly furry anatomy
    "snout", "muzzle",
    "animal nose", "wet nose",
    "paws", "paw", "paw pads",
    "animal feet", "animal foot", "animal hands", "animal hand",
    "clawed hands", "clawed feet",
    "whiskers",
    # Ear details common to furry art
    "animal ear fluff", "ear fluff", "inner ear fluff",
    "notched ear", "notched ears", "torn ear", "folded ear",
    # Body markings
    "facial markings", "body markings", "muzzle markings",
    # Meta / genre tags
    "furry art", "anthro art",
}

# Single-word furry terms for word-level compound-tag matching.
# Catches "body_fur", "white_fur", "two-tone_fur", "grey_fur", etc.
_FURRY_WORDS = frozenset({
    "fur", "furry", "anthro",
    "snout", "muzzle", "whiskers",
    "paw", "paws", "fluff",
})


# ---------------------------------------------------------------------------
# Explicit content  (filtered under character_traits toggle)
# ---------------------------------------------------------------------------
# These describe character-specific anatomy and acts rather than
# scene / environment / lighting content.

_EXPLICIT_TAGS = {
    # Male anatomy
    "penis", "cock", "erection", "erect penis", "flaccid penis",
    "large penis", "huge penis", "small penis", "veiny penis",
    "testicles", "balls", "scrotum", "foreskin",
    # Female anatomy
    "vagina", "vulva", "clitoris", "labia", "pussy",
    # Non-gendered explicit anatomy
    "areola", "areolae",
    # Female explicit anatomy (additional)
    "cleft of venus", "camel toe", "cameltoe",
    # Explicit fluids / states
    "cum", "semen", "sperm",
    "cum on body", "cum on face", "cum on breasts", "cum on hair",
    "cum on stomach", "cum on tongue", "cum on clothes",
    "cum in mouth", "cum inside", "cumshot",
    "creampie", "squirting", "ahegao",
    # Explicit acts
    "sex", "intercourse", "coitus", "copulation",
    "ejaculation", "ejaculating", "orgasm",
    "handjob", "blowjob", "fellatio", "cunnilingus", "analingus",
    "masturbation", "fingering", "penetration",
    "double penetration", "triple penetration",
    "gangbang", "gang bang", "bukakke", "bukkake", "facial",
    "double handjob", "footjob", "paizuri",
    "group sex", "threesome", "foursome", "orgy",
    # Sexual context tags
    "hetero", "yuri", "yaoi",
    "interspecies",
    "solo focus",
}

# Single explicit words for word-level compound-tag matching.
# Catches "veiny_penis", "cum_on_breasts", "double_handjob", etc.
_EXPLICIT_WORDS = frozenset({
    "penis", "cock", "vagina", "vulva", "pussy", "clitoris",
    "cum", "semen", "ejaculation", "orgasm",
    "handjob", "blowjob", "fellatio", "gangbang", "bukkake",
    "penetration", "paizuri", "footjob",
})


# ---------------------------------------------------------------------------
# Local character supplement
# ---------------------------------------------------------------------------
# Body tags not in the sorter's sets, plus WD14 body-position / framing tags
# that describe the character rather than the scene.

_LOCAL_CHAR_TAGS = {
    # Body features
    "breasts", "breast", "nipples", "nipple",
    "dark nipples", "pink nipples", "large nipples", "small nipples",
    "erect nipples", "pointy nipples", "perky nipples",
    "areola", "areolae",
    "lips", "lip", "tongue", "teeth", "upper teeth", "lower teeth",
    "navel", "belly button", "belly",
    "collarbone", "collar bone", "clavicle",
    "cleavage", "sideboob", "underboob",
    # Skin tone compound tags (WD14 uses these as direct character descriptors)
    "dark skin", "dark skinned", "dark-skinned", "dark skin tone",
    "light skin", "light skinned", "light-skinned", "light skin tone",
    "fair skin", "fair skinned", "fair-skinned",
    "pale skin", "pale skinned", "pale-skinned",
    "tan skin", "tanned skin", "bronze skin", "bronzed skin",
    "brown skin", "warm skin", "olive skin",
    "ebony skin",
    # Skin marks / texture
    "freckles", "freckle", "body freckles", "face freckles",
    "mole", "moles", "mole under eye", "mole on cheek", "mole on breast",
    "mole on neck", "mole on body", "mole on stomach", "multiple moles",
    "beauty mark", "birthmark", "scar", "scars",
    "tattoo", "tattoos", "tribal tattoo", "sleeve tattoo", "back tattoo",
    "chest tattoo", "arm tattoo", "shoulder tattoo", "neck tattoo",
    "shiny skin", "oily skin", "wet skin", "glistening skin",
    "tan", "tan line", "tan lines",
    # Body / trunk
    "stomach", "abdomen", "torso", "midriff",
    "thigh", "thighs", "inner thigh",
    "legs", "leg", "calf", "calves", "shin", "ankle",
    "feet", "foot", "toes", "toe",
    # Body state
    "sweat", "sweaty", "sweat drop", "sweat drops", "sweating",
    "dripping sweat", "wet", "dripping wet",
    "veins", "vein", "veiny", "bulging veins",
    "nude", "naked", "completely nude", "fully nude", "fully naked",
    "partially nude", "partially clothed", "topless", "bottomless",
    # Lying / reclining poses
    "lying", "lying down", "lying on back", "lying on side", "lying on stomach",
    "on back", "on side", "on stomach", "on knees", "on all fours",
    "reclined", "reclining",
    # Leg / lower body poses
    "leg up", "legs up", "leg spread", "legs spread", "spread legs",
    "spread eagle", "knee up", "knees up", "legs apart", "legs together",
    "legs crossed", "crossed legs", "indian style", "seiza",
    "squatting", "kneeling", "crouching",
    # Arm / hand positions
    "arm up", "arm down", "arm at side", "arms at sides",
    "arm support", "arm over head", "arm behind back",
    "arm behind head", "arm raised", "arm out",
    "arms up", "arms down", "arms behind back", "arms behind head",
    "hand up", "hand down", "hand on hip", "hand on face",
    "hand on head", "hand rest", "hand in hair",
    "hand on own face", "hand on own head", "hand on own chest",
    "hand to mouth", "hand to cheek", "hand to chin",
    "hands up", "hands down", "hands on hips", "hands clasped",
    "hands together", "hands in hair", "hands on own chest",
    "reaching", "reaching out", "reaching up",
    "hand on another s head", "hand on another's head",
    # Head / facing
    "facing viewer", "facing away", "facing forward", "facing camera",
    "head tilt", "head down", "head up", "head back", "head turn",
    "turned", "turned away",
    # Body framing / visibility (character-relative, not scene)
    "full body", "upper body", "lower body",
    "feet out of frame", "legs out of frame",
    "cropped legs", "cropped torso", "cropped shoulders", "cropped head",
    "from below", "from above", "from side", "from behind",
    "back view", "rear view",
}

# character_traits toggle = sorter character set + explicit content + local supplement.
# Fantasy traits and expressions are handled by their own toggles.
_CHAR_TRAITS_TAGS = (
    (_SORTER_CHARACTER_TAGS - _SORTER_EXPRESSION_TAGS - _FANTASY_TAGS)
    | _LOCAL_CHAR_TAGS
    | _EXPLICIT_TAGS
)

# Single-word body/character terms for word-level compound-tag matching.
# Catches "dark_nipples", "body_freckles", "shiny_skin", "cum_on_breasts", etc.
_CHAR_TRAIT_WORDS = frozenset({
    "breast", "breasts", "nipple", "nipples", "areola",
    "cleavage", "collarbone",
    "freckles", "freckle", "mole",
    "tattoo", "tattoos",
    "sweat", "veins", "vein", "veiny",
    "nude", "naked",
    "cum", "semen",
    # Catches "wet_hair", "short_hair", "blonde_hair", etc.
    "hair",
    # Hair styles that don't contain "hair" — catches "braided_ponytail",
    # "high_ponytail", "low_twintails", "twin_braids", "side_bun", etc.
    "ponytail", "braid", "braids", "braided", "twintails", "pigtails",
    "bun", "updo", "ahoge", "bang", "bangs", "fringe",
    # Catches "dark-skinned", "light-skinned", "shiny_skin", etc.
    # (hyphens are normalised to spaces before splitting, so
    # "dark-skinned" → ["dark","skinned"] → "skinned" hits here)
    "skinned", "skin",
    "thigh", "thighs", "stomach", "belly",
})


# ---------------------------------------------------------------------------
# Clothes / accessory tag set  (WD14 tag-level matching)
# ---------------------------------------------------------------------------

_CLOTHES_TAGS = {
    # Tops
    "shirt", "t-shirt", "tshirt", "blouse", "top", "crop top", "tank top",
    "tube top", "halter top", "off shoulder", "off-shoulder", "turtleneck",
    "sweater", "hoodie", "hoodie jacket", "pullover", "polo", "polo shirt",
    "henley", "flannel", "flannel shirt", "button-up", "button up",
    "dress shirt", "jacket", "coat", "trench coat", "overcoat", "peacoat",
    "pea coat", "duster", "windbreaker", "parka", "bomber jacket",
    "leather jacket", "denim jacket", "cardigan", "vest", "blazer",
    "suit jacket", "sports jacket", "zip-up", "zip up",
    # Bottoms
    "skirt", "miniskirt", "mini skirt", "microskirt", "micro skirt",
    "pleated skirt", "pencil skirt", "maxi skirt", "a-line skirt",
    "wrap skirt", "denim skirt", "pants", "trousers", "slacks",
    "shorts", "hot pants", "boyshorts", "board shorts", "jeans",
    "skinny jeans", "leggings", "tights", "sweatpants", "joggers",
    "culottes", "palazzo pants", "wide leg pants", "cargo pants",
    # Dresses / full outfits
    "dress", "mini dress", "maxi dress", "sundress", "slip dress",
    "shirt dress", "wrap dress", "bodycon dress", "a-line dress",
    "gown", "evening gown", "ball gown", "cocktail dress",
    "uniform", "school uniform", "sailor uniform", "military uniform",
    "maid uniform", "maid outfit", "nurse uniform", "police uniform",
    "suit", "pantsuit", "tuxedo", "formal wear", "business suit",
    "kimono", "yukata", "hakama", "haori", "qipao", "cheongsam",
    "hanbok", "sari", "salwar", "kameez", "kurta", "sarong",
    "bikini", "swimsuit", "swimwear", "bathing suit", "one-piece swimsuit",
    "two-piece", "school swimsuit", "sailor dress", "competition swimsuit",
    "lingerie", "underwear", "bra", "panties", "panty", "thong",
    "g-string", "briefs", "boyshorts", "bustier", "corset", "teddy",
    "babydoll", "chemise", "negligee", "slip", "camisole", "bralette",
    "sports bra", "bodysuit", "catsuit", "leotard", "unitard", "playsuit",
    "romper", "jumpsuit", "overalls", "dungarees",
    "robe", "bathrobe", "kimono robe", "cloak", "cape", "mantle",
    "apron", "lab coat", "lab jacket", "scrubs", "coveralls",
    "tracksuit", "sweatsuit", "jogging suit",
    # Legwear
    "stockings", "thighhighs", "thigh highs", "thigh-highs",
    "over-the-knee socks", "over the knee socks", "pantyhose",
    "tights", "fishnet stockings", "fishnet tights", "fishnet",
    "socks", "knee socks", "ankle socks", "crew socks", "no-show socks",
    "leg warmers", "garter", "garter belt", "suspenders",
    # Footwear
    "boots", "ankle boots", "knee boots", "knee-high boots",
    "thigh boots", "thigh-high boots", "over-the-knee boots",
    "combat boots", "cowboy boots", "heeled boots", "platform boots",
    "high heels", "heels", "stilettos", "pumps", "wedges", "kitten heels",
    "sneakers", "trainers", "running shoes", "athletic shoes",
    "shoes", "flats", "ballet flats", "loafers", "oxfords", "brogues",
    "sandals", "flip flops", "slides", "mules", "clogs",
    "barefoot", "bare feet", "bare foot",
    # Headwear
    "hat", "cap", "baseball cap", "snapback", "beanie", "beret",
    "bucket hat", "cowboy hat", "top hat", "sun hat", "wide-brim hat",
    "hood", "bonnet", "headband", "hair band", "crown", "tiara",
    "headpiece", "fascinator", "veil", "hijab", "headscarf",
    # Clothing details / fabric tags (WD14 often tags these separately)
    "frills", "frill", "frilled", "lace", "lace trim", "ruffle", "ruffles",
    "bow", "bows", "ribbon", "ribbons", "buttons", "zipper", "buckle",
    "sleeves", "sleeve", "long sleeves", "short sleeves", "medium sleeves",
    "wide sleeves", "puffed sleeves", "bell sleeves", "detached sleeves",
    "sleeveless", "no sleeves", "bare shoulders",
    "collar", "white collar", "sailor collar", "frilled collar",
    "capelet", "pelisse", "mantle",
    # Generic category words (catches compound tags: argyle_clothes, black_footwear)
    "clothes", "clothing", "outfit", "outfits",
    "legwear", "footwear", "headwear", "neckwear", "handwear",
    # Hair accessories
    "hairband", "hair band", "hairclip", "hair clip",
    "hairpin", "hair pin", "scrunchie", "hair scrunchie",
    # Worn accessories
    "glasses", "spectacles", "eyeglasses", "sunglasses", "reading glasses",
    "mask", "face mask", "surgical mask", "gas mask", "respirator",
    "scarf", "muffler", "wrap", "shawl", "stole",
    "gloves", "mittens", "fingerless gloves", "opera gloves",
    "belt", "waistband", "tie", "necktie", "bow tie", "bowtie",
    "cravat", "ascot", "choker", "collar", "necklace", "pendant",
    "bracelet", "bangle", "wristband", "anklet",
    "earring", "earrings", "stud earrings", "hoop earrings", "drop earrings",
    "piercing", "piercings", "ear piercing", "nose ring", "nose piercing",
    "lip piercing", "navel piercing", "belly button ring", "septum piercing",
    "ring", "rings", "jewelry", "jewellery", "accessories",
    "watch", "wristwatch", "armband", "arm warmers",
    "bag", "purse", "handbag", "clutch", "backpack", "satchel",
    "ribbon", "hair ribbon", "bow", "hair bow",
}

# Single-word items for word-level compound-tag matching
# (catches "white shirt", "frilled dress", "thigh high boots", etc.)
_CLOTHES_WORDS = frozenset(item for item in _CLOTHES_TAGS if " " not in item)


# ---------------------------------------------------------------------------
# Natural-language vocabulary  (Florence2 sentence-level stripping)
# ---------------------------------------------------------------------------

_HAIR_COLORS = (
    r'blonde?|brunette|brown|dark\s+brown|light\s+brown|dirty\s+blonde?|'
    r'strawberry\s+blonde?|ash\s+blonde?|platinum\s+blonde?|'
    r'black|jet\s+black|raven|ebony|'
    r'red|auburn|ginger|copper|chestnut|rust|russet|crimson|scarlet|'
    r'white|snow\s+white|pearl|platinum|silver|silvery|grey|gray|'
    r'dark\s+grey|light\s+grey|charcoal|ash|'
    r'purple|violet|lavender|lilac|magenta|'
    r'blue|dark\s+blue|light\s+blue|navy|cobalt|sapphire|'
    r'green|mint|teal|emerald|olive|'
    r'pink|rose|coral|salmon|bubblegum|'
    r'orange|amber|peach|'
    r'golden|gold|honey|caramel|sandy|flaxen|wheat|'
    r'turquoise|aqua|cyan|indigo|'
    r'multicolored?|multi[- ]colored?|rainbow|gradient|ombre|two[- ]tone|'
    r'streaked|highlighted|dyed|bleached|frosted|pastel|neon|electric|iridescent'
)

_HAIR_STYLES = (
    r'very\s+long|extremely\s+long|extra\s+long|super\s+long|'
    r'long|short|medium|medium[- ]length|shoulder[- ]length|chin[- ]length|'
    r'wavy|curly|tightly\s+curled|loosely\s+curled|kinky|coily|'
    r'straight|pin[- ]straight|sleek|smooth|'
    r'messy|disheveled|tangled|windswept|tousled|wild|unruly|unkempt|'
    r'flowing|cascading|tumbling|sweeping|billowing|free[- ]flowing|'
    r'fluffy|voluminous|full|thick|thin|fine|wispy|sparse|'
    r'silky|lustrous|glossy|shiny|shining|gleaming|'
    r'tied|pulled\s+back|swept\s+back|pinned|clipped|'
    r'braided|french\s+braid|twin\s+braid|pigtails|'
    r'layered|feathered|razored|textured|'
    r'cropped|close[- ]cropped|buzz\s+cut|pixie|bob|lob|'
    r'dreadlocked?|dreads|locs|afro|natural|'
    r'half[- ]up|half[- ]down|let\s+down|worn\s+down|worn\s+loose'
)

_EYE_COLORS = (
    r'blue|light\s+blue|dark\s+blue|sky\s+blue|ocean\s+blue|'
    r'ice\s+blue|steel\s+blue|cobalt|sapphire|'
    r'green|light\s+green|dark\s+green|emerald|jade|forest\s+green|'
    r'lime|mint|olive|'
    r'brown|dark\s+brown|light\s+brown|warm\s+brown|honey|caramel|'
    r'hazel|amber|golden|gold|copper|bronze|'
    r'grey|gray|dark\s+grey|light\s+grey|silver|steel|'
    r'purple|violet|lavender|lilac|indigo|'
    r'red|crimson|scarlet|ruby|bloodshot|'
    r'pink|rose|'
    r'black|dark|void|'
    r'white|pale|'
    r'teal|turquoise|aqua|cyan|'
    r'orange|'
    r'yellow|golden\s+yellow|'
    r'glowing|luminous|sparkling|shimmering|piercing|intense|'
    r'bright|vivid|deep|pale|washed[- ]out|blank|empty|soulless|'
    r'heterochromatic|mismatched|multicolored?'
)

_SKIN_TONES = (
    r'pale|very\s+pale|porcelain|ivory|alabaster|'
    r'fair|light|light[- ]skinned|'
    r'olive|medium|tan|tanned|bronzed|sun[- ]kissed|sun\s+kissed|'
    r'brown|warm\s+brown|'
    r'dark|dark[- ]skinned|deep|ebony|'
    r'freckled|spotted|'
    r'golden|glowing|radiant|luminous|'
    r'smooth|flawless|clear|soft|'
    # Fantasy / non-human skin colours (demons, oni, elves, slimes, etc.)
    r'red|scarlet|crimson|blood\s+red|dark\s+red|deep\s+red|'
    r'blue|dark\s+blue|light\s+blue|cobalt|azure|'
    r'green|dark\s+green|lime\s+green|emerald\s+green|'
    r'purple|violet|lavender|'
    r'orange|burnt\s+orange|'
    r'grey|gray|ash\s+grey|ash\s+gray|stone\s+grey|'
    r'yellow|golden\s+yellow|'
    r'teal|turquoise|cyan|'
    r'pink|rosy|'
    r'ashen|chalky|deathly\s+pale|mottled|scaly'
)

_BODY_TYPES = (
    r'slender|slim|thin|lean|willowy|lithe|petite|small|tiny|'
    r'athletic|toned|fit|muscular|buff|built|strong|powerful|'
    r'curvy|curvaceous|voluptuous|busty|buxom|full[- ]figured|'
    r'tall|short|average|medium[- ]build|'
    r'chubby|plump|thick|heavyset|full|'
    r'hourglass|pear[- ]shaped|'
    r'large[- ]breasted|big[- ]breasted|flat[- ]chested'
)

_CLOTHING_NOUNS = (
    r'dress(?:es)?|gown|skirt|shirt|blouse|top|'
    r'uniform|suit|coat|jacket|vest|blazer|cardigan|'
    r'sweater|hoodie|pullover|jumper|'
    r'pants|trousers|shorts|jeans|leggings|'
    r'robe|kimono|yukata|qipao|cheongsam|hanbok|sari|sarong|'
    r'bikini|swimsuit|swimwear|'
    r'bodysuit|catsuit|leotard|jumpsuit|romper|playsuit|overalls|'
    r'lingerie|underwear|bra|corset|bustier|'
    r'cape|cloak|mantle|poncho|shawl|wrap|'
    r'apron|lab\s+coat|scrubs|coveralls|'
    r'outfit|clothing|clothes|garments?|attire|ensemble|apparel|wardrobe|'
    r'armor|armour|chainmail|breastplate|'
    r'earrings?|piercings?|jewelry|jewellery|accessories'
)

# ---------------------------------------------------------------------------
# Natural-language phrase patterns
# ---------------------------------------------------------------------------

# Flexible adjective block: 0–6 words, commas allowed between them.
# Handles "long hair", "long blonde hair", "long, flowing orange hair", etc.
_ADJ_BLOCK = r'(?:[\w-]+(?:[,\s]+[\w-]+){0,5}\s+)?'

# Possessives: her / his / their / its
_POSS = r'(?:her|his|their|its)\s+'

# Subject anchor — covers pronouns, definite/indefinite NPs, and common
# Florence2 constructions like "the character", "a young woman", etc.
_SUBJ = (
    r'(?:she|he|they|it|'
    r'(?:the|a|an)\s+(?:young\s+|old\s+|tall\s+|short\s+|small\s+)?'
    r'(?:girl|boy|woman|man|lady|gentleman|child|kid|teen|teenager|'
    r'character|figure|protagonist|heroine|hero|person|individual|'
    r'warrior|mage|witch|wizard|elf|demon|angel|spirit|creature|oni|being))'
)

# Verbs that introduce trait descriptions (present + past tense)
_HAS  = (
    r'(?:has|have|had|boasts?|boasted|sports?|sported|'
    r'features?|featured|displays?|displayed|'
    r'possesses?|possessed|shows?|showed|bore|carries?|carried)'
)
_WEAR = (
    r'(?:wears?|wore|dons?|donned|sports?|sported|'
    r'is\s+wearing|was\s+wearing|had\s+on|puts?\s+on)'
)

# Person nouns — kept when stripping appearance adjectives from subject NPs.
_PERSON_NOUNS = (
    r'woman|man|girl|boy|lady|gentleman|child|kid|teen|teenager|'
    r'character|figure|protagonist|heroine|hero|person|individual|'
    r'warrior|mage|witch|wizard|elf|demon|angel|spirit|creature|oni|being|'
    r'human|female|male|gal|guy|model|subject|babe|vixen'
)

# Appearance adjectives that qualify person nouns in Florence2 subject NPs.
# Used to strip "a brunette woman" → "a woman", "a slender blonde girl" → "a girl".
_APPEARANCE_ADJS = (
    # Hair colour words — often used as standalone person descriptors too
    r'brunette|blonde?|ginger|redhead(?:ed)?|auburn|raven(?:[- ]haired)?|'
    r'silver(?:[- ]haired)?|platinum(?:[- ]haired)?|ash(?:[- ]haired)?|'
    r'white(?:[- ]haired)?|dark(?:[- ]haired)?|black(?:[- ]haired)?|'
    r'brown(?:[- ]haired)?|golden(?:[- ]haired)?|'
    r'(?:long|short|curly|wavy|straight|flowing|messy)[- ]haired|'
    # Body-type adjectives
    r'slender|slim|lithe|willowy|lean|petite|svelte|statuesque|'
    r'curvy|curvaceous|voluptuous|busty|buxom|full[- ]figured|'
    r'athletic|toned|fit|muscular|buff|built|sculpted|'
    r'chubby|plump|thick|heavyset|'
    r'tall|short|average|'
    # Age
    r'young|old|elderly|middle[- ]aged|teenage|adult|mature|youthful|aged|'
    r'prepubescent|adolescent|'
    # General attractiveness / appearance
    r'beautiful|pretty|attractive|gorgeous|stunning|lovely|striking|'
    r'exotic|alluring|sensual|sultry|seductive|sexy|ravishing|enchanting|'
    r'elegant|graceful|radiant|luminous|ethereal|celestial|divine|'
    r'mysterious|enigmatic|fierce|wild|feral|'
    # Fantasy/creature-qualified
    r'angelic|demonic|elvish|elven|half[- ](?:elf|demon|angel|human|dragon|oni)|'
    r'wolfish|feline|vulpine|draconic|vampiric|'
    # Nationality / ethnicity descriptors (Florence2 often includes these)
    r'asian|east\s+asian|japanese|chinese|korean|'
    r'european|western|nordic|slavic|mediterranean|'
    r'latin(?:a|o)?|hispanic|'
    r'african|black|dark[- ]skinned|light[- ]skinned|'
    r'middle\s+eastern|south\s+asian|'
    # Compound body-state adjectives
    r'well[- ]endowed|large[- ]breasted|big[- ]breasted|flat[- ]chested|'
    r'broad[- ]shouldered|narrow[- ]waisted|wide[- ]hipped'
)

# Fantasy creature descriptor words — used in NL fantasy appearance patterns
_FANTASY_CREATURE_WORDS = (
    r'demon(?:ic)?|devil(?:ish)?|diabol(?:ic|ical)|infernal|hellish|'
    r'monstrous?|abyssal|eldritch|unholy|malevolent|sinister|'
    r'oni|yokai|spectral|ghostly?|wraith[- ]?like|vampiric|'
    r'undead|supernatural|otherworldly|arcane|mystical|bestial|'
    r'beast[- ]?like|creature[- ]?like|inhuman|non[- ]?human'
)

_NL_CHAR_PATTERNS: list[tuple[re.Pattern, str]] = [

    # ── Subject appearance stripping ──────────────────────────────────────────
    # Florence2 often introduces the character as "a brunette woman", "a slender
    # blonde girl", etc.  We keep the article + person noun and strip the
    # appearance adjectives so the subject mention survives in the output.

    # "a/an [adj-block] [appearance adj, comma-ok chain] [person noun]"
    # → "a/an [person noun]"
    # The appearance adj can itself be a comma-separated sequence:
    # "a brunette woman", "a slender, young girl",
    # "a tall, athletic warrior", "a beautiful blonde heroine"
    # _ADJ_BLOCK handles any preceding non-appearance words; the chain
    # `(?:[,\s]+APPEAR){0,4}` handles additional comma-separated appearance
    # adjectives between the first one and the person noun.
    (re.compile(
        r'\b(a|an)\s+' + _ADJ_BLOCK +
        r'(?:' + _APPEARANCE_ADJS + r')'
        r'(?:[,\s]+(?:' + _APPEARANCE_ADJS + r')){0,4}'
        r'\s+(' + _PERSON_NOUNS + r')\b',
        re.IGNORECASE), r'\1 \2'),

    # "a/an [adj-block] [hair-colour-as-noun]" — hair colour words used as
    # standalone person references: "a brunette,", "a blonde.", "a redhead"
    (re.compile(
        r'\b(a|an)\s+' + _ADJ_BLOCK +
        r'(?:brunette|blonde?|ginger|redhead(?:ed)?|raven|'
        r'silver[- ]haired|platinum[- ]haired)\b',
        re.IGNORECASE), r'\1 person'),

    # ── Hair ──────────────────────────────────────────────────────────────────

    # "with [adj*, comma-ok] hair [that …]"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+' + _ADJ_BLOCK +
        r'hair\b(?:\s+that\s+[^,\.]{0,50})?',
        re.IGNORECASE), ''),

    # "and [adj*, comma-ok] hair"
    (re.compile(
        r'(?:,\s*|\s+)and\s+' + _ADJ_BLOCK +
        r'hair\b(?:\s+that\s+[^,\.]{0,50})?',
        re.IGNORECASE), ''),

    # "her/his/their [adj*] hair"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?' + _POSS + _ADJ_BLOCK + r'hair\b[^,\.]{0,50}',
        re.IGNORECASE), ''),

    # "who has / that has [adj*] hair"
    (re.compile(
        r'(?:,\s*|\s+)(?:who|that)\s+has\s+' + _ADJ_BLOCK + r'hair\b',
        re.IGNORECASE), ''),

    # "featuring / sporting [adj*] hair"
    (re.compile(
        r'(?:,\s*|\s+)(?:featuring|sporting)\s+' + _ADJ_BLOCK + r'hair\b',
        re.IGNORECASE), ''),

    # "She has / He boasts / The girl features [adj*] hair [with ...]"
    # The optional "with [...]" tail absorbs stray descriptors like
    # "with a triangular green triangle" that belong to the hair description.
    (re.compile(
        r'\b' + _SUBJ + r'\s+' + _HAS + r'\s+' + _ADJ_BLOCK +
        r'hair\b(?:\s+with\s+[^,\.]{0,80})?(?:\s+that\s+[^,\.]{0,60})?',
        re.IGNORECASE), ''),

    # ── Eyes ──────────────────────────────────────────────────────────────────

    # "with [adj*, comma-ok] eyes"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+' + _ADJ_BLOCK + r'eyes?\b',
        re.IGNORECASE), ''),

    # "and [adj*, comma-ok] eyes"
    (re.compile(
        r'(?:,\s*|\s+)and\s+' + _ADJ_BLOCK + r'eyes?\b',
        re.IGNORECASE), ''),

    # "her/his/their [adj*] eyes"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?' + _POSS + _ADJ_BLOCK + r'eyes?\b',
        re.IGNORECASE), ''),

    # "who has / that has [adj*] eyes"
    (re.compile(
        r'(?:,\s*|\s+)(?:who|that)\s+has\s+' + _ADJ_BLOCK + r'eyes?\b',
        re.IGNORECASE), ''),

    # "She has / He boasts [adj*] eyes"
    (re.compile(
        r'\b' + _SUBJ + r'\s+' + _HAS + r'\s+' + _ADJ_BLOCK + r'eyes?\b[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # Comma-list item WITHOUT "and"/"with": ", yellow eyes" / ", striking yellow eyes"
    # Florence2 often comma-lists traits: "long hair, yellow eyes, pale skin".
    # The patterns above require "and/with" so bare comma items leak.
    # Requires at least one eye-colour word to avoid matching unrelated ", eyes X" phrases.
    (re.compile(
        r',\s+' + _ADJ_BLOCK + r'(?:' + _EYE_COLORS + r')\s+eyes?\b',
        re.IGNORECASE), ''),

    # ── Skin ──────────────────────────────────────────────────────────────────

    # "with [skin tone] skin"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+'
        r'(?:' + _SKIN_TONES + r')\s+skin\b',
        re.IGNORECASE), ''),

    # "and [skin tone] skin"
    (re.compile(
        r'(?:,\s*|\s+)and\s+(?:' + _SKIN_TONES + r')\s+skin\b',
        re.IGNORECASE), ''),

    # "her/his/their [adj] skin"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?' + _POSS + r'(?:' + _SKIN_TONES + r')\s+skin\b',
        re.IGNORECASE), ''),

    # "She has [skin tone] skin"
    (re.compile(
        r'\b' + _SUBJ + r'\s+' + _HAS + r'\s+'
        r'(?:' + _SKIN_TONES + r')\s+skin\b',
        re.IGNORECASE), ''),

    # "[Noun]'s [adj*] skin" — catches "The figure's striking red skin"
    # Handles possessive NPs not covered by _POSS (her/his/their/its).
    (re.compile(
        r'\b[\w]+\'s\s+' + _ADJ_BLOCK + r'skin\b[^,\.]{0,60}',
        re.IGNORECASE), ''),

    # ── Body type ─────────────────────────────────────────────────────────────

    # "with a [body type] figure/build/physique/body/frame"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+(?:a\s+|an\s+)?'
        r'(?:' + _BODY_TYPES + r')\s+'
        r'(?:figure|build|physique|body|frame|form|silhouette|stature)\b',
        re.IGNORECASE), ''),

    # "She has a slender figure / He has a muscular build"
    (re.compile(
        r'\b' + _SUBJ + r'\s+' + _HAS + r'\s+(?:a\s+|an\s+)?'
        r'(?:' + _BODY_TYPES + r')\s+'
        r'(?:figure|build|physique|body|frame|form|silhouette|stature)\b',
        re.IGNORECASE), ''),

    # "her body is slim and toned" / "his figure is athletic"
    # Catches body-type descriptions using "is" rather than "has".
    (re.compile(
        r'\b' + _POSS +
        r'(?:body|figure|build|physique|frame|silhouette|form|shape|stature)\s+'
        r'(?:is|was|appears?\s+to\s+be|looks?|seems?)\s+'
        r'(?:' + _BODY_TYPES + r')'
        r'(?:\s+and\s+(?:' + _BODY_TYPES + r'))?'
        r'\b[^,\.]{0,50}',
        re.IGNORECASE), ''),

    # "[subj]'s body / figure is [body type]"
    # Catches "The woman's body is slim and toned"
    (re.compile(
        r"\b[\w]+'s\s+"
        r'(?:body|figure|build|physique|frame|silhouette|form|shape)\s+'
        r'(?:is|was|appears?\s+to\s+be|looks?|seems?)\s+'
        r'(?:' + _BODY_TYPES + r')'
        r'(?:\s+and\s+(?:' + _BODY_TYPES + r'))?'
        r'\b[^,\.]{0,50}',
        re.IGNORECASE), ''),

    # ── Exposed / described body features ────────────────────────────────────
    # "featuring/revealing/showing/exposing mostly nude breasts"

    (re.compile(
        r'(?:,\s*|\s+)(?:featuring|revealing|showing|exposing|displaying)\s+'
        r'(?:mostly\s+|partially\s+|nearly\s+|bare\s+|nude\s+|naked\s+|exposed\s+)?'
        r'(?:breasts?|nipples?|cleavage|chest|torso|nudity|flesh|skin|body)\b'
        r'[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "with [adj*] breasts / bust / bosom / cleavage / chest / nipples"
    # Prefix optional — catches both mid-sentence and sentence-initial forms.
    (re.compile(
        r'(?:(?:,\s*|\s+)(?:and\s+)?)?\bwith\s+' + _ADJ_BLOCK +
        r'(?:breasts?|bust|bosom|cleavage|nipples?|areola[e]?|d(?:é|e)colletage)\b'
        r'[^,\.]{0,50}',
        re.IGNORECASE), ''),

    # Comma-list item WITHOUT "and"/"with": ", large breasts" / ", huge bust"
    # Same gap as the yellow-eyes comma-list fix — requires a size/shape adjective
    # before the body-feature noun so bare ", breasts" isn't over-matched.
    (re.compile(
        r',\s+' + _ADJ_BLOCK +
        r'(?:large|huge|big|small|flat|pert|perky|round|full|heavy|natural|'
        r'bare|exposed|visible|bouncy|pendulous|voluminous)\s+'
        r'(?:breasts?|bust|bosom|nipples?|cleavage)\b'
        r'[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "she has / the girl boasts [adj*] breasts / bust / curves / hips"
    (re.compile(
        r'\b' + _SUBJ + r'\s+' + _HAS + r'\s+' + _ADJ_BLOCK +
        r'(?:breasts?|bust|bosom|cleavage|curves?|hips?|waist|figure)\b'
        r'[^,\.]{0,50}',
        re.IGNORECASE), ''),

    # "with [adj*] hips / waist / abs / curves / midriff"
    (re.compile(
        r'(?:(?:,\s*|\s+)(?:and\s+)?)?\bwith\s+' + _ADJ_BLOCK +
        r'(?:hips?|waist|abs?|abdominals?|muscles?|curves?|midriff|navel)\b'
        r'[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "her breasts / stomach / thighs / back / skin are/is visible / bare / exposed"
    (re.compile(
        r'\b' + _POSS +
        r'(?:breasts?|nipples?|stomach|midriff|navel|belly|'
        r'thighs?|legs?|skin|back|shoulders?|chest|cleavage|curves?)\s+'
        r'(?:are?|is|was|were)\s+'
        r'(?:visible|exposed|bare|showing|uncovered|revealed|naked|nude|on\s+display)\b'
        r'[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "with freckles [on/across ...]" / "covered in freckles"
    (re.compile(
        r'(?:(?:,\s*|\s+)(?:and\s+)?)?\bwith\s+'
        r'(?:(?:light|dark|faint|numerous|many|scattered|subtle|heavy|adorable|'
        r'cute|visible|small)\s+)?'
        r'(?:freckles?|spots?|skin\s+blemishes?|beauty\s+spots?)\b[^,\.]{0,60}',
        re.IGNORECASE), ''),
    (re.compile(
        r'(?:(?:,\s*|\s+)(?:and\s+)?)?\bcovered\s+(?:in|with)\s+'
        r'(?:freckles?|spots?|skin\s+blemishes?)\b[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "She has [adj*] lips / mouth / face / complexion / features"
    (re.compile(
        r'\b' + _SUBJ + r'\s+' + _HAS + r'\s+' + _ADJ_BLOCK +
        r'(?:lips?|mouth|face|complexion|features?|appearance|look)\b[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # ── Body markings / tattoos / piercings ──────────────────────────────────
    # "and a small tattoo on her left breast" / "a tattoo on her arm"
    # "a scar on her shoulder" / "a birthmark on her back" / "a mole on her cheek"

    # "[,/and] a/an [adj?] tattoo/piercing/scar/birthmark/mole [on ...]"
    # Prefix is optional so sentence-initial phrases are also caught.
    (re.compile(
        r'(?:(?:,\s*|\s+)(?:and\s+)?)?\b(?:a|an|the)\s+'
        r'(?:(?:small|large|tiny|little|big|elaborate|intricate|simple|delicate|'
        r'faint|subtle|visible|prominent|colou?rful|black|red|dark|tribal|floral|'
        r'geometric|minimalist|decorative)\s+)?'
        r'(?:tattoo|tattoos?|piercing|piercings?|birthmark|birthmarks?|'
        r'scar|scars?|brand|brands?|marking|markings?|blemish|blemishes|'
        r'beauty\s+mark|mole|freckle|freckles?)\b'
        r'[^,\.]{0,80}',
        re.IGNORECASE), ''),

    # "She has a tattoo / piercing / scar [on/along ...]"
    (re.compile(
        r'\b' + _SUBJ + r'\s+' + _HAS + r'\s+(?:a\s+|an\s+|the\s+)?'
        r'(?:(?:small|large|tiny|little|elaborate|intricate|faint|subtle|'
        r'visible|prominent|colou?rful)\s+)?'
        r'(?:tattoo|piercing|birthmark|scar|marking|beauty\s+mark|mole)\b'
        r'[^,\.]{0,60}',
        re.IGNORECASE), ''),

]

# Fantasy / non-human trait phrases — own list so the fantasy_traits toggle
# controls them independently.
_FANTASY_APPENDAGES = (
    r'ears?|tails?|horns?|wings?|halo|fangs?|claws?|antlers?|'
    r'tentacles?|scales?|fur|feathers?|paws?'
)

_NL_FANTASY_PATTERNS: list[tuple[re.Pattern, str]] = [

    # ── Creature appearance / nature ──────────────────────────────────────────

    # "with a [adj*, comma-ok] demonic/monstrous appearance/form/nature"
    # Catches "with a red, demonic appearance"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+(?:a\s+|an\s+)?' + _ADJ_BLOCK +
        r'(?:' + _FANTASY_CREATURE_WORDS + r')'
        r'(?:\s+(?:appearance|look|form|body|features?|aura|nature|presence|aesthetic))?'
        r'\b[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # "of a/an [adj*] monstrous figure / demonic being / creature"
    # Catches "portrayal of a monstrous figure"
    (re.compile(
        r'\bof\s+(?:a\s+|an\s+)?' + _ADJ_BLOCK +
        r'(?:' + _FANTASY_CREATURE_WORDS + r')\s+'
        r'(?:figure|character|being|creature|entity|individual|form|appearance)\b'
        r'[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "[subj] is/was a/an [adj*] demon/oni/vampire/etc."
    (re.compile(
        r'\b' + _SUBJ + r'\s+(?:is|was|appears?\s+to\s+be|seems?\s+to\s+be)\s+'
        r'(?:a\s+|an\s+)?' + _ADJ_BLOCK +
        r'(?:' + _FANTASY_CREATURE_WORDS + r')\b[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # ── Fantasy appendages ────────────────────────────────────────────────────

    # "with [adj*] ears/tail/horns/wings/etc."
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+' + _ADJ_BLOCK +
        r'(?:' + _FANTASY_APPENDAGES + r')\b',
        re.IGNORECASE), ''),

    # "and [adj*] ears/tail/etc."
    (re.compile(
        r'(?:,\s*|\s+)and\s+' + _ADJ_BLOCK +
        r'(?:' + _FANTASY_APPENDAGES + r')\b',
        re.IGNORECASE), ''),

    # "her/his/their [adj*] ears/tail/etc."
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?' + _POSS + _ADJ_BLOCK +
        r'(?:' + _FANTASY_APPENDAGES + r')\b',
        re.IGNORECASE), ''),

    # "who has / that has [adj*] ears/horns/etc."
    (re.compile(
        r'(?:,\s*|\s+)(?:who|that)\s+has\s+' + _ADJ_BLOCK +
        r'(?:' + _FANTASY_APPENDAGES + r')\b',
        re.IGNORECASE), ''),

    # "She has / The elf boasts [adj*] ears/tail/horns/wings/etc."
    (re.compile(
        r'\b' + _SUBJ + r'\s+' + _HAS + r'\s+' + _ADJ_BLOCK +
        r'(?:' + _FANTASY_APPENDAGES + r')\b[^,\.]{0,40}',
        re.IGNORECASE), ''),
]

# Expression phrases
_NL_EXPR_PATTERNS: list[tuple[re.Pattern, str]] = [
    # standalone expression participle: "smiling", "blushing", etc.
    (re.compile(
        r'(?:,\s*|\s+)(?:who\s+is\s+|who\s+appears\s+)?'
        r'(?:smiling|grinning|beaming|laughing|chuckling|giggling|snickering|'
        r'blushing|flushing|reddening|'
        r'frowning|scowling|glaring|glowering|sneering|'
        r'crying|weeping|sobbing|tearing\s+up|teary|'
        r'pouting|sulking|brooding|'
        r'winking|smirking|leering|'
        r'grimacing|wincing|cringing|menacing)\b',
        re.IGNORECASE), ''),

    # "with a smile / with a grin / with tears in her eyes"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+(?:a\s+|an\s+)?'
        r'(?:smile|grin|smirk|frown|pout|scowl|glare|sneer|blush|'
        r'tears?|teary\s+eyes?|look\s+of\s+(?:\w+\s+){0,3}(?:sadness|joy|anger|fear|surprise|disgust))\b'
        r'[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # "looking [emotion]"  — only when clearly emotional, not directional
    (re.compile(
        r'(?:,\s*|\s+)looking\s+'
        r'(?:happy|sad|angry|upset|frightened|scared|nervous|anxious|'
        r'embarrassed|shy|confident|seductive|sultry|fierce|menacing|'
        r'shocked|surprised|confused|worried|pensive|melancholic|'
        r'joyful|ecstatic|furious|enraged|terrified|gleeful|playful)\b',
        re.IGNORECASE), ''),

    # "an expression of [emotion]"
    (re.compile(
        r'(?:,\s*|\s+)(?:with\s+)?an?\s+expression\s+of\s+[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "mouth/lips/jaw is open / open mouth" — catches "its mouth is open"
    (re.compile(
        r'(?:,\s*|\s+|\b)(?:its?|her|his|their|the\s+\w+\'s)\s+'
        r'(?:open|gaping|agape|wide[- ]?open|parted)\s+'
        r'(?:mouth|maw|jaw|lips?)\b[^,\.]{0,40}',
        re.IGNORECASE), ''),
    (re.compile(
        r'(?:,\s*|\s+|\b)(?:mouth|lips?|jaw)\s+'
        r'(?:is|was|are|were|being)\s+'
        r'(?:open|agape|ajar|parted|wide|gaping)\b[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "in an act of [action]" — catches "in an act of menacing brushing"
    (re.compile(
        r'(?:,\s*|\s+)in\s+an?\s+act\s+of\s+[^,\.]{0,60}',
        re.IGNORECASE), ''),

    # "licking [her/his/their] lips" / "licking lips"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?licking\s+(?:her|his|their|its\s+)?lips?\b[^,\.]{0,20}',
        re.IGNORECASE), ''),

    # "talking" / "speaking" / "saying [something]"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?(?:talking|speaking|whispering|shouting|calling\s+out)\b[^,\.]{0,30}',
        re.IGNORECASE), ''),
]

_NL_CLOTH_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "wearing [a/an] [...clothing...]"  (participial / mid-sentence)
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?(?:who\s+is\s+)?wearing\s+'
        r'(?:a\s+|an\s+|the\s+)?[^,\.]*?(?:' + _CLOTHING_NOUNS + r')[^,\.]*',
        re.IGNORECASE), ''),

    # "She wears / He wore / The girl dons [a/an] [clothing]"
    (re.compile(
        r'\b' + _SUBJ + r'\s+' + _WEAR + r'\s+'
        r'(?:a\s+|an\s+|the\s+)?[^\.!?]*',
        re.IGNORECASE), ''),

    # "dressed in / clad in / clothed in / adorned in [...]"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?(?:dressed|clad|clothed|adorned)\s+in\s+[^,\.]*',
        re.IGNORECASE), ''),

    # "donning / sporting [a/an] [clothing]"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?(?:donning|sporting)\s+'
        r'(?:a\s+|an\s+|the\s+)?[^,\.]*?(?:' + _CLOTHING_NOUNS + r')[^,\.]*',
        re.IGNORECASE), ''),

    # "decked out in [...]"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?decked\s+out\s+in\s+[^,\.]*',
        re.IGNORECASE), ''),

    # "in a/an [clothing]"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?in\s+(?:a|an)\s+'
        r'[^,\.]*?(?:' + _CLOTHING_NOUNS + r')[^,\.]*',
        re.IGNORECASE), ''),

    # "with a/an [clothing]"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+(?:a|an)\s+'
        r'[^,\.]*?(?:' + _CLOTHING_NOUNS + r')[^,\.]*',
        re.IGNORECASE), ''),

    # "her/his/their [clothing]"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?' + _POSS +
        r'(?:[^,\.]*?)?(?:' + _CLOTHING_NOUNS + r')[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # "[Noun]'s [clothing]" — catches "The figure's earring is raised"
    # Handles possessive NPs not covered by _POSS (her/his/their/its).
    (re.compile(
        r'\b[\w]+\'s\s+(?:[^,\.]*?)?(?:' + _CLOTHING_NOUNS + r')[^,\.]{0,30}',
        re.IGNORECASE), ''),
]

# Furry / anthro NL phrase patterns
_NL_FURRY_PATTERNS: list[tuple[re.Pattern, str]] = [

    # "with [adj*] fur [covering/on/all over ...]"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+' + _ADJ_BLOCK +
        r'fur\b[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "covered/coated/blanketed in [adj*] fur"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?(?:covered|coated|blanketed|draped)\s+in\s+'
        + _ADJ_BLOCK + r'fur\b[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # "her/his/their [adj*] fur"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?' + _POSS + _ADJ_BLOCK + r'fur\b[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # "She has / The wolf boasts [adj*] fur [covering ...]"
    (re.compile(
        r'\b' + _SUBJ + r'\s+' + _HAS + r'\s+' + _ADJ_BLOCK +
        r'fur\b[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "with a [adj*] snout / muzzle"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+(?:a\s+|an\s+)?' + _ADJ_BLOCK +
        r'(?:snout|muzzle)\b[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # "She has a [adj*] snout / muzzle / whiskers"
    (re.compile(
        r'\b' + _SUBJ + r'\s+' + _HAS + r'\s+(?:a\s+|an\s+)?' + _ADJ_BLOCK +
        r'(?:snout|muzzle|whiskers?)\b[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # "with whiskers"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+(?:long\s+|short\s+|thin\s+)?whiskers?\b',
        re.IGNORECASE), ''),

    # "with [adj*] paws / paw pads / animal feet/hands"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+' + _ADJ_BLOCK +
        r'(?:paws?|paw\s+pads?|animal\s+(?:feet|foot|hands?|paws?))\b[^,\.]{0,20}',
        re.IGNORECASE), ''),

    # "with [adj*] animal/furry/anthro features/markings/body"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+(?:a\s+|an\s+)?' + _ADJ_BLOCK +
        r'(?:animal|furry|anthro)\s+'
        r'(?:features?|markings?|characteristics?|traits?|body|appearance|anatomy)\b'
        r'[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # "fur-covered / fur-coated [body part]"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?fur[- ](?:covered|coated|lined|trimmed)\s+'
        r'[^,\.]{0,30}',
        re.IGNORECASE), ''),
]

# ---------------------------------------------------------------------------
# Meta / boilerplate patterns — ALWAYS applied, no toggle required.
# These are PromptGen CYA disclaimers and watermark/meta commentary that
# are never useful in a generation prompt.
# ---------------------------------------------------------------------------

_NL_META_PATTERNS: list[tuple[re.Pattern, str]] = [

    # ── Age / legal / ethnicity disclaimers ───────────────────────────────────
    # PromptGen v2.0 often appends these to comply with content policies.

    # "she appears to be a licensed adult" / "appears to be a consenting adult"
    (re.compile(
        r'\b(?:she|he|they|it|'
        r'(?:the|a|an)\s+\w+)\s+'
        r'appears?\s+to\s+be\s+'
        r'(?:a\s+)?(?:licensed\s+|consenting\s+|legal\s+)?adult\b[^,\.]{0,60}',
        re.IGNORECASE), ''),

    # "appears to be of legal age" / "of legal / consenting age"
    (re.compile(
        r'\b(?:appears?\s+to\s+be\s+of\s+)?(?:legal|consenting)\s+age\b[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "who appears to be in her late teens / early twenties"
    # "appears to be around 20 years old" / "estimated age of 25"
    (re.compile(
        r'\b(?:who\s+)?appears?\s+to\s+be\s+in\s+'
        r'(?:(?:her|his|their)\s+)?'
        r'(?:early|mid[- ]?|late)\s*'
        r'(?:teens?|twenties?|thirties?|forties?|fifties?|sixties?|seventies?)\b'
        r'[^,\.]{0,40}',
        re.IGNORECASE), ''),
    (re.compile(
        r'\bappears?\s+to\s+be\s+(?:around\s+|approximately\s+|about\s+)?'
        r'\d+(?:\s*[-–]\s*\d+)?\s+years?\s+(?:old|of\s+age)\b[^,\.]{0,30}',
        re.IGNORECASE), ''),
    (re.compile(
        r'\b(?:estimated|approximate|approx\.?)\s+age\s+(?:of\s+)?\d+\b[^,\.]{0,30}',
        re.IGNORECASE), ''),
    (re.compile(
        r'\b\d+\s+years?\s+(?:old|of\s+age)\b[^,\.]{0,20}',
        re.IGNORECASE), ''),

    # "with no specific age or ethnicity preference"
    # "with no specific age indicated / specified"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?with\s+no\s+specific\s+'
        r'(?:age|ethnicity|race|nationality|gender)'
        r'(?:\s+or\s+(?:age|ethnicity|race|nationality|gender))?\s+'
        r'(?:preference|indicated?|specified?|mentioned?|given|shown|depicted?)\b[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "no specific age / ethnicity preference" (without leading "with")
    (re.compile(
        r'(?:,\s*|\s+)no\s+specific\s+'
        r'(?:age|ethnicity|race|nationality)'
        r'(?:\s+or\s+\w+)?\s+'
        r'(?:preference|is\s+indicated?|is\s+specified?|indicated?|specified?)\b[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "age is unknown / not specified / unclear"
    (re.compile(
        r'\b(?:her|his|their\s+)?age\s+'
        r'(?:is\s+)?(?:unknown|unspecified|unclear|indeterminate|'
        r'not\s+(?:specified|mentioned|given|shown|clear|determined))\b[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # "ethnicity / race is unknown / not specified"
    (re.compile(
        r'\b(?:her|his|their\s+)?(?:ethnicity|race|nationality)\s+'
        r'(?:is\s+)?(?:unknown|unspecified|unclear|'
        r'not\s+(?:specified|mentioned|given|shown|clear|determined))\b[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # "it is difficult / unclear / impossible to determine [age/who/what]"
    (re.compile(
        r'\bit\s+is\s+'
        r'(?:difficult|hard|impossible|not\s+possible|unclear|uncertain|impossible)\s+'
        r'(?:to\s+(?:determine|tell|say|know|identify|ascertain)|whether)\s+'
        r'[^,\.]{0,80}',
        re.IGNORECASE), ''),

    # "please note that / note: / it should be noted that" — disclaimer preambles
    (re.compile(
        r'\b(?:it\s+should\s+be\s+noted|please\s+note)\s+'
        r'(?:that\s+)?[^,\.]{0,80}',
        re.IGNORECASE), ''),
    (re.compile(
        r'\bnote\s*:\s*[^,\.]{0,80}',
        re.IGNORECASE), ''),

    # ── Watermark / signature / image-meta commentary ─────────────────────────

    # "the artist's signature / name / watermark is [also] visible in the corner"
    (re.compile(
        r"\b(?:the\s+)?artist(?:'s?)?\s+"
        r'(?:signature|name|watermark|mark|logo|tag|handle|username)\b'
        r'[^\.]{0,100}',
        re.IGNORECASE), ''),

    # "there is a watermark that reads 'patreon.com/balexi'"
    # "there is a patreon watermark" / "there is a small signature"
    # Tail: quoted strings consumed whole; unquoted URLs step through internal
    # dots (\.(?=\w)) so "MisaMi.com/misamart" isn't truncated to "MisaMi".
    # Trailing \.? consumes the sentence-ending period so it doesn't orphan.
    (re.compile(
        r'\bthere\s+(?:is|are)\s+(?:a\s+|the\s+|an?\s+)?'
        r'(?:\w+\s+)?'
        r'(?:watermark|signature|logo|copyright\s+(?:notice|mark|symbol))\b'
        r'(?:"[^"]*"|\'[^\']*\'|(?:[^,\.\n]|\.(?=\w)))*\.?',
        re.IGNORECASE), ''),

    # "a/the watermark / signature that reads / saying [content]"
    # Sentence-initial or mid-sentence.
    (re.compile(
        r'(?:(?:,\s*|\s+)(?:and\s+)?)?\b(?:a|the|an)\s+'
        r'(?:\w+\s+)?'
        r'(?:watermark|signature|logo|copyright\s+(?:notice|mark|symbol))\s+'
        r'(?:that\s+reads?|that\s+says?|reading|saying|which\s+reads?)\s*'
        r'(?:"[^"]*"|\'[^\']*\'|(?:[^,\.\n]|\.(?=\w)))*\.?',
        re.IGNORECASE), ''),

    # "a watermark / signature is visible / present / can be seen"
    (re.compile(
        r'(?:,\s*|\s+)(?:a\s+|the\s+)?'
        r'(?:watermark|signature|copyright\s+(?:notice|mark|symbol)|logo)\s+'
        r'(?:is\s+(?:also\s+)?|appears?\s+to\s+be\s+)?'
        r'(?:visible|present|shown|displayed|seen?|located?|found?|placed?|legible)\b'
        r'[^,\.]{0,60}',
        re.IGNORECASE), ''),

    # "the image is signed [by the artist / by KITEW / 'KITEW' / with name X / in the corner]"
    # Matches only when preceded by:
    #   (a) a comma (mid-sentence clause: ", signed KITEW" / ", the artwork is signed …")
    #   (b) sentence-start "the [image/artwork/…] is" (no prior comma needed)
    # Does NOT fire on bare mid-sentence "signed" (e.g. "holds a signed letter").
    (re.compile(
        r'(?:'
        r'(?:,\s*)(?:the\s+(?:image|photo|illustration|artwork|picture|piece|work)\s+(?:is\s+)?)?'
        r'|the\s+(?:image|photo|illustration|artwork|picture|piece|work)\s+(?:is\s+)?'
        r')'
        r'signed\b[^,\.]{0,70}',
        re.IGNORECASE), ''),

    # "the image is titled / called / entitled 'NYUUNZ'"
    # Florence2 misreads artist handles / watermarks as titles.
    # Matches sentence-start ("The image is titled X") and mid-sentence
    # (", titled X" / ", the artwork is titled X").
    (re.compile(
        r'(?:'
        r'(?:,\s*)(?:the\s+(?:image|photo|illustration|artwork|picture|piece|work)\s+(?:is\s+)?)?'
        r'|(?:the\s+(?:image|photo|illustration|artwork|picture|piece|work)\s+(?:is\s+)?)'
        r'|(?:it\s+is\s+|this\s+is\s+)'
        r')'
        r'(?:titled?|called|entitled|named|known\s+as)\b[^,\.]{0,70}',
        re.IGNORECASE), ''),

    # "the image/artwork contains/features a watermark/signature"
    (re.compile(
        r'(?:(?:,\s*|\s+))?(?:the\s+)?'
        r'(?:image|artwork|illustration|photo|picture|piece|work)\s+'
        r'(?:contains?|features?|includes?|has|shows?|displays?|bears?)\s+'
        r'(?:a\s+|the\s+|an?\s+)?(?:\w+\s+)?'
        r'(?:watermark|signature|logo|copyright\s+(?:notice|mark|symbol))\b'
        r'(?:"[^"]*"|\'[^\']*\'|(?:[^,\.\n]|\.(?=\w)))*\.?',
        re.IGNORECASE), ''),

    # "there is a URL / link / web address [in the image / reading X]"
    (re.compile(
        r'\bthere\s+(?:is|are)\s+(?:a\s+|the\s+|an?\s+)?(?:\w+\s+)?'
        r'(?:url|link|web\s+address|website\s+address|hyperlink|web\s+link)\b'
        r'(?:"[^"]*"|\'[^\']*\'|(?:[^,\.\n]|\.(?=\w)))*\.?',
        re.IGNORECASE), ''),

    # "the creator's / artist's handle / username / link is visible"
    (re.compile(
        r'\b(?:the\s+)?'
        r'(?:creator|author|artist|illustrator|photographer|uploader)(?:\'s?)?\s+'
        r'(?:handle|username|social\s+media|profile\s+link|link|url|tag|account|page)\b'
        r'[^\.]{0,80}',
        re.IGNORECASE), ''),

    # "all/any characters [depicted/shown] are adults / 18+ / of legal age"
    (re.compile(
        r'\b(?:all|any)\s+(?:characters?|depicted\s+characters?|persons?|individuals?)\s+'
        r'(?:(?:depicted|shown|portrayed|featured)\s+)?(?:are|is)\s+'
        r'(?:legal(?:ly\s+)?(?:of\s+age|adults?)|(?:consenting\s+)?adults?|'
        r'(?:of\s+)?legal\s+age|18\s*\+|18\s*plus|eighteen\s+(?:or\s+)?(?:older|over|plus)|'
        r'over\s+18|at\s+least\s+18)[^,\.]{0,60}',
        re.IGNORECASE), ''),

    # "the depicted character[s] are [legal adult / 18+]" — variant order
    (re.compile(
        r'\b(?:any|all)?\s*(?:character|person|individual|figure)s?\s+'
        r'(?:in\s+this\s+(?:image|artwork|illustration|content)\s+)?'
        r'(?:are?|is)\s+(?:fictional\s+and\s+)?'
        r'(?:(?:consenting\s+)?adults?|18\s*\+|18\s*plus|of\s+legal\s+age)'
        r'[^,\.]{0,60}',
        re.IGNORECASE), ''),

    # "fictional characters / any resemblance is coincidental" — boilerplate
    (re.compile(
        r'\b(?:any\s+)?(?:all\s+)?characters?\s+(?:depicted\s+)?(?:are\s+)?fictional\b'
        r'[^\.]{0,80}',
        re.IGNORECASE), ''),

    # "in the [top/bottom] [left/right/center] corner" — positional watermark ref
    # Only strip when standalone (sentence-final), not mid-sentence scene positions.
    (re.compile(
        r'(?:,\s*|\s+)(?:located\s+)?in\s+the\s+'
        r'(?:top|bottom|upper|lower)\s+(?:right|left|center)\s+corner\s*[,\.]?',
        re.IGNORECASE), ''),

    # "the image quality / resolution is [X]"
    (re.compile(
        r'(?:,\s*|\s+)(?:the\s+)?(?:image|photo|picture)\s+'
        r'(?:quality|resolution)\s+(?:is|appears?\s+to\s+be)\s+[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "this appears to be an AI-generated / digitally created image"
    (re.compile(
        r'(?:,\s*|\s+)(?:this\s+)?(?:appears?\s+to\s+be\s+)?'
        r'(?:an?\s+)?(?:AI[- ]generated|digitally[- ](?:created|rendered|painted|drawn)|'
        r'computer[- ]generated|CGI|3D[- ]rendered)\s+'
        r'(?:image|illustration|artwork|render|picture)\b[^,\.]{0,40}',
        re.IGNORECASE), ''),
    # ── Positional / compositional layout descriptions ───────────────────────
    # Florence2 describes where each character is standing in the frame.
    # These are never useful generation tokens; they also leave orphan fragments
    # like "one in the middle, and one on the right" after partial fantasy strips.

    # "one [entity?] on the left / in the middle / on the right"
    # "one on each side" / "on either side"
    # Catches both the anchored form and orphan fragments.
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?(?:one|two|three|another|each)\s+'
        r'(?:(?:[\w-]+\s+){0,3})?'
        r'(?:on\s+(?:the\s+(?:left|right|far\s+left|far\s+right|outer\s+(?:left|right))|'
        r'each\s+side|either\s+side)|'
        r'in\s+the\s+(?:center|middle|background|foreground|front|back))\b'
        r'[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "side by side" / "in a row" / "in a line" / "from left to right"
    # Also: "positioned/arranged symmetrically" and reverse word order
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?'
        r'(?:side\s+by\s+side|in\s+a\s+row|in\s+a\s+line|back\s+to\s+back|'
        r'from\s+left\s+to\s+right|from\s+right\s+to\s+left|'
        r'evenly\s+spaced|equally\s+spaced|'
        r'(?:symmetrically|evenly|neatly)\s+(?:placed|arranged|positioned|spaced)|'
        r'(?:placed|arranged|positioned)\s+symmetrically|'
        r'arranged\s+(?:in\s+a\s+row|side\s+by\s+side|symmetrically|evenly))\b'
        r'[^,\.]{0,30}',
        re.IGNORECASE), ''),

    # "positioned / standing / placed [on the left / in the center / ...]"
    (re.compile(
        r'(?:,\s*|\s+)(?:and\s+)?'
        r'(?:positioned|standing|placed|located|situated|depicted|shown|seen)\s+'
        r'(?:on\s+the\s+(?:left|right)|in\s+the\s+(?:center|middle|background|foreground)|'
        r'(?:to\s+the\s+)?(?:left|right)\s+(?:side|of\s+the\s+(?:frame|image|scene))|'
        r'symmetrically|evenly)\b'
        r'[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # Dangling prepositions/conjunctions left after phrase removal
    # e.g. "with" after "with one elf on the left [stripped]"
    (re.compile(
        r'(?:^|(?<=,)\s*)(?:with|and|or|but)\s*$',
        re.IGNORECASE | re.MULTILINE), ''),
]

# Overlay text patterns — toggle-controlled (overlay_text).
# Strips Florence2 descriptions of visible text/signs/writing IN the image.
# Disable this toggle when you want to preserve text descriptions —
# e.g. Anima can generate legible signs/captions that may be worth keeping.

_NL_TEXT_PATTERNS: list[tuple[re.Pattern, str]] = [

    # "text / writing / inscription reading / saying '...'"
    # Uses \b so it matches sentence-initially as well as mid-sentence.
    (re.compile(
        r'\b(?:some\s+|the\s+|any\s+)?'
        r'(?:text|writing|inscription|lettering|typography|words?)\s+'
        r'(?:reading|saying|that\s+reads?|that\s+says?|which\s+reads?|which\s+says?)\s*'
        r'[^,\.]{0,80}',
        re.IGNORECASE), ''),

    # "a/the sign / label / caption / banner reading / saying '...'"
    # Requires the content verb (reading/saying) to avoid matching scene signs.
    (re.compile(
        r'\b(?:a\s+|the\s+)?(?:[\w-]+\s+)?'
        r'(?:sign|label|caption|banner|placard|poster|notice|board|tag)\s+'
        r'(?:reading|saying|that\s+reads?|that\s+says?|which\s+reads?|which\s+says?)\s*'
        r'[^,\.]{0,80}',
        re.IGNORECASE), ''),

    # "the word(s) '...' is/are written / visible / present"
    (re.compile(
        r'\b(?:the\s+)?words?\s+'
        r'(?:[\'\"«].{0,40}[\'\"»]\s+)?'
        r'(?:(?:is|are)\s+)?(?:written|visible|present|displayed|shown|printed)\b'
        r'[^,\.]{0,40}',
        re.IGNORECASE), ''),

    # "visible text / overlaid text / on-screen text"
    (re.compile(
        r'\b(?:visible|overlaid?|on[- ]screen|superimposed?|embedded?)\s+'
        r'(?:text|writing|lettering|caption|typography)\b[^,\.]{0,50}',
        re.IGNORECASE), ''),

    # "text overlay / text box / text element"
    (re.compile(
        r'\b(?:a\s+|the\s+)?text\s+'
        r'(?:overlay|box|element|block|area|field)\b'
        r'[^,\.]{0,60}',
        re.IGNORECASE), ''),

    # "there is text / writing [on/in ...]"
    (re.compile(
        r'\bthere\s+(?:is|are)\s+'
        r'(?:some\s+)?(?:text|writing|words?|lettering|a\s+caption|a\s+label)\b'
        r'[^,\.]{0,60}',
        re.IGNORECASE), ''),

    # "written on [a sign/the wall/a banner/...]"
    (re.compile(
        r'\bwritten\s+(?:on|across|upon)\s+'
        r'(?:a\s+|the\s+)?(?:sign|wall|banner|board|surface|poster|label)\b'
        r'[^,\.]{0,50}',
        re.IGNORECASE), ''),
]

# Cleanup applied after phrase removal
_CLEANUP_PATTERNS = [
    (re.compile(r'\s{2,}'),                               ' '),
    (re.compile(r'\s*,\s*,+'),                            ','),
    (re.compile(r'^[\s,]+'),                              ''),
    (re.compile(r'[\s,]+$'),                              ''),
    (re.compile(r',\s*(?:and|with|or)\s*,', re.IGNORECASE), ','),
    (re.compile(r'\bwith\s*,'),                           ','),
    (re.compile(r'\band\s*,'),                            ','),
    (re.compile(r'\s+,'),                                 ','),
    # Orphaned punctuation left after phrase removal
    (re.compile(r'(?<!\w)\.\s*$'),                        ''),   # trailing lone period
    (re.compile(r'^\s*\.(?!\w)'),                         ''),   # leading lone period
]


def _strip_nl_phrases(text: str, toggles: dict) -> tuple[str, list[str]]:
    """Remove character-trait and clothing phrases from a natural-language
    string.  Returns (cleaned_text, list_of_removed_snippets)."""
    result  = text
    removed: list[str] = []

    # Meta / boilerplate patterns run unconditionally — these are never useful
    # in a generation prompt regardless of which toggles are active.
    for pat, repl in _NL_META_PATTERNS:
        for m in pat.finditer(result):
            snippet = m.group(0).strip(" ,")
            if snippet:
                removed.append(snippet)
        result = pat.sub(repl, result)

    patterns: list[tuple[re.Pattern, str]] = []
    if toggles.get("character_traits"):
        patterns.extend(_NL_CHAR_PATTERNS)
    if toggles.get("expressions"):
        patterns.extend(_NL_EXPR_PATTERNS)
    if toggles.get("fantasy_traits"):
        patterns.extend(_NL_FANTASY_PATTERNS)
    if toggles.get("clothes"):
        patterns.extend(_NL_CLOTH_PATTERNS)
    if toggles.get("furry"):
        patterns.extend(_NL_FURRY_PATTERNS)
    if toggles.get("overlay_text"):
        patterns.extend(_NL_TEXT_PATTERNS)

    for pat, repl in patterns:
        for m in pat.finditer(result):
            snippet = m.group(0).strip(" ,")
            if snippet:
                removed.append(snippet)
        result = pat.sub(repl, result)

    for pat, repl in _CLEANUP_PATTERNS:
        result = pat.sub(repl, result)

    return result.strip(), removed


# ---------------------------------------------------------------------------
# Helpers (tag-level)
# ---------------------------------------------------------------------------

def _normalise(tag: str) -> str:
    return tag.lower().strip().replace("_", " ")


def _split_tags(text: str) -> list[str]:
    """Split on commas, respecting parenthesis depth."""
    if not text or not text.strip():
        return []
    tags: list[str] = []
    depth   = 0
    current: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1; current.append(ch)
        elif ch == ")":
            depth -= 1; current.append(ch)
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


def _parse_exclude_patterns(exclude_text: str) -> list[str]:
    raw: list[str] = []
    for line in exclude_text.splitlines():
        for part in line.split(","):
            s = part.strip()
            if s:
                raw.append(s)
    return [_normalise(p) for p in raw]


def _tag_excluded_by_pattern(tag_norm: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(tag_norm, pat) for pat in patterns)


# ---------------------------------------------------------------------------
# Subject / composition whitelist — these tags are NEVER filtered by toggles.
# They describe who is in the frame (count, grouping), not what they look like.
# A group photo should still say "group photo".  A solo shot should say "solo".
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Meta / attribution tag set — ALWAYS filtered, no toggle required.
# These are image-metadata tags (watermarks, platform links, attribution)
# that are never useful in a generation prompt.
# ---------------------------------------------------------------------------

_META_TAGS = {
    # Generic attribution
    "artist name", "artist username", "artist credit",
    "web address", "website", "url", "link", "hyperlink",
    "watermark", "signature", "logo",
    "copyright", "registered trademark", "trademark", "all rights reserved",
    "qr code", "barcode",
    # Platform handles (WD14 tags these when visible in the image)
    "patreon username", "patreon logo", "patreon",
    "twitter username", "twitter logo", "twitter",
    "gumroad username", "gumroad",
    "deviantart username", "deviantart",
    "instagram username", "instagram",
    "pixiv username", "pixiv id", "pixiv",
    "booth username", "booth",
    "ci-en username", "ci-en",
    "youtube username", "youtube",
    "twitch username", "twitch",
    "facebook username", "facebook",
    "tumblr username", "tumblr",
    "reddit username", "reddit",
    "bluesky username", "bluesky",
    "artstation username", "artstation",
    "skeb username", "skeb",
    "fanbox username", "fanbox",
    "ko-fi username", "ko-fi",
    "subscribestar username", "subscribestar",
    "onlyfans username", "onlyfans",
    "fansly username", "fansly",
    "linktree username", "linktree",
    "discord username", "discord server", "discord",
    "mastodon username", "mastodon",
    "telegram username", "telegram",
    "tiktok username", "tiktok",
    "snapchat username", "snapchat",
    "weibo username", "weibo",
    "niconico username", "niconico",
    "misskey username", "misskey",
    "threads username", "threads",
    "x username", "x.com",
    # Character attribution
    "borrowed character",
    "original character",
    "fan character",
    "character name",
    # Meta genre / quality flags
    "uncensored", "censored", "mosaic censoring",
    "ai generated", "ai-generated",
    "low quality", "high quality", "best quality",
    "normal quality", "worst quality", "jpeg artifacts",
    "scan", "screencap", "official art", "album cover",
}

# Word-level meta matching — catches compound tags like
# "patreon_username", "gumroad_logo", "pixiv_id", etc.
_META_WORDS = frozenset({
    "username", "logo", "watermark", "signature",
    "copyright", "trademark",
    "patreon", "gumroad", "deviantart", "instagram",
    "pixiv", "artstation", "fanbox", "skeb",
    "twitter", "twitch", "youtube", "tumblr",
    "bluesky", "ci-en",
    "subscribestar", "onlyfans", "fansly", "linktree",
    "discord", "mastodon", "telegram", "tiktok",
    "snapchat", "weibo", "niconico", "misskey",
})

# Overlay text / visible-text WD14 tags — filtered under overlay_text toggle.
# These describe text, signs, and speech elements visible IN the image.
_OVERLAY_TEXT_TAGS = {
    "text", "english text", "japanese text", "chinese text", "korean text",
    "arabic text", "latin text", "roman numerals", "handwritten text",
    "printed text", "text focus", "text only", "text on image",
    "speech bubble", "thought bubble", "dialogue box", "text box",
    "caption", "subtitle", "subtitles", "credits", "title",
    "sign", "street sign", "neon sign", "neon lights",
    "billboard", "poster", "banner", "label", "price tag",
    "newspaper", "book text", "letter", "note",
}

_OVERLAY_TEXT_WORDS = frozenset({
    "subtitle", "subtitles",
})

_SUBJECT_TAGS = frozenset({
    # WD14 character-count tags
    "1girl", "2girls", "3girls", "4girls", "5girls", "6+girls", "multiple girls",
    "1boy", "2boys", "3boys", "4boys", "5boys", "6+boys", "multiple boys",
    "1other", "2others", "3others", "multiple others",
    # Grouping descriptors
    "solo", "duo", "trio", "group", "crowd", "pair", "couple",
    "everyone", "all characters",
    # Florence2 / NL subject words that might leak through as tags
    "group photo", "group shot", "group portrait",
})


def _tag_excluded_by_toggles(tag_norm: str, toggles: dict) -> bool:
    # Normalise hyphens → spaces once for all word-level checks below.
    # "dark-skinned_female" → "dark skinned female" → ["dark","skinned","female"]
    words = tag_norm.replace("-", " ").split()

    # Meta / attribution tags are always stripped — never useful in a prompt.
    if tag_norm in _META_TAGS:
        return True
    if any(w in _META_WORDS for w in words):
        return True
    # User-defined always-filter words (no toggle required).
    if any(w in _USER_ALWAYS_WORDS for w in words):
        return True
    # Character source / franchise disambiguation: "katarina (league of legends)",
    # "yoruichi (bleach)", "2b (nier:automata)", etc.
    # WD14 tags the character+source pair as "name_(franchise)".
    # After normalise() the underscore becomes a space, giving "name (franchise)".
    # Any tag ending with (...) from tagger output is always source meta — never
    # useful in a generation prompt.
    if re.search(r'\([^)]+\)\s*$', tag_norm):
        return True

    # Subject/composition tags are never stripped by any toggle.
    if tag_norm in _SUBJECT_TAGS:
        return False
    if toggles.get("character_traits"):
        if tag_norm in _CHAR_TRAITS_TAGS:
            return True
        # Word-level: catches "dark_skinned", "dark-skinned_female",
        # "dark_nipples", "body_freckles", "cum_on_breasts", etc.
        if any(w in _CHAR_TRAIT_WORDS for w in words):
            return True
        if any(w in _EXPLICIT_WORDS for w in words):
            return True
        if any(w in _USER_CHAR_WORDS for w in words):
            return True
    if toggles.get("expressions") and tag_norm in _SORTER_EXPRESSION_TAGS:
        return True
    if toggles.get("fantasy_traits"):
        if tag_norm in _FANTASY_TAGS:
            return True
        # Word-level: catches "skin-covered_horns", "red_tail", "demon_girl",
        # "red_oni", "borrowed_character" stays clean (no fantasy words).
        if any(w in _FANTASY_WORDS for w in tag_norm.split()):
            return True
        if any(w in _USER_FANTASY_WORDS for w in tag_norm.split()):
            return True
    if toggles.get("clothes"):
        if tag_norm in _CLOTHES_TAGS:
            return True
        if any(w in _CLOTHES_WORDS for w in tag_norm.split()):
            return True
    if toggles.get("furry"):
        if tag_norm in _FURRY_TAGS:
            return True
        # Word-level: catches "body_fur", "white_fur", "two-tone_fur",
        # "animal_ear_fluff" (→ "fluff"), "wolf_girl" (→ "wolf"? no,
        # handled by set), "furry_female" (→ "furry"), etc.
        if any(w in _FURRY_WORDS for w in tag_norm.replace("-", " ").split()):
            return True
    if toggles.get("overlay_text"):
        if tag_norm in _OVERLAY_TEXT_TAGS:
            return True
        if any(w in _OVERLAY_TEXT_WORDS for w in words):
            return True
        if any(w in _USER_OVERLAY_WORDS for w in words):
            return True
    return False


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class FrogTagFilter:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "exclude": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": (
                        "Tags / phrases to remove before the string reaches the prompt.\n"
                        "One entry per line — or comma-separated on one line.\n\n"
                        "Wildcards supported:\n"
                        "  rating:*      removes every tag starting with 'rating:'\n"
                        "  *background*  removes any tag containing 'background'\n"
                        "  nude          removes only the exact tag 'nude'\n\n"
                        "Matching is case-insensitive; underscores == spaces."
                    ),
                }),
            },
            "optional": {
                "florence2": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Natural-language caption from Florence2. "
                        "Character-trait and clothing phrases are stripped "
                        "from within the sentence before it is passed through."
                    ),
                }),
                "wd14": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Gelbooru-style comma-separated tags from WD14. Placed after Florence2.",
                }),
                "toggle_pack": ("TAG_FILTER_TOGGLES", {
                    "tooltip": "Optional 🐸 Filter Toggle Pack — enables category-level filtering.",
                }),
            },
        }

    RETURN_TYPES  = ("STRING", "STRING", "INT")
    RETURN_NAMES  = ("filtered", "removed", "removed_count")
    FUNCTION      = "filter_tags"
    CATEGORY      = "🐸 Node Pack/Utility"

    def filter_tags(self, exclude: str,
                    florence2: str = "", wd14: str = "",
                    toggle_pack: dict | None = None):

        patterns = _parse_exclude_patterns(exclude)
        toggles  = toggle_pack or {}
        active   = any(toggles.values())

        nl_removed: list[str] = []

        # Florence2: NL phrase stripping first, then tag-filter residue.
        # _NL_META_PATTERNS (watermarks, disclaimers) always run regardless of
        # toggle state.  Toggle-based patterns (character_traits, clothes, etc.)
        # only run when at least one toggle is active.
        fl_text = florence2.strip() if florence2 else ""
        if fl_text:
            fl_text, nl_removed = _strip_nl_phrases(fl_text, toggles)
        fl_tokens = _split_tags(fl_text)

        # WD14: direct tag-level filtering
        wd_tokens = _split_tags(wd14 or "")

        all_tokens = fl_tokens + wd_tokens

        if not all_tokens and not nl_removed:
            return ("", "", 0)

        # Note: do NOT short-circuit here when `not active`.  _META_TAGS and the
        # source-disambiguation check in _tag_excluded_by_toggles always run
        # regardless of toggle state, so we must always process the token list.

        kept:        list[str] = []
        tag_removed: list[str] = []

        for tag in all_tokens:
            tag_norm = _normalise(tag)
            if (_tag_excluded_by_pattern(tag_norm, patterns) or
                    _tag_excluded_by_toggles(tag_norm, toggles)):
                tag_removed.append(tag)
            else:
                kept.append(tag)

        all_removed = nl_removed + tag_removed
        return (", ".join(kept), ", ".join(all_removed), len(all_removed))


# ---------------------------------------------------------------------------
# Vocabulary Extender node
# ---------------------------------------------------------------------------

def _vocab_widget_default(key: str) -> str:
    """Load saved words for one category and return as a newline-joined string."""
    path = _vocab_path()
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return "\n".join(data.get(key, []))
    except Exception:
        return ""


class FrogVocabExtender:
    """
    Permanently extend the 🐸 Tag Filter's built-in vocabulary.

    Type words or phrases — one per line (or comma-separated).
    On execution the list is saved to data/vocab_extensions.json and
    loaded immediately, so subsequent filter runs see the new words
    without a ComfyUI restart.

    On the next ComfyUI startup the same file is loaded automatically,
    so your additions persist across sessions even if this node is not
    in the active workflow.

    Matching is word-level (same as the built-in sets):
      • Adding "kitew"  filters any tag containing the word "kitew".
      • Adding "elf"    filters "dark elf", "forest elf", "half elf", etc.

    Categories mirror the Filter Toggle Pack toggles:
      • Always         — filtered unconditionally, no toggle required.
                         Use for artist names, specific handles, proprietary
                         watermarks (e.g. KITEW, NYUUNZ).
      • Fantasy        — filtered when fantasy_traits toggle is ON.
      • Character Traits — filtered when character_traits toggle is ON.
      • Overlay Text   — filtered when overlay_text toggle is ON.
    """

    DESCRIPTION = (
        "Permanently extend the 🐸 Tag Filter's built-in word lists. "
        "Entries are saved to data/vocab_extensions.json and reloaded on "
        "every ComfyUI start — no restart needed after adding words."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "always": ("STRING", {
                    "multiline": True,
                    "default": _vocab_widget_default("always"),
                    "tooltip": (
                        "Words filtered unconditionally — no toggle required.\n"
                        "Use for artist handles, specific watermarks, or any\n"
                        "tag that should ALWAYS be removed.\n"
                        "Example:  kitew\n"
                        "          nyuunz\n"
                        "          misamart"
                    ),
                }),
                "fantasy": ("STRING", {
                    "multiline": True,
                    "default": _vocab_widget_default("fantasy"),
                    "tooltip": (
                        "Words filtered when the fantasy_traits toggle is ON.\n"
                        "Word-level: 'elf' also catches 'dark elf', 'forest elf'.\n"
                        "Example:  dryad\n"
                        "          sphinx\n"
                        "          centaur"
                    ),
                }),
                "character_traits": ("STRING", {
                    "multiline": True,
                    "default": _vocab_widget_default("character_traits"),
                    "tooltip": (
                        "Words filtered when the character_traits toggle is ON.\n"
                        "Word-level: 'breasts' also catches 'large breasts', etc.\n"
                        "Example:  abs\n"
                        "          muscular"
                    ),
                }),
                "overlay_text": ("STRING", {
                    "multiline": True,
                    "default": _vocab_widget_default("overlay_text"),
                    "tooltip": (
                        "Words filtered when the overlay_text toggle is ON.\n"
                        "Use for text / sign / caption descriptors not already\n"
                        "in the built-in list.\n"
                        "Example:  graffiti\n"
                        "          chalk writing"
                    ),
                }),
            },
        }

    RETURN_TYPES  = ()
    FUNCTION      = "apply"
    CATEGORY      = "🐸 Node Pack/Utility"
    OUTPUT_NODE   = True

    def apply(self, always: str, fantasy: str,
              character_traits: str, overlay_text: str):

        parsed_always    = _parse_vocab_text(always)
        parsed_fantasy   = _parse_vocab_text(fantasy)
        parsed_char      = _parse_vocab_text(character_traits)
        parsed_overlay   = _parse_vocab_text(overlay_text)

        _save_user_vocab(parsed_always, parsed_fantasy, parsed_char, parsed_overlay)

        total = len(parsed_always) + len(parsed_fantasy) + len(parsed_char) + len(parsed_overlay)
        print(
            f"[Frog Vocab Extender] saved -- "
            f"always:{len(parsed_always)}  fantasy:{len(parsed_fantasy)}  "
            f"char:{len(parsed_char)}  overlay:{len(parsed_overlay)}  "
            f"total:{total}"
        )
        return {}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "FrogTagFilter":     FrogTagFilter,
    "FrogVocabExtender": FrogVocabExtender,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "FrogTagFilter":     "🐸 Tag Filter",
    "FrogVocabExtender": "🐸 Vocab Extender",
}
