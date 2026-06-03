/**
 * 🐸 Merge — dynamic input growth
 *
 * Starts with input_1 visible. Each time the highest-numbered visible input
 * is connected, the next slot appears (up to MAX_INPUTS). Disconnecting
 * collapses empty trailing slots back down, always leaving exactly one
 * unconnected slot at the bottom.
 */

import { app } from "../../../scripts/app.js";

const NODE_TYPE  = "FrogMerge";
const MAX_INPUTS = 10;

function highestConnected(node) {
    let hi = 0;
    for (let i = 1; i <= MAX_INPUTS; i++) {
        const inp = node.inputs?.find(x => x.name === `input_${i}`);
        if (inp && inp.link != null) hi = i;
    }
    return hi;
}

function updateInputs(node) {
    if (!node.inputs) return;

    // Show all connected slots plus exactly one empty "next" slot.
    const visible = Math.min(highestConnected(node) + 1, MAX_INPUTS);

    for (let i = 1; i <= MAX_INPUTS; i++) {
        const inp = node.inputs.find(x => x.name === `input_${i}`);
        if (!inp) continue;

        if (i <= visible) {
            inp.hidden = false;
            if (inp._frog_orig_type) {
                inp.type = inp._frog_orig_type;
                delete inp._frog_orig_type;
            }
        } else {
            if (!inp._frog_orig_type) inp._frog_orig_type = inp.type;
            inp.hidden = true;
        }
    }

    node.setSize(node.computeSize());
    node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "comfy.FrogMerge",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_TYPE) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated?.apply(this, arguments);
            setTimeout(() => updateInputs(this), 10);
            return r;
        };

        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const r = onConnectionsChange?.apply(this, arguments);
            setTimeout(() => updateInputs(this), 10);
            return r;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure?.apply(this, arguments);
            setTimeout(() => updateInputs(this), 10);
            return r;
        };
    },
});
