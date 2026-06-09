/**
 * FrogNodePack — LLM Control Widget
 *
 * Adds a Start / Stop button to the 🐸 Prompt Refiner (Ollama) node.
 * Uses the Ollama REST API to load or unload the selected model on demand.
 *
 * Load:   POST /api/generate  { model, keep_alive: -1 }
 * Unload: POST /api/generate  { model, keep_alive: 0  }
 * Status: GET  /api/ps        → { models: [{ name }] }
 */

import { app } from "../../scripts/app.js";

const OLLAMA = "http://192.168.0.194:11434";

// ── Ollama helpers ─────────────────────────────────────────────────────────

async function getRunningModels() {
    try {
        const r = await fetch(`${OLLAMA}/api/ps`);
        if (!r.ok) return [];
        const d = await r.json();
        return (d.models || []).map(m => m.name);
    } catch {
        return null;   // null = server unreachable
    }
}

async function ollamaLoad(model) {
    try {
        await fetch(`${OLLAMA}/api/generate`, {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ model, keep_alive: -1 }),
        });
    } catch { /* server offline */ }
}

async function ollamaUnload(model) {
    try {
        await fetch(`${OLLAMA}/api/generate`, {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ model, keep_alive: 0 }),
        });
    } catch { /* server offline */ }
}

// ── Extension ──────────────────────────────────────────────────────────────

app.registerExtension({
    name: "FrogNodePack.LLMControl",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "FrogPromptRefiner") return;

        const _onCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            if (_onCreated) _onCreated.apply(this, arguments);

            const node = this;

            // Add the button widget
            const btn = node.addWidget(
                "button",
                "⏳ Checking...",
                null,
                async () => { await toggle(node, btn); }
            );
            btn.serialize = false;   // don't save button state to workflow JSON

            // ── Status helpers ───────────────────────────────────────────

            async function refreshStatus() {
                const model  = getModel(node);
                const loaded = await getRunningModels();

                if (loaded === null) {
                    // Ollama server not reachable
                    btn.name = "⚫ Ollama Offline";
                } else {
                    const running = loaded.some(m => m === model || m.startsWith(model + ":"));
                    btn.name = running
                        ? "🟢 LLM Running  —  click to Stop"
                        : "🔴 LLM Stopped  —  click to Start";
                }
                node.setDirtyCanvas(true);
            }

            async function toggle(node, btn) {
                const model  = getModel(node);
                const loaded = await getRunningModels();

                if (loaded === null) {
                    btn.name = "⚫ Ollama Offline";
                    node.setDirtyCanvas(true);
                    return;
                }

                const running = loaded.some(m => m === model || m.startsWith(model + ":"));

                if (running) {
                    btn.name = "⏳ Stopping...";
                    node.setDirtyCanvas(true);
                    await ollamaUnload(model);
                } else {
                    btn.name = "⏳ Starting...";
                    node.setDirtyCanvas(true);
                    await ollamaLoad(model);
                }

                // Give Ollama a moment to settle then refresh
                setTimeout(() => refreshStatus(), 1500);
            }

            // ── Poll every 15 s ──────────────────────────────────────────

            refreshStatus();

            const interval = setInterval(() => {
                if (!node.graph) { clearInterval(interval); return; }
                refreshStatus();
            }, 15_000);
        };
    },
});

// ── Utility ────────────────────────────────────────────────────────────────

function getModel(node) {
    const w = node.widgets?.find(w => w.name === "model");
    return (w?.value || "qwen3:8b").trim();
}
