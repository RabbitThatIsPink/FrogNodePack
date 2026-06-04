"""
Autocomplete Optimization Patch for ComfyUI-Custom-Scripts
===========================================================
Applies three targeted changes to autocomplete.js:

  1. Pre-caches lowercased word keys at load time so the search loop
     doesn't call toLocaleLowerCase() on every word on every keystroke.

  2. Debounces the update trigger (80 ms) so rapid typing fires one
     search for the final typed state instead of one per keystroke.

  3. Rebuilds the cache whenever the word list changes.

A .bak backup is created before any changes are written.
Re-running after a Custom-Scripts update will re-apply cleanly.
"""
import os
import shutil
import sys

MARKER = "// [FrogNodePack-autocomplete-patch]"


def find_target():
    # This script lives in:
    #   custom_nodes/FrogNodePack/Autocomplete Optimization Patch - Custom Scripts/
    # Custom-Scripts lives in:
    #   custom_nodes/ComfyUI-Custom-Scripts/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(
        script_dir, "..", "..",
        "ComfyUI-Custom-Scripts", "web", "js", "common", "autocomplete.js"
    ))


# ---------------------------------------------------------------------------
# Each patch is (description, original_text, replacement_text).
# The original_text must be an exact substring of the unpatched file.
# ---------------------------------------------------------------------------

PATCHES = [

    # ------------------------------------------------------------------
    # 1. Add globalWordsList static property
    # ------------------------------------------------------------------
    (
        "Add globalWordsList static property",
        '\t/** @type {Record<string, AutoCompleteEntry>} */\n\tstatic globalWordsExclLoras = {};',
        '\t/** @type {Record<string, AutoCompleteEntry>} */\n'
        '\tstatic globalWordsExclLoras = {};\n'
        '\t/** @type {Array<{lower: string, wordInfo: AutoCompleteEntry}>} */\n'
        '\tstatic globalWordsList = []; ' + MARKER,
    ),

    # ------------------------------------------------------------------
    # 2. Add wordsList getter (cached lowercase list per instance)
    # ------------------------------------------------------------------
    (
        "Add wordsList getter",
        '\tget words() {\n'
        '\t\treturn this.overrideWords ?? TextAreaAutoComplete.globalWords;\n'
        '\t}\n'
        '\n'
        '\tget separator() {',
        '\tget words() {\n'
        '\t\treturn this.overrideWords ?? TextAreaAutoComplete.globalWords;\n'
        '\t}\n'
        '\n'
        '\tget wordsList() {\n'
        '\t\tif (this.overrideWords) {\n'
        '\t\t\tif (!this._overrideWordsList) {\n'
        '\t\t\t\tthis._overrideWordsList = Object.entries(this.overrideWords)\n'
        '\t\t\t\t\t.map(([key, wordInfo]) => ({ lower: key.toLocaleLowerCase(), wordInfo }));\n'
        '\t\t\t}\n'
        '\t\t\treturn this._overrideWordsList;\n'
        '\t\t}\n'
        '\t\treturn TextAreaAutoComplete.globalWordsList;\n'
        '\t}\n'
        '\n'
        '\tget separator() {',
    ),

    # ------------------------------------------------------------------
    # 3. Replace #getFilteredWords loop with pre-cached version
    # ------------------------------------------------------------------
    (
        "Optimize #getFilteredWords loop",
        '\t\tfor (const word of Object.keys(this.words)) {\n'
        '\t\t\tconst lowerWord = word.toLocaleLowerCase();\n'
        '\t\t\tif (lowerWord === term) {\n'
        '\t\t\t\t// Dont include exact matches\n'
        '\t\t\t\tcontinue;\n'
        '\t\t\t}\n'
        '\n'
        '\t\t\tconst pos = lowerWord.indexOf(term);\n'
        '\t\t\tif (pos === -1) {\n'
        '\t\t\t\t// No match\n'
        '\t\t\t\tcontinue;\n'
        '\t\t\t}\n'
        '\n'
        '\t\t\tconst wordInfo = this.words[word];\n'
        '\t\t\tif (wordInfo.priority) {\n'
        '\t\t\t\tpriorityMatches.push({ pos, wordInfo });\n'
        '\t\t\t} else if (pos) {\n'
        '\t\t\t\tincludesMatches.push({ pos, wordInfo });\n'
        '\t\t\t} else {\n'
        '\t\t\t\tprefixMatches.push({ pos, wordInfo });\n'
        '\t\t\t}\n'
        '\t\t}',
        '\t\tfor (const { lower, wordInfo } of this.wordsList) {\n'
        '\t\t\tif (lower === term) continue;\n'
        '\n'
        '\t\t\tconst pos = lower.indexOf(term);\n'
        '\t\t\tif (pos === -1) continue;\n'
        '\n'
        '\t\t\tif (wordInfo.priority) {\n'
        '\t\t\t\tpriorityMatches.push({ pos, wordInfo });\n'
        '\t\t\t} else if (pos) {\n'
        '\t\t\t\tincludesMatches.push({ pos, wordInfo });\n'
        '\t\t\t} else {\n'
        '\t\t\t\tprefixMatches.push({ pos, wordInfo });\n'
        '\t\t\t}\n'
        '\t\t}',
    ),

    # ------------------------------------------------------------------
    # 4. Debounce #update() — rename body to #doUpdate()
    # ------------------------------------------------------------------
    (
        "Debounce #update()",
        '\t#update() {\n'
        '\t\tlet before = this.helper.getBeforeCursor();',
        '\t#update() {\n'
        '\t\tclearTimeout(this._updateTimer);\n'
        '\t\tthis._updateTimer = setTimeout(() => this.#doUpdate(), 80);\n'
        '\t}\n'
        '\n'
        '\t#doUpdate() {\n'
        '\t\tlet before = this.helper.getBeforeCursor();',
    ),

    # ------------------------------------------------------------------
    # 5. Rebuild globalWordsList at end of updateWords()
    # ------------------------------------------------------------------
    (
        "Rebuild globalWordsList in updateWords()",
        '\t\t} else if (addGlobal) {\n'
        '\t\t\t// Just insert the new words\n'
        '\t\t\tObject.assign(TextAreaAutoComplete.globalWords, words);\n'
        '\t\t}\n'
        '\t}\n'
        '}',
        '\t\t} else if (addGlobal) {\n'
        '\t\t\t// Just insert the new words\n'
        '\t\t\tObject.assign(TextAreaAutoComplete.globalWords, words);\n'
        '\t\t}\n'
        '\n'
        '\t\t// Rebuild the pre-lowercased search cache so #getFilteredWords\n'
        '\t\t// does not call toLocaleLowerCase() on every word every keystroke.\n'
        '\t\tif (addGlobal) {\n'
        '\t\t\tTextAreaAutoComplete.globalWordsList = Object.entries(TextAreaAutoComplete.globalWords)\n'
        '\t\t\t\t.map(([key, wordInfo]) => ({ lower: key.toLocaleLowerCase(), wordInfo }));\n'
        '\t\t}\n'
        '\t}\n'
        '}',
    ),
]


def main():
    print()
    target = find_target()
    print(f"Target : {target}")

    if not os.path.exists(target):
        print()
        print("  ComfyUI-Custom-Scripts not found — nothing to patch.")
        print("  Install Custom-Scripts first, then re-run this script.")
        print()
        input("  Press Enter to close...")
        return

    with open(target, "r", encoding="utf-8") as f:
        content = f.read()

    if MARKER in content:
        print()
        print("  Already patched — nothing to do.")
        print("  If you want to re-patch after a Custom-Scripts update,")
        print("  restore the .bak file first, then run this script again.")
        return

    # Back up before touching anything
    backup = target + ".bak"
    shutil.copy2(target, backup)
    print(f"Backup  : {os.path.basename(backup)}")
    print()

    patched = content
    ok, skipped = [], []

    for desc, original, replacement in PATCHES:
        if original in patched:
            patched = patched.replace(original, replacement, 1)
            ok.append(desc)
            print(f"  [OK]     {desc}")
        else:
            skipped.append(desc)
            print(f"  [SKIP]   {desc}  <-- anchor not found, Custom-Scripts may have changed")

    if not ok:
        print()
        print("  No patches applied. The file structure may have changed.")
        print("  Restore from backup and check for a newer version of this patch.")
        return

    with open(target, "w", encoding="utf-8") as f:
        f.write(patched)

    print()
    if skipped:
        print(f"  Wrote {len(ok)} of {len(PATCHES)} patches.")
        print("  Hard-refresh your browser (Ctrl+Shift+R) to apply.")
        print()
        print("  WARNING: some patches were skipped — autocomplete may still")
        print("  be slow for those sections. Check the SKIP lines above.")
    else:
        print(f"  All {len(ok)} patches applied successfully.")
        print("  Hard-refresh your browser (Ctrl+Shift+R) to apply.")


if __name__ == "__main__":
    main()
    print()
