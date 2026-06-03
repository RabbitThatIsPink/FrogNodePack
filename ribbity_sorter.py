r"""
🐸-Pack — Ribbity Sorter
Single input, single output.
Output order: Quality → Subject → Character → Series → Artist → General
"""

import re

# ── Quality ───────────────────────────────────────────────────────────────────
_QUALITY_TAGS = {
    "masterpiece", "best quality", "very aesthetic", "aesthetic",
    "high quality", "highres", "ultra highres", "absurdres",
    "score_9", "score_8", "score_7", "score_6", "score_5", "score_4",
    "score_9_up", "score_8_up", "score_7_up", "score_6_up",
    "score 9", "score 8", "score 7", "score 6", "score 5", "score 4",
    "rating_safe", "rating_questionable", "rating_explicit", "rating_sensitive",
    "safe", "explicit", "sensitive", "questionable",
    "source_anime", "source_manga", "source_cartoon", "source_furry", "source_pony",
    "newest", "recent", "old", "early",
    "amazing quality", "great quality", "normal quality", "low quality", "worst quality",
    "ultra detailed", "highly detailed", "detailed", "intricate details",
    "sharp focus", "8k", "4k", "hd", "uhd",
    "e621", "e621 score", "pony", "pony diffusion",
    "source_western", "source_game_cg",
    "12k", "2k", "6k", "10k",
    "realistic", "semi-realistic", "hyperdetailed",
    "vibrant colors", "vivid colors", "rich colors",
    "polished", "polished rendering", "polished artwork",
    "professional", "professional quality", "professional art",
    "perfect anatomy", "anatomically correct",
    "official art", "promotional art",
    "trending on artstation", "award winning",
}
_QUALITY_YEAR_RE = re.compile(r"^(19|20)\d{2}$")

# ── Subject ───────────────────────────────────────────────────────────────────
_SUBJECT_TAGS = {
    "solo", "solo focus", "1girl", "1boy", "1other",
    "2girls", "3girls", "4girls", "5girls", "6+girls", "multiple girls", "multiple_girls",
    "2boys", "3boys", "4boys", "5boys", "6+boys", "multiple boys", "multiple_boys",
    "2others", "3others", "4others", "5others", "6+others", "multiple others", "multiple_others",
    "group", "couple", "trio", "duo", "zero girls", "no humans",
    "1girl 1boy", "1boy 1girl", "1girl 2boys", "2girls 1boy",
}

# ── Known character names → Character bucket ──────────────────────────────────
# Full names take priority over first names to avoid false matches.
_CHARACTER_NAMES = {
    # Disney
    "ariel", "belle", "cinderella", "aurora", "snow white", "rapunzel",
    "tiana", "merida", "moana", "raya", "asha", "elena",
    "anna", "elsa", "olaf", "kristoff",
    "mulan", "jasmine", "pocahontas", "esmeralda",
    "nala", "kiara", "kida",
    "tinker bell", "tinkerbell",
    "wendy darling", "wendy",
    "alice",
    "maid marian",
    "vanellope", "vanellope von schweetz",
    "judy hopps", "nick wilde",
    "mirabel", "luisa", "isabela", "camilo",
    "asha",
    # Disney (male)
    "hercules", "aladdin", "simba", "bambi", "pinocchio",
    "tarzan", "quasimodo", "naveen",
    # Pixar
    "jessie", "woody", "buzz lightyear", "buzz",
    "elastigirl", "violet parr", "dash parr",
    "merida",
    "joy", "sadness", "anger", "disgust", "fear", "bing bong",
    "riley andersen", "riley",
    "nemo", "dory", "marlin",
    "remy", "linguini",
    "wall-e", "eve",
    "boo", "sulley", "mike wazowski",
    "luca paguro", "luca", "alberto scorfano", "alberto",
    "luz noceda", "luz",
    # Kim Possible
    "kim possible", "kim",
    "shego",
    "ron stoppable", "ron",
    # Gravity Falls
    "dipper pines", "dipper",
    "mabel pines", "mabel",
    "pacifica northwest", "pacifica",
    "wendy corduroy",
    # Star vs the Forces of Evil
    "star butterfly", "star",
    "marco diaz", "marco",
    # The Owl House
    "luz noceda",
    "amity blight", "amity",
    "eda clawthorne", "eda",
    "willow park", "willow",
    "gus porter", "gus",
    # Amphibia
    "anne boonchuy", "anne",
    "sasha waybright", "sasha",
    "marcy wu", "marcy",
    # Avatar
    "katara", "aang", "zuko", "sokka", "toph",
    "korra", "asami sato", "asami", "mako", "bolin",
    # My Little Pony
    "twilight sparkle", "rainbow dash", "fluttershy",
    "rarity", "applejack", "pinkie pie",
    "princess celestia", "princess luna", "princess cadance",
    "starlight glimmer", "sunset shimmer", "trixie",
    # Pokemon
    "pikachu", "eevee", "mewtwo", "mew", "charizard",
    "misty", "ash ketchum", "ash", "brock",
    "serena", "dawn", "may",
    "jessie", "james",
    # Naruto
    "naruto uzumaki", "naruto",
    "sakura haruno", "sakura",
    "sasuke uchiha", "sasuke",
    "hinata hyuga", "hinata",
    "kakashi hatake", "kakashi",
    "tsunade", "orochimaru", "itachi",
    "temari", "ino yamanaka", "ino",
    # Bleach
    "ichigo kurosaki", "ichigo",
    "rukia kuchiki", "rukia",
    "orihime inoue", "orihime",
    "yoruichi shihouin", "yoruichi",
    "rangiku matsumoto", "rangiku",
    "nelliel tu odelschwanck", "nel",
    # One Piece
    "nami", "nico robin", "robin",
    "monkey d luffy", "luffy",
    "roronoa zoro", "zoro",
    "boa hancock", "hancock",
    "nefertari vivi", "vivi",
    # Fairy Tail
    "erza scarlet", "erza",
    "lucy heartfilia", "lucy",
    "natsu dragneel", "natsu",
    "wendy marvell",
    "mirajane strauss", "mirajane",
    "cana alberona", "cana",
    # Attack on Titan
    "mikasa ackerman", "mikasa",
    "historia reiss", "historia",
    "annie leonhart", "annie",
    "ymir",
    "eren yeager", "eren",
    "levi ackerman", "levi",
    # Re:Zero
    "emilia", "rem", "ram",
    "beatrice",
    # Sword Art Online
    "asuna yuuki", "asuna",
    "sinon", "leafa", "silica",
    "kirito",
    # No Game No Life
    "shiro", "sora",
    "stephanie dola", "stephanie",
    # Overlord
    "albedo", "shalltear bloodfallen", "shalltear",
    "narberal gamma", "narberal",
    # KonoSuba
    "aqua", "megumin", "darkness",
    "kazuma satou", "kazuma",
    # Fate series
    "saber", "rin tohsaka", "rin",
    "sakura matou", "sakura",
    "rider", "caster", "archer", "lancer", "berserker", "assassin",
    "artoria pendragon", "artoria",
    "tamamo no mae", "tamamo",
    "scathach",
    "nero claudius", "nero",
    "jeanne d'arc", "jeanne",
    # Touhou
    "reimu hakurei", "reimu",
    "marisa kirisame", "marisa",
    "sakuya izayoi", "sakuya",
    "remilia scarlet", "remilia",
    "flandre scarlet", "flandre",
    "cirno", "chen", "alice margatroid",
    "patchouli knowledge", "patchouli",
    "youmu konpaku", "youmu",
    "yuyuko saigyouji", "yuyuko",
    "yukari yakumo", "yukari",
    "reisen udongein inaba", "reisen",
    "eirin yagokoro", "eirin",
    "kaguya houraisan", "kaguya",
    "mokou fujiwara", "mokou",
    "sanae kochiya", "sanae",
    "nitori kawashiro", "nitori",
    "koishi komeiji", "koishi",
    "satori komeiji", "satori",
    "aya shameimaru", "aya",
    "tenshi hinanawi", "tenshi",
    # Vocaloid
    "hatsune miku", "miku",
    "kagamine rin", "rin",
    "kagamine len", "len",
    "megurine luka", "luka",
    "kaito", "meiko",
    # Street Fighter
    "chun-li", "chun li",
    "cammy white", "cammy",
    "juri han", "juri",
    "sakura kasugano",
    # Mortal Kombat
    "kitana", "mileena", "jade", "sonya blade", "sonya",
    "cassie cage", "cassie",
    # League of Legends
    "jinx", "vi", "caitlyn",
    "ahri", "lux", "miss fortune",
    "ashe", "sivir", "nidalee",
    "sona", "soraka", "janna",
    "kaisa", "kai'sa",
    "seraphine", "akali", "evelynn", "bea",
    # Genshin Impact
    "lumine", "aether",
    "amber", "lisa", "jean",
    "fischl", "keqing", "ganyu",
    "hu tao", "xiao", "zhongli",
    "raiden shogun", "raiden", "ei",
    "kokomi", "yoimiya", "ayaka",
    "shenhe", "yae miko", "yae",
    "nilou", "nahida", "cyno",
    "arlecchino", "furina", "navia",
    "chiori", "citlali",
    # Honkai Star Rail
    "stelle", "trailblazer",
    "kafka", "blade", "silver wolf",
    "himeko", "welt",
    "bronya", "seele",
    "fu xuan", "fu xuan",
    "robin", "sparkle", "acheron",
    "firefly", "ruan mei",
    # Blue Archive
    "arona", "plana",
    "aris", "noa", "yuzu",
    "hoshino", "shiroko", "serika",
    # Azur Lane
    "enterprise", "belfast",
    "illustrious", "le malin",
    "prinz eugen", "tirpitz",
    # Nikke
    "rapi", "anis", "neon", "yuni",
    "privaty", "modernia", "scarlet",
    # Original / misc
    "zero two", "zero-two",
    "ichigo",
    "nino nakano", "miku nakano",
    "itsuki nakano", "yotsuba nakano", "ichika nakano",
    "raphtalia",
    "violet evergarden", "violet",
    "nezuko kamado", "nezuko",
    "tanjiro kamado", "tanjiro",
    "mitsuri kanroji", "mitsuri",
    "shinobu kocho", "shinobu",
    "power", "makima", "himeno",
    "nobara kugisaki", "nobara",
    "maki zenin", "maki",
    "yor forger", "yor",
    "anya forger", "anya",
    "fiona frost", "fiona",
    "frieren",
    "fern",
    "chika fujiwara", "chika",
    "kaguya shinomiya", "kaguya",
    "ai hayasaka", "hayasaka",
    "nagatoro",
    "uzaki hana", "uzaki",
    "android 18", "android 21",
    "bulma",
    "launch",
    "nami",
}

# ── Known series/franchise names → Series bucket ──────────────────────────────
_SERIES_NAMES = {
    # Disney / Pixar
    "disney", "pixar", "studio ghibli", "ghibli",
    "the little mermaid", "beauty and the beast", "cinderella",
    "sleeping beauty", "snow white", "tangled", "brave",
    "moana", "frozen", "encanto", "raya and the last dragon",
    "the lion king", "aladdin", "mulan", "hercules",
    "the incredibles", "toy story", "finding nemo", "finding dory",
    "monsters inc", "monsters university", "up", "coco",
    "soul", "luca", "turning red", "elemental",
    "wreck-it ralph", "zootopia", "inside out",
    "gravity falls", "star vs the forces of evil",
    "the owl house", "amphibia",
    "ducktales", "darkwing duck", "chip n dale",
    # Anime
    "naruto", "shippuden", "boruto",
    "bleach", "one piece", "fairy tail",
    "attack on titan", "shingeki no kyojin",
    "sword art online", "sao",
    "re:zero", "rezero",
    "no game no life",
    "overlord", "konosuba",
    "fate", "fate stay night", "fate grand order", "fgo",
    "touhou", "touhou project",
    "vocaloid",
    "dragon ball", "dragon ball z", "dragon ball super",
    "fullmetal alchemist", "fma",
    "hunter x hunter", "hxh",
    "demon slayer", "kimetsu no yaiba",
    "jujutsu kaisen", "jjk",
    "chainsaw man",
    "spy x family",
    "my hero academia", "boku no hero academia", "bnha", "mha",
    "black clover",
    "the quintessential quintuplets", "quintessential quintuplets",
    "kaguya-sama love is war", "kaguya sama",
    "don't toy with me miss nagatoro", "nagatoro",
    "uzaki-chan wants to hang out", "uzaki chan",
    "oshi no ko",
    "vinland saga",
    "frieren beyond journey's end", "sousou no frieren",
    "bocchi the rock",
    "lycoris recoil",
    "blue lock",
    "trigun", "cowboy bebop", "evangelion", "neon genesis evangelion",
    "gurren lagann", "kill la kill", "darling in the franxx",
    "steins gate", "code geass", "death note",
    "re:zero", "sword art online",
    "made in abyss",
    "violet evergarden",
    "a silent voice", "your name", "weathering with you",
    # Games
    "pokemon", "pokémon",
    "street fighter",
    "mortal kombat",
    "league of legends", "lol",
    "genshin impact", "genshin",
    "honkai star rail", "star rail",
    "honkai impact", "honkai impact 3rd",
    "blue archive",
    "azur lane",
    "nikke", "goddess of victory nikke",
    "fire emblem",
    "persona", "persona 5", "persona 4", "persona 3",
    "final fantasy", "ff7", "ff14",
    "nier automata", "nier",
    "dota 2", "dota",
    "overwatch",
    "apex legends",
    "valorant",
    "arknights",
    "girls frontline",
    "punishing gray raven",
    "wuthering waves",
    "zenless zone zero", "zzz",
    # Western
    "avatar the last airbender", "avatar",
    "the legend of korra", "korra",
    "my little pony", "mlp", "friendship is magic",
    "steven universe",
    "she-ra", "she ra",
    "arcane",
    "marvel", "dc",
    "spider-man", "batman", "wonder woman", "supergirl",
    "x-men",
}

# ── Artist names & style terms ────────────────────────────────────────────────
_ARTIST_STYLE_NAMES = [
    "arcane style", "fortiche", "fortiche studio",
    "ghibli style", "pixar style", "pixar 3d",
    "disney 2d", "disney style", "classic disney",
    "makoto shinkai", "shinkai", "kyoto animation", "kyoani",
    "mappa", "madhouse", "trigger",
    "spider-verse", "into the spider verse",
    "borderlands style",
    "persona style", "atlus",
    "wlop", "wlop style",
    "shigenori soejima", "yoshitaka amano", "akihiko yoshida",
    "kim jung gi", "stjepan sejic", "stjepan šejić", "sejic",
    "adam hughes", "alphonse mucha", "mucha", "egon schiele",
    "van gogh", "van gogh style", "monet", "renoir", "sargent",
    "rembrandt", "caravaggio", "bouguereau", "waterhouse",
    "mike mignola", "mignola", "frank miller", "moebius",
    "ilya kuvshinov", "ross tran", "loish", "sakimichan",
    "artgerm", "artgerm style", "greg rutkowski", "beeple",
]

_STYLE_TERMS = [
    "oil painting", "oil on canvas", "watercolor", "watercolour",
    "watercolor painting", "watercolour painting", "gouache", "gouache painting",
    "acrylic", "acrylic painting", "ink wash", "sumi-e",
    "pencil sketch", "pencil drawing", "graphite", "graphite drawing",
    "charcoal", "charcoal sketch", "charcoal drawing",
    "pastel", "soft pastel", "oil pastel",
    "marker rendering", "copic markers", "marker drawing",
    "ballpoint pen", "pen and ink", "digital painting",
    "digital illustration", "digital art", "mixed media", "traditional media",
    "cel shading", "cel-shaded", "cel shaded",
    "hatching", "cross hatching", "cross-hatching",
    "halftone", "halftone dots", "stippling", "pointillism",
    "linework", "line art", "clean lineart", "painterly",
    "film grain", "35mm film",
    "impressionist", "expressionist", "art nouveau", "art deco",
    "romanticism", "baroque", "renaissance",
    "pop art", "surrealism", "minimalism",
    "comic book", "comic style", "graphic novel",
    "manga", "manga style", "anime", "anime style", "anime illustration",
    "cinematic", "cinematic lighting", "photorealistic", "photorealism",
    "pixel art", "pixelated", "8bit", "16bit",
    "vector art", "concept art", "fantasy art",
]

# ── Character physical descriptors ───────────────────────────────────────────
_HAIR_COLORS = {
    "orange hair", "red hair", "blue hair", "green hair", "purple hair",
    "pink hair", "blonde hair", "black hair", "white hair", "silver hair",
    "brown hair", "grey hair", "gray hair", "dark hair", "light hair",
    "multicolored hair", "gradient hair", "streaked hair", "cream hair",
    "platinum hair", "golden hair", "teal hair", "cyan hair", "aqua hair",
    "lavender hair", "mint hair", "coral hair", "dark brown hair",
    "light brown hair", "dirty blonde", "strawberry blonde", "ash blonde",
    "two-tone hair", "ombre hair", "dyed hair", "dyed tips",
}
_HAIR_STYLES = {
    "long hair", "short hair", "medium hair", "very long hair", "extra long hair",
    "twin tails", "twintails", "ponytail", "pigtails", "braids", "braid",
    "bun", "side bun", "double bun", "bob cut", "pixie cut",
    "straight hair", "wavy hair", "curly hair", "messy hair", "disheveled hair",
    "ahoge", "drill hair", "undercut", "bangs", "side swept", "swept bangs",
    "high ponytail", "low ponytail", "half up", "french braid", "side ponytail",
    "hair down", "hair up", "loose hair", "tied hair",
    "low twintails", "high twintails", "side braid", "twin braids",
    "hime cut", "wolf cut", "layered hair", "shoulder length hair",
    "hair over one eye", "hair over eyes", "blunt bangs", "crossed bangs",
    "hair bun", "high bun", "low bun", "messy bun",
    "hair ornament", "hair ribbon", "hair bow", "hair clip", "hair tie",
    "hair band", "hairband", "hairpin", "scrunchie", "hair scrunchie",
}
_EYE_DESCRIPTORS = {
    "green eyes", "blue eyes", "red eyes", "purple eyes", "orange eyes",
    "yellow eyes", "brown eyes", "black eyes", "grey eyes", "gray eyes",
    "pink eyes", "heterochromia", "teal eyes", "cyan eyes", "amber eyes",
    "aqua eyes", "gold eyes", "silver eyes", "white eyes", "dark eyes",
    "glowing eyes", "slit pupils", "vertical pupils", "star-shaped pupils",
    "heart-shaped pupils", "empty eyes", "hollow eyes", "half-closed eyes",
    "closed eyes", "one eye closed", "wink", "wide eyes", "narrowed eyes",
    "colored sclera", "yellow sclera", "red sclera", "black sclera",
    "multicolored eyes", "gradient eyes", "ringed eyes",
}
_SKIN_DESCRIPTORS = {
    "grey skin", "green skin", "dark skin", "pale skin", "tan skin",
    "light skin", "brown skin", "blue skin", "purple skin", "pink skin",
    "red skin", "yellow skin", "white skin", "ivory skin", "ebony skin",
    "colored skin", "multicolored skin", "demon skin", "monster skin",
    "scales", "fur", "feathers",
}
_BODY_DESCRIPTORS = {
    "medium breasts", "small breasts", "large breasts", "flat chest",
    "big breasts", "huge breasts", "gigantic breasts", "petite", "slim",
    "athletic build", "curvy", "muscular", "wide hips", "narrow waist",
    "hourglass figure", "slender", "chubby", "plump", "thick thighs",
    "long legs", "pointy ears", "elf ears", "cat ears", "animal ears",
    "horns", "demon horns", "tail", "wings", "angel wings", "demon wings",
    "halo", "oni horns", "wolf ears", "fox ears", "bunny ears", "rabbit ears",
    "dragon horns", "dragon tail", "cat tail", "fox tail", "wolf tail",
}
_EXPRESSION_TAGS = {
    "smile", "smiling", "grin", "grinning", "laugh", "laughing",
    "blush", "blushing", "frown", "frowning", "scowl", "glare",
    "surprised", "shocked", "embarrassed", "shy", "nervous",
    "angry", "furious", "sad", "crying", "tears", "teary eyes",
    "happy", "excited", "confident", "seductive", "flirty",
    "serious", "stoic", "expressionless", "neutral expression",
    "open mouth", "closed mouth", "parted lips", "tongue out",
    "pout", "pouting", "smirk",
}

_CHARACTER_TAGS = (
    _HAIR_COLORS | _HAIR_STYLES | _EYE_DESCRIPTORS |
    _SKIN_DESCRIPTORS | _BODY_DESCRIPTORS | _EXPRESSION_TAGS
)

# ── General vocab ─────────────────────────────────────────────────────────────
_GENERAL_TAGS = {
    "indoors", "outdoors", "nature", "city", "urban", "forest", "beach",
    "school", "bedroom", "kitchen", "bathroom", "park", "garden",
    "day", "night", "sunset", "sunrise", "dawn", "dusk", "moonlight",
    "sunlight", "overcast", "rain", "snow", "fog", "mist", "cloudy",
    "blue sky", "clear sky", "dramatic sky", "stormy sky",
    "soft lighting", "hard lighting", "rim lighting", "side lighting",
    "backlight", "backlighting", "volumetric lighting", "god rays",
    "dramatic lighting", "moody lighting", "ambient light",
    "sitting", "standing", "lying", "walking", "running", "jumping",
    "looking at viewer", "looking away", "looking back", "looking up",
    "looking down", "from above", "from below", "from side", "from behind",
    "upper body", "lower body", "full body", "close-up", "portrait",
    "profile view", "three-quarter view", "cowboy shot", "bust",
    "dynamic pose", "action pose", "relaxed pose", "crossed arms",
    "arms up", "hands on hips", "leaning forward", "leaning back",
    "dress", "skirt", "pants", "shorts", "jeans", "jacket", "coat",
    "hoodie", "sweater", "shirt", "blouse", "uniform", "school uniform",
    "suit", "bikini", "swimsuit", "lingerie", "underwear",
    "hat", "cap", "glasses", "sunglasses", "mask", "scarf", "gloves",
    "boots", "sneakers", "heels", "shoes", "barefoot",
    "background", "simple background", "white background", "black background",
    "gradient background", "blurry background", "bokeh",
}

# ── Series anchor pattern (e.g. kim possible \(series\)) ──────────────────────
_ANCHOR_PATTERN = re.compile(r'^[a-zA-Z0-9][\w\s\-\'\.]*\s*\([^\)]{2,}\)\s*$')
_ANCHOR_EXCLUDES = {
    "nose", "eyes", "ears", "mouth", "hair", "skin", "face",
    "hands", "feet", "arms", "legs", "body", "chest",
}


def _normalise(tag: str) -> str:
    """Canonical form for duplicate detection: lowercase, stripped, underscores→spaces."""
    return tag.lower().strip().replace("_", " ")


def _split_tags(text: str) -> list[str]:
    """Split on commas/newlines, respecting parenthesis depth."""
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


def _is_subject_tag(tag: str) -> bool:
    return tag.lower().strip().replace("_", " ") in _SUBJECT_TAGS


def _is_anchor_tag(tag: str) -> bool:
    tl = tag.lower().strip()
    if any(tl.startswith(e) for e in _ANCHOR_EXCLUDES):
        return False
    # Normalise Danbooru-style backslash escapes: \( -> (  \) -> )
    normalised = tag.strip().replace(r"\(", "(").replace(r"\)", ")")
    return bool(_ANCHOR_PATTERN.match(normalised))


def _tag_matches_any(tag, vocab_list):
    tl = tag.lower().strip()
    ts = re.sub(r'^(by |@)', '', tl).strip()
    for vocab in vocab_list:
        vl = vocab.lower().strip()
        if tl == vl or ts == vl:
            return True
        if re.search(r'\b' + re.escape(vl) + r'\b', tl):
            return True
    return False


def _detect_category(tag):
    t  = tag.strip()
    tl = t.lower()
    tn = tl.replace("_", " ")

    # Quality
    if tn in _QUALITY_TAGS or tl in _QUALITY_TAGS:
        return "quality"
    if _QUALITY_YEAR_RE.match(tl):
        return "quality"

    # Subject
    if _is_subject_tag(t):
        return "subject"

    # Known character names — before anchor check to avoid bare name collision
    if tn in _CHARACTER_NAMES or tl in _CHARACTER_NAMES:
        return "character"

    # Series anchor e.g. kim possible (series) or kim possible \(series\)
    if _is_anchor_tag(t):
        return "series"

    # Known series names
    if tn in _SERIES_NAMES or tl in _SERIES_NAMES:
        return "series"

    # @ artist or "by name"
    if t.startswith("@") or re.match(r'^by\s+\S', t, re.IGNORECASE):
        return "artist_at"

    # Named artist style
    if _tag_matches_any(t, _ARTIST_STYLE_NAMES):
        return "artist_named"

    # Style / medium
    if _tag_matches_any(t, _STYLE_TERMS):
        return "style"

    # Physical character descriptors
    if tn in _CHARACTER_TAGS or tl in _CHARACTER_TAGS:
        return "character"

    # General
    if tn in _GENERAL_TAGS or tl in _GENERAL_TAGS:
        return "general"
    for gt in _GENERAL_TAGS:
        if len(gt) > 5 and gt in tn:
            return "general"

    return "general"


# ── Node ──────────────────────────────────────────────────────────────────────

class RibbitySorter:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "string_input": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Wired string of tags to sort.",
                }),
            }
        }

    # Output order: Quality → Subject → Character → Series → Artist → General
    RETURN_TYPES  = ("STRING", "STRING")
    RETURN_NAMES  = ("sorted_prompt", "debug")
    FUNCTION      = "sort"
    CATEGORY      = "🐸 Node Pack"

    def sort(self, string_input):

        combined = string_input or ""

        if not combined.strip():
            return ("", "No input provided.")

        tags = _split_tags(combined)

        quality    = []
        subjects   = []
        characters = []
        series     = []
        at_artists = []
        named_art  = []
        styles     = []
        general    = []
        log        = []

        for tag in tags:
            cat = _detect_category(tag)
            if   cat == "quality":      quality.append(tag);    log.append(f"  QUALITY   <- {tag}")
            elif cat == "subject":      subjects.append(tag);   log.append(f"  SUBJECT   <- {tag}")
            elif cat == "character":    characters.append(tag); log.append(f"  CHARACTER <- {tag}")
            elif cat == "series":       series.append(tag);     log.append(f"  SERIES    <- {tag}")
            elif cat == "artist_at":    at_artists.append(tag); log.append(f"  ARTIST(@) <- {tag}")
            elif cat == "artist_named": named_art.append(tag);  log.append(f"  ARTIST    <- {tag}")
            elif cat == "style":        styles.append(tag);     log.append(f"  STYLE     <- {tag}")
            else:                       general.append(tag);    log.append(f"  GENERAL   <- {tag}")

        artists_combined = at_artists + named_art + styles
        buckets = [quality, subjects, characters, series, artists_combined, general]

        # Flatten bucket order, then deduplicate preserving first occurrence.
        ordered: list[str] = []
        for b in buckets:
            ordered.extend(b)
        seen: set[str] = set()
        deduped: list[str] = []
        dupes: list[str] = []
        for tag in ordered:
            key = _normalise(tag)
            if key in seen:
                dupes.append(tag)
            else:
                seen.add(key)
                deduped.append(tag)

        sorted_prompt = ", ".join(deduped) + ", " if deduped else ""

        dupe_note = (f"\nRemoved {len(dupes)} duplicate(s): {', '.join(dupes)}"
                     if dupes else "\nNo duplicates found.")
        debug = (
            f"=== 🐸 SORTER ===\n"
            f"Input: {len(tags)} tag(s)\n"
            f"Quality:{len(quality)} Subject:{len(subjects)} Character:{len(characters)} "
            f"Series:{len(series)} Artist:{len(artists_combined)} General:{len(general)}"
            f"{dupe_note}\n\n"
            "Routing:\n" + "\n".join(log)
        )

        return (sorted_prompt, debug)


NODE_CLASS_MAPPINGS        = {"RibbitySorter": RibbitySorter}
NODE_DISPLAY_NAME_MAPPINGS = {"RibbitySorter": "🐸 Sorter"}
