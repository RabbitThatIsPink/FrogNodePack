/**
 * 🐸 Wildcard Box — autocomplete
 *
 * Type __ anywhere in the text widget to trigger a dropdown of matching
 * wildcard names fetched from /ribbity/wildcards/list.
 *
 * Keyboard:  ↑ / ↓ to move, Enter / Tab to accept, Escape to dismiss.
 * Click:     selects the entry, inserts __name__, and closes the dropdown.
 * Accept:    replaces from the opening __ to the cursor with __name__,
 *            appending a trailing ", " so the next tag can be typed right away.
 */

import { app } from "../../../scripts/app.js";

const NODE_TYPE = "FrogWildcardBox";

// ── Wildcard list cache ───────────────────────────────────────────────────────

let _cache   = null;
let _pending = null;

async function fetchWildcards() {
    if (_cache   !== null) return _cache;
    if (_pending !== null) return _pending;
    _pending = fetch("/ribbity/wildcards/list")
        .then(r => r.json())
        .then(d => { _cache = d.wildcards || []; return _cache; })
        .catch(err => {
            console.warn("[🐸 WildcardBox] Could not load wildcard list:", err);
            _cache = [];
            return _cache;
        });
    return _pending;
}

// Warm the cache as soon as the script loads so the first keystroke is instant.
fetchWildcards();

// ── Dropdown ──────────────────────────────────────────────────────────────────

function attachAutocomplete(inputEl) {
    let dropdown      = null;
    let matches       = [];
    let highlightIdx  = 0;

    // ── helpers ──

    function hide() {
        dropdown?.remove();
        dropdown     = null;
        matches      = [];
        highlightIdx = 0;
    }

    function renderItems() {
        if (!dropdown) return;
        dropdown.innerHTML = "";
        matches.forEach((name, idx) => {
            const row = document.createElement("div");
            row.textContent = `__${name}__`;
            Object.assign(row.style, {
                padding:      "4px 8px",
                cursor:       "pointer",
                borderRadius: "2px",
                background:   idx === highlightIdx ? "#3a7a3a" : "transparent",
            });
            row.addEventListener("mouseenter", () => { highlightIdx = idx; renderItems(); });
            row.addEventListener("mousedown",  e  => { e.preventDefault(); e.stopPropagation(); accept(name); });
            dropdown.appendChild(row);
        });
    }

    function show(newMatches) {
        hide();
        if (!newMatches.length) return;
        matches      = newMatches;
        highlightIdx = 0;

        dropdown = document.createElement("div");
        Object.assign(dropdown.style, {
            position:   "absolute",
            background: "#1e1e1e",
            color:      "#e0e0e0",
            border:     "1px solid #555",
            borderRadius: "4px",
            padding:    "2px",
            maxHeight:  "180px",
            overflowY:  "auto",
            zIndex:     "99999",
            fontFamily: "monospace",
            fontSize:   "12px",
            minWidth:   "200px",
            boxShadow:  "0 4px 12px rgba(0,0,0,0.7)",
            top:        (inputEl.offsetTop + inputEl.offsetHeight + 4) + "px",
            left:       inputEl.offsetLeft + "px",
            width:      inputEl.offsetWidth + "px",
        });

        renderItems();
        const parent = inputEl.parentElement || document.body;
        parent.style.position = "relative";
        parent.appendChild(dropdown);
    }

    // ── accept ──

    function accept(name) {
        const val    = inputEl.value;
        const cursor = inputEl.selectionStart ?? val.length;
        const before = val.substring(0, cursor);
        const after  = val.substring(cursor);

        const triggerIdx = before.lastIndexOf("__");
        if (triggerIdx === -1) { hide(); return; }

        // Replace from the opening __ through the cursor with __name__,
        const inserted  = `__${name}__, `;
        const newValue  = val.substring(0, triggerIdx) + inserted + after;
        const newCursor = triggerIdx + inserted.length;

        inputEl.value = newValue;
        inputEl.setSelectionRange(newCursor, newCursor);
        inputEl.dispatchEvent(new Event("input",  { bubbles: true }));
        inputEl.dispatchEvent(new Event("change", { bubbles: true }));

        hide();
        inputEl.focus();
    }

    // ── check on every keystroke ──

    async function check() {
        const val      = inputEl.value;
        const cursor   = inputEl.selectionStart ?? val.length;
        const before   = val.substring(0, cursor);
        const lastOpen = before.lastIndexOf("__");

        if (lastOpen === -1)                          { hide(); return; }

        const partial = before.substring(lastOpen + 2);
        if (partial.includes("__"))                  { hide(); return; } // already closed
        if (/[\s,]/.test(partial))                   { hide(); return; } // whitespace/comma = not a wildcard

        const all     = await fetchWildcards();
        const found   = all
            .filter(w => w.toLowerCase().includes(partial.toLowerCase()))
            .slice(0, 15);

        found.length ? show(found) : hide();
    }

    // ── event wiring ──

    inputEl.addEventListener("input", check);

    inputEl.addEventListener("keyup", e => {
        if (["ArrowUp", "ArrowDown", "Enter", "Escape", "Tab"].includes(e.key)) return;
        check();
    });

    inputEl.addEventListener("keydown", e => {
        if (!dropdown) return;
        if (e.key === "ArrowDown") {
            e.preventDefault();
            highlightIdx = (highlightIdx + 1) % matches.length;
            renderItems();
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            highlightIdx = (highlightIdx - 1 + matches.length) % matches.length;
            renderItems();
        } else if (e.key === "Enter" || e.key === "Tab") {
            if (matches[highlightIdx] !== undefined) {
                e.preventDefault();
                accept(matches[highlightIdx]);
            }
        } else if (e.key === "Escape") {
            hide();
        }
    });

    // Small delay on blur so a mousedown click fires before the dropdown vanishes.
    inputEl.addEventListener("blur", () => setTimeout(hide, 150));
}

// ── Extension ─────────────────────────────────────────────────────────────────

app.registerExtension({
    name: "comfy.FrogWildcardBox",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_TYPE) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated?.apply(this, arguments);
            // Widget's inputEl is created asynchronously — wait one tick.
            setTimeout(() => {
                const widget = this.widgets?.find(w => w.name === "text");
                if (widget?.inputEl) attachAutocomplete(widget.inputEl);
            }, 10);
            return r;
        };
    },
});
