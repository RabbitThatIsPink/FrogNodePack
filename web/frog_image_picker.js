/**
 * 🐸 Image Picker — DOM widget
 *
 * Captures a KSampler batch on Run 1, shows thumbnails for selection,
 * then on Proceed queues Run 2 which passes only the chosen frames
 * to the downstream Save node.
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
.fip-proceed { background: #3d8f5c; color: #fff; }
.fip-proceed:not(:disabled):hover { background: #4daf72; }
.fip-cancel  { background: #7d3333; color: #fff; }
.fip-cancel:not(:disabled):hover  { background: #9d4444; }

.fip-select-all {
  background: #2d5a8a;
  color: #fff;
}
.fip-select-all:not(:disabled):hover { background: #3a72af; }

.fip-status {
  margin-left: auto;
  color: #888;
  font-size: 11px;
  white-space: nowrap;
}

/* ── grid ── */
.fip-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--fip-thumb-size, 130px), 1fr));
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
  aspect-ratio: 1 / 1;
}
.fip-tile:hover              { border-color: #555; }
.fip-tile.fip-selected       { border-color: #4aaa7a; }
.fip-tile.fip-selected:hover { border-color: #5dcc95; }

.fip-tile img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
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

// ─── Widget builder ──────────────────────────────────────────────────────────

function buildPickerWidget(node) {
  _injectCSS();

  // ── DOM skeleton ──
  const wrap = document.createElement("div");
  wrap.className = "fip-wrap";

  const toolbar = document.createElement("div");
  toolbar.className = "fip-toolbar";

  const proceedBtn  = document.createElement("button");
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

  const status = document.createElement("span");
  status.className = "fip-status";
  status.textContent = "Run the workflow to generate images";

  toolbar.append(proceedBtn, cancelBtn, selectAllBtn, status);

  const grid = document.createElement("div");
  grid.className = "fip-grid";

  // Initial empty state
  const emptyMsg = document.createElement("div");
  emptyMsg.className = "fip-empty";
  emptyMsg.innerHTML = "<strong>No images yet</strong>Queue a workflow with this node to capture a batch.";
  grid.appendChild(emptyMsg);

  wrap.append(toolbar, grid);

  // ── State ──
  const selectedIndices = new Set();
  let totalCount = 0;

  // ── Helpers ──
  const updateStatus = () => {
    if (totalCount === 0) {
      status.textContent = "Run the workflow to generate images";
      proceedBtn.disabled  = true;
      cancelBtn.disabled   = true;
      selectAllBtn.disabled = true;
    } else {
      status.textContent = `${selectedIndices.size} / ${totalCount} selected`;
      proceedBtn.disabled  = selectedIndices.size === 0;
      cancelBtn.disabled   = false;
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
    if (!images || images.length === 0) return;

    grid.replaceChildren();
    selectedIndices.clear();
    totalCount = images.length;

    images.forEach((img, idx) => {
      const tile = document.createElement("div");
      tile.className = "fip-tile";

      const imgEl = document.createElement("img");
      const url   = api.apiURL(
        `/view?filename=${encodeURIComponent(img.filename)}` +
        `&subfolder=${encodeURIComponent(img.subfolder)}` +
        `&type=${encodeURIComponent(img.type)}`
      );
      imgEl.src = url;
      imgEl.alt = `Frame ${idx + 1}`;
      imgEl.draggable = false;

      const numBadge = document.createElement("div");
      numBadge.className = "fip-tile-num";
      numBadge.textContent = `#${idx + 1}`;

      const tick = document.createElement("div");
      tick.className = "fip-tile-tick";
      tick.textContent = "✓";

      tile.append(imgEl, numBadge, tick);

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

  // ── Select All / Deselect All ──
  selectAllBtn.addEventListener("click", () => {
    const tiles = [...grid.querySelectorAll(".fip-tile")];
    if (selectedIndices.size === totalCount) {
      // Deselect all
      selectedIndices.clear();
      tiles.forEach(t => t.classList.remove("fip-selected"));
    } else {
      // Select all
      tiles.forEach((t, i) => {
        selectedIndices.add(i);
        t.classList.add("fip-selected");
      });
    }
    updateStatus();
  });

  // ── Proceed ──
  proceedBtn.addEventListener("click", async () => {
    if (selectedIndices.size === 0) return;

    const nodeId    = String(node.id);
    const selection = [...selectedIndices].sort((a, b) => a - b);

    proceedBtn.disabled = true;
    proceedBtn.textContent = "…";
    status.textContent = "Queuing…";

    try {
      const resp = await fetch("/frog_picker/proceed", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ node_id: nodeId, selection }),
      });
      if (!resp.ok) throw new Error(`Server returned ${resp.status}`);

      // Queue one workflow run — the Picker node will output selected frames.
      await app.queuePrompt(0, 1);

      // Reset UI immediately (optimistic)
      resetUI();
      proceedBtn.textContent = "▶  Proceed";

    } catch (err) {
      console.error("[🐸 Image Picker] proceed failed:", err);
      proceedBtn.disabled  = false;
      proceedBtn.textContent = "▶  Proceed";
      status.textContent = "⚠ Proceed failed — check console";
    }
  });

  // ── Cancel ──
  cancelBtn.addEventListener("click", async () => {
    const nodeId = String(node.id);
    try {
      await fetch("/frog_picker/cancel", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ node_id: nodeId }),
      });
    } catch (err) {
      console.error("[🐸 Image Picker] cancel failed:", err);
    }
    resetUI();
  });

  // ── Listen for execution results ──
  // ComfyUI fires an "executed" event when a node completes with UI output.
  // We filter for this node's ID and populate thumbnails from the result.
  const onExecuted = ({ detail }) => {
    if (String(detail?.node) !== String(node.id)) return;

    const images = detail?.output?.images;
    // Images present → capture run completed, show thumbnails.
    // Empty / absent → proceed run completed, UI already reset.
    if (images && images.length > 0) {
      populateThumbnails(images);
    }
  };

  api.addEventListener("executed", onExecuted);

  // Cleanup when node is removed from the graph
  const origOnRemoved = node.onRemoved;
  node.onRemoved = function (...args) {
    api.removeEventListener("executed", onExecuted);
    return origOnRemoved?.apply(this, args);
  };

  return wrap;
}

// ─── Extension registration ──────────────────────────────────────────────────

const PICKER_TYPE = "FrogImagePicker";

app.registerExtension({
  name: "FrogNodePack.ImagePicker",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== PICKER_TYPE) return;

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
