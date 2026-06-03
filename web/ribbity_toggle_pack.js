/**
 * 🐸-Pack — Ribbity Toggle Pack
 * When a toggle is turned OFF, all nodes inside a canvas group whose title
 * contains the matching keyword are BYPASSED. ON re-enables them.
 */

import { app } from "../../scripts/app.js";

const MODE_ACTIVE = 0;
const MODE_BYPASS = 4;
const NODE_TYPE   = "FrogTogglePack";

const TOGGLE_MAP = {
    "tagger":    "tagger",
    "raffle":  "raffle",
    "florence2": "florence2",
    "scene":     "scene",
};

function getNodesInGroup(keyword) {
    const graph = app.graph;
    const groups = (graph._groups || []).filter(g =>
        g.title.toLowerCase().includes(keyword.toLowerCase())
    );
    if (!groups.length) return [];
    const result = [];
    for (const group of groups) {
        const [gx, gy, gw, gh] = [group.pos[0], group.pos[1], group.size[0], group.size[1]];
        for (const node of graph._nodes || []) {
            if (node.pos[0] >= gx && node.pos[1] >= gy &&
                node.pos[0] <= gx + gw && node.pos[1] <= gy + gh) {
                result.push(node);
            }
        }
    }
    return result;
}

function applyBypass(keyword, enabled) {
    const nodes = getNodesInGroup(keyword);
    const mode  = enabled ? MODE_ACTIVE : MODE_BYPASS;
    for (const node of nodes) {
        if (node.mode !== mode) {
            node.mode = mode;
            node.setDirtyCanvas(true, true);
        }
    }
}

function patchNode(node) {
    if (node.__frogTogglePatched) return;
    node.__frogTogglePatched = true;
    const orig = node.onWidgetChanged;
    node.onWidgetChanged = function(name, value, oldValue, widget) {
        if (orig) orig.call(this, name, value, oldValue, widget);
        const keyword = TOGGLE_MAP[name];
        if (keyword !== undefined) applyBypass(keyword, value);
    };
}

app.registerExtension({
    name: "RibbityPack.TogglePack",

    async nodeCreated(node) {
        if (node.comfyClass === NODE_TYPE || node.type === NODE_TYPE) patchNode(node);
    },

    async loadedGraphNode(node) {
        if (node.type === NODE_TYPE) {
            patchNode(node);
            for (const widget of node.widgets || []) {
                const keyword = TOGGLE_MAP[widget.name];
                if (keyword !== undefined) applyBypass(keyword, widget.value);
            }
        }
    },
});
