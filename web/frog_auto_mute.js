/**
 * 🐸 Auto-Mute — Tagger subgraph
 *
 * Watches the `florence2` toggle on every FrogTogglePack node.
 *
 * When the toggle is OFF  → mutes the node wired into FrogPromptMerge's
 *   "Florence2" input so ComfyUI skips the entire tagger pipeline
 *   (Florence2 + WD14 + FrogTagFilter) and saves the processing time.
 *
 * When the toggle is ON  → restores that node to active.
 *
 * Graph traversal (no hardcoded IDs):
 *   FrogTogglePack  →[ANIMA_TOGGLES]→  FrogPromptMerge
 *                                              ↑
 *                         tagger node  →[Florence2 input]
 */

import { app } from "../../scripts/app.js";

// ─── Core logic ──────────────────────────────────────────────────────────────

function applyMuteState(togglePackNode) {
    const w = togglePackNode.widgets?.find(w => w.name === "florence2");
    if (!w) return;

    // 0 = LiteGraph ALWAYS (active)  |  4 = LiteGraph NEVER (muted)
    const targetMode = w.value === true ? 0 : 4;

    for (const output of (togglePackNode.outputs ?? [])) {
        for (const linkId of (output.links ?? [])) {
            const link = app.graph.links[linkId];
            if (!link) continue;

            const mergeNode = app.graph.getNodeById(link.target_id);
            if (mergeNode?.type !== "FrogPromptMerge") continue;

            for (const inp of (mergeNode.inputs ?? [])) {
                if (inp.name !== "Florence2" || inp.link == null) continue;

                const srcLink = app.graph.links[inp.link];
                if (!srcLink) continue;

                const taggerNode = app.graph.getNodeById(srcLink.origin_id);
                if (!taggerNode) continue;

                if (taggerNode.mode === targetMode) continue; // already correct

                taggerNode.mode = targetMode;
                taggerNode.setDirtyCanvas?.(true, true);
                console.log(
                    `[🐸 Auto-Mute] ${taggerNode.title || taggerNode.type}`
                    + ` (id ${taggerNode.id})`
                    + ` → ${targetMode === 0 ? "▶ active" : "⏸ muted"}`
                );
            }
        }
    }

    app.graph.setDirtyCanvas?.(true, false);
}

// ─── Hook a single FrogTogglePack node ───────────────────────────────────────

function hookNode(node) {
    const w = node.widgets?.find(w => w.name === "florence2");
    if (!w || w._frogAutoMuteHooked) return;
    w._frogAutoMuteHooked = true;

    const origCb = w.callback;
    w.callback = function (value, ...rest) {
        origCb?.call(this, value, ...rest);
        // Defer one tick so the widget value is committed before we read it
        setTimeout(() => applyMuteState(node), 0);
    };
}

// ─── Debounced full-graph scan ────────────────────────────────────────────────
// Fires once after ALL nodes have loaded rather than once per node, so that
// graph links are fully established before we traverse them.

let _scanTimer = null;
function scheduleFullScan() {
    clearTimeout(_scanTimer);
    _scanTimer = setTimeout(() => {
        for (const node of (app.graph._nodes ?? [])) {
            if (node.type === "FrogTogglePack") applyMuteState(node);
        }
    }, 150);
}

// ─── Extension registration ───────────────────────────────────────────────────

app.registerExtension({
    name: "FrogNodePack.AutoMuteTagger",

    // Called when a node is created interactively (drag from menu)
    nodeCreated(node) {
        if (node.type !== "FrogTogglePack") return;
        hookNode(node);
    },

    // Called for each node as a saved workflow is loaded
    loadedGraphNode(node) {
        if (node.type !== "FrogTogglePack") return;
        hookNode(node);
        // Debounced — actually runs after the last node in the workflow loads
        scheduleFullScan();
    },
});
