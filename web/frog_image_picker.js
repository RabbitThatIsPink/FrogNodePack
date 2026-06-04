/**
 * 🐸 Image Picker — DOM widget
 *
 * Captures a KSampler batch on Run 1, shows thumbnails for selection,
 * then on Proceed queues a MINIMAL prompt (Picker + downstream only —
 * no KSampler re-run) that passes only the chosen frames to Save.
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ─── CSS ────────────────────────────────────────────────────────────────────

const _CSS = `
.fip-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  height: 100%;
  box-sizing: border-box;
  font-size: 12px;
  color: #ccc;
  user-select: none;
}

/* ── toolbar ── */
.fip-toolbar {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.fip-btn {
  padding: 5px 12px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.3px;
  transition: background 80ms;
}
.fip-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.fip-proceed     { background: #3d8f5c; color: #fff; }
.fip-proceed:not(:disabled):hover { background: #4daf72; }
.fip-cancel      { background: #7d3333; color: #fff; }
.fip-cancel:not(:disabled):hover  { background: #9d4444; }
.fip-select-all  { background: #2d5a8a; color: #fff; }
.fip-select-all:not(:disabled):hover { background: #3a72af; }

/* ── status bar — sits below the buttons ── */
.fip-status {
  font-size: 11px;
  color: #888;
  flex-shrink: 0;
  padding: 2px 0;
}

/* ── grid ── */
.fip-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 6px;
  overflow-y: auto;
  flex: 1;
  min-height: 80px;
}

/* ── tile ── */
.fip-tile {
  position: relative;
  border: 2px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  overflow: hidden;
  background: #1a1a1a;
  transition: border-color 80ms;
  /* No fixed aspect-ratio — image determines height naturally */
}
.fip-tile:hover              { border-color: #555; }
.fip-tile.fip-selected       { border-color: #4aaa7a; }
.fip-tile.fip-selected:hover { border-color: #5dcc95; }

.fip-tile img {
  width: 100%;
  height: auto;
  display: block;
  pointer-events: none;
}

/* number badge */
.fip-tile-num {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  background: rgba(0,0,0,.55);
  color: #eee;
  font-size: 10px;
  text-align: center;
  padding: 2px 0;
  pointer-events: none;
}

/* tick mark */
.fip-tile-tick {
  position: absolute;
  top: 4px; right: 4px;
  width: 18px; height: 18px;
  background: #4aaa7a;
  border-radius: 50%;
  display: none;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: #fff;
  font-weight: bold;
  pointer-events: none;
}
.fip-tile.fip-selected .fip-tile-tick { display: flex; }

/* empty state */
.fip-empty {
  grid-column: 1 / -1;
  text-align: center;
  color: #555;
  padding: 24px 8px;
  font-size: 12px;
  line-height: 1.5;
}
.fip-empty strong { color: #666; display: block; margin-bottom: 4px; }
`;

let _cssInjected = false;
function _injectCSS() {
  if (_cssInjected) return;
  _cssInjected = true;
  const s = document.createElement("style");
  s.textContent = _CSS;
  document.head.appendChild(s);
}

// ─── Graph helper ────────────────────────────────────────────────────────────

/**
 * Serialise the current graph to the API prompt format.
 * Returns the output object, or null if graphToPrompt is unavailable / throws.
 */
async function getFullPrompt() {
  try {
    const result = await app.graphToPrompt();
    // Different ComfyUI versions may return {output, workflow} or just the output
    return result?.output ?? result ?? null;
  } catch (e) {
    console.warn("[🐸 Image Picker] graphToPrompt failed:", e);
    return null;
  }
}

// ─── Widget builder ──────────────────────────────────────────────────────────

function buildPickerWidget(node) {
  _injectCSS();

  // ── DOM skeleton ──────────────────────────────────────────────────────────
  const wrap = document.createElement("div");
  wrap.className = "fip-wrap";

  // Buttons row
  const toolbar = document.createElement("div");
  toolbar.className = "fip-toolbar";

  const proceedBtn = document.createElement("button");
  proceedBtn.className = "fip-btn fip-proceed";
  proceedBtn.textContent = "▶  Proceed";
  proceedBtn.disabled = true;

  const cancelBtn = document.createElement("button");
  cancelBtn.className = "fip-btn fip-cancel";
  cancelBtn.textContent = "✕  Cancel";
  cancelBtn.disabled = true;

  const selectAllBtn = document.createElement("button");
  selectAllBtn.className = "fip-btn fip-select-all";
  selectAllBtn.textContent = "Select All";
  selectAllBtn.disabled = true;

  toolbar.append(proceedBtn, cancelBtn, selectAllBtn);

  // Status line — below the buttons
  const status = document.createElement("div");
  status.className = "fip-status";
  status.textContent = "Run the workflow to generate images.";

  // Thumbnail grid
  const grid = document.createElement("div");
  grid.className = "fip-grid";

  const emptyMsg = document.createElement("div");
  emptyMsg.className = "fip-empty";
  emptyMsg.innerHTML = "<strong>No images yet</strong>Queue a workflow with this node to capture a batch.";
  grid.appendChild(emptyMsg);

  wrap.append(toolbar, status, grid);

  // ── State ─────────────────────────────────────────────────────────────────
  const selectedIndices = new Set();
  let totalCount = 0;

  // ── Helpers ───────────────────────────────────────────────────────────────
  const updateStatus = () => {
    if (totalCount === 0) {
      status.textContent = "Run the workflow to generate images.";
      proceedBtn.disabled   = true;
      cancelBtn.disabled    = true;
      selectAllBtn.disabled = true;
    } else {
      status.textContent = `${selectedIndices.size} / ${totalCount} selected`;
      proceedBtn.disabled   = selectedIndices.size === 0;
      cancelBtn.disabled    = false;
      selectAllBtn.disabled = false;
      selectAllBtn.textContent =
        selectedIndices.size === totalCount ? "Deselect All" : "Select All";
    }
  };

  const resetUI = () => {
    grid.replaceChildren(emptyMsg);
    selectedIndices.clear();
    totalCount = 0;
    updateStatus();
  };

  const populateThumbnails = (images) => {
    if (!images?.length) return;
    grid.replaceChildren();
    selectedIndices.clear();
    totalCount = images.length;

    images.forEach((img, idx) => {
      const tile = document.createElement("div");
      tile.className = "fip-tile";

      const imgEl = document.createElement("img");
      imgEl.src = api.apiURL(
        `/view?filename=${encodeURIComponent(img.filename)}` +
        `&subfolder=${encodeURIComponent(img.subfolder)}` +
        `&type=${encodeURIComponent(img.type)}`
      );
      imgEl.alt     = `Frame ${idx + 1}`;
      imgEl.draggable = false;

      const num = document.createElement("div");
      num.className   = "fip-tile-num";
      num.textContent = `#${idx + 1}`;

      const tick = document.createElement("div");
      tick.className   = "fip-tile-tick";
      tick.textContent = "✓";

      tile.append(imgEl, num, tick);
      tile.addEventListener("click", () => {
        if (selectedIndices.has(idx)) {
          selectedIndices.delete(idx);
          tile.classList.remove("fip-selected");
        } else {
          selectedIndices.add(idx);
          tile.classList.add("fip-selected");
        }
        updateStatus();
      });

      grid.appendChild(tile);
    });

    updateStatus();
  };

  // ── Select All / Deselect All ─────────────────────────────────────────────
  selectAllBtn.addEventListener("click", () => {
    const tiles = [...grid.querySelectorAll(".fip-tile")];
    if (selectedIndices.size === totalCount) {
      selectedIndices.clear();
      tiles.forEach(t => t.classList.remove("fip-selected"));
    } else {
      tiles.forEach((t, i) => { selectedIndices.add(i); t.classList.add("fip-selected"); });
    }
    updateStatus();
  });

  // ── Proceed ───────────────────────────────────────────────────────────────
  proceedBtn.addEventListener("click", async () => {
    if (selectedIndices.size === 0) return;

    const nodeId    = String(node.id);
    const selection = [...selectedIndices].sort((a, b) => a - b);

    proceedBtn.disabled    = true;
    proceedBtn.textContent = "…";
    status.textContent     = "Queuing…";

    try {
      // Serialise the current graph so Python can build the minimal
      // sub-prompt (Picker + downstream only, KSampler stripped).
      const fullPrompt = await getFullPrompt();

      const resp = await fetch("/frog_picker/proceed", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({
          node_id:   nodeId,
          selection,
          prompt:    fullPrompt,          // Python handles graph trimming
          client_id: api.clientId ?? "",
        }),
      });
      if (!resp.ok) throw new Error(`/frog_picker/proceed → ${resp.status}`);

      const result = await resp.json();

      if (!result.queued) {
        // Python couldn't queue directly (e.g. older ComfyUI build) —
        // fall back to full workflow.  KSampler re-runs but Picker
        // uses stored frames so the correct images are still saved.
        console.warn("[🐸 Image Picker] server-side queue unavailable, falling back to full queue");
        await app.queuePrompt(0, 1);
      }

      resetUI();
      proceedBtn.textContent = "▶  Proceed";

    } catch (err) {
      console.error("[🐸 Image Picker] proceed failed:", err);
      proceedBtn.disabled    = false;
      proceedBtn.textContent = "▶  Proceed";
      status.textContent     = "⚠ Proceed failed — check console";
    }
  });

  // ── Cancel ────────────────────────────────────────────────────────────────
  cancelBtn.addEventListener("click", async () => {
    try {
      await fetch("/frog_picker/cancel", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ node_id: String(node.id) }),
      });
    } catch (err) {
      console.error("[🐸 Image Picker] cancel failed:", err);
    }
    resetUI();
  });

  // ── Listen for captured batch (custom WS event) ───────────────────────────
  // The Python node sends "frog_picker.captured" instead of returning
  // ui.images — this prevents ComfyUI from rendering a duplicate image strip.
  const onCaptured = ({ detail }) => {
    if (String(detail?.node_id) !== String(node.id)) return;
    populateThumbnails(detail.images);
  };
  api.addEventListener("frog_picker.captured", onCaptured);

  // Cleanup on node removal
  const origOnRemoved = node.onRemoved;
  node.onRemoved = function (...args) {
    api.removeEventListener("frog_picker.captured", onCaptured);
    return origOnRemoved?.apply(this, args);
  };

  return wrap;
}

// ─── Extension registration ──────────────────────────────────────────────────

app.registerExtension({
  name: "FrogNodePack.ImagePicker",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "FrogImagePicker") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onNodeCreated?.apply(this, arguments);

      const container = buildPickerWidget(this);
      container.style.minHeight = "240px";
      container.style.width     = "100%";

      this.addDOMWidget("picker_grid", "FrogImagePickerGrid", container, {
        serialize:    false,
        hideOnZoom:   false,
        getMinHeight: () => 240,
        getValue:     () => "",
        setValue:     () => {},
      });

      this.size = [340, 420];
      if (typeof this.setSize === "function") this.setSize([340, 420]);
      return r;
    };
  },
});
