/**
 * 🐸 Image Picker — DOM widget
 *
 * Capture run  → thumbnails appear, user selects, then clicks Proceed.
 * Proceed      → server queues a minimal sub-prompt (Picker + Save only,
 *                no KSampler) and the selected frames flow to Save.
 * Cancel       → stored frames are cleared, UI resets.
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ─── Styles ─────────────────────────────────────────────────────────────────

const CSS = `
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

/* buttons row */
.fip-btns {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  flex-wrap: wrap;
  justify-content: center;
}
.fip-btn {
  flex: 1;
  min-width: 75px;
  max-width: 180px;
  padding: 5px 12px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  transition: background 80ms;
}
.fip-btn:disabled { opacity: 0.35; cursor: not-allowed; }

.fip-proceed    { background: #3d8f5c; color: #fff; }
.fip-proceed:not(:disabled):hover { background: #4daf72; }
.fip-cancel     { background: #7d3333; color: #fff; }
.fip-cancel:not(:disabled):hover  { background: #9d4444; }
.fip-selall     { background: #2d5a8a; color: #fff; }
.fip-selall:not(:disabled):hover  { background: #3a72af; }

/* status line */
.fip-status {
  font-size: 11px;
  color: #888;
  flex-shrink: 0;
}

/* thumbnail grid — columns set dynamically by ResizeObserver (2–10 per row) */
.fip-grid {
  display: grid;
  gap: 6px;
  justify-content: start;
  align-content: start;
  overflow-y: auto;
  overflow-x: hidden;
  flex: 1;
  min-height: 60px;
}

/* tile — fills its grid column; height comes from the image */
.fip-tile {
  width: 100%;
  position: relative;
  border: 2px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  overflow: hidden;
  background: #1a1a1a;
  transition: border-color 80ms;
  box-sizing: border-box;
}
.fip-tile:hover              { border-color: #555; }
.fip-tile.fip-sel            { border-color: #4aaa7a; }
.fip-tile.fip-sel:hover      { border-color: #5dcc95; }

.fip-tile img {
  width: 100%;
  height: auto;   /* preserves aspect ratio */
  display: block;
  pointer-events: none;
}

/* number badge */
.fip-num {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  background: rgba(0,0,0,.55);
  color: #eee;
  font-size: 10px;
  text-align: center;
  padding: 2px 0;
  pointer-events: none;
}

/* selection tick */
.fip-tick {
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
.fip-tile.fip-sel .fip-tick { display: flex; }

/* empty-state placeholder */
.fip-empty {
  grid-column: 1 / -1;
  text-align: center;
  color: #555;
  padding: 24px 8px;
  line-height: 1.5;
}
.fip-empty strong { color: #666; display: block; margin-bottom: 4px; }

/* size slider row */
.fip-size-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  font-size: 11px;
  color: #888;
}
.fip-size-row label { white-space: nowrap; }
.fip-size-slider {
  flex: 1;
  accent-color: #4aaa7a;
  cursor: pointer;
}
.fip-size-val {
  min-width: 32px;
  text-align: right;
  color: #aaa;
}
`;

let _cssAdded = false;
function injectCSS() {
  if (_cssAdded) return;
  _cssAdded = true;
  const s = document.createElement("style");
  s.textContent = CSS;
  document.head.appendChild(s);
}

// ─── Widget ──────────────────────────────────────────────────────────────────

function buildWidget(node) {
  injectCSS();

  // ── skeleton ──
  const wrap   = document.createElement("div");
  wrap.className = "fip-wrap";

  const btns   = document.createElement("div");
  btns.className = "fip-btns";

  const proceedBtn = el("button", "fip-btn fip-proceed", "▶  Proceed");
  const cancelBtn  = el("button", "fip-btn fip-cancel",  "✕  Cancel");
  const selAllBtn  = el("button", "fip-btn fip-selall",  "Select All");
  [proceedBtn, cancelBtn, selAllBtn].forEach(b => b.disabled = true);
  btns.append(proceedBtn, cancelBtn, selAllBtn);

  // ── size slider ──
  const LS_KEY = "frog_picker_tile_size";
  const TILE_MIN = 60, TILE_MAX = 320, TILE_DEFAULT = 150;
  let tileSize = parseInt(localStorage.getItem(LS_KEY) ?? TILE_DEFAULT, 10);
  if (isNaN(tileSize) || tileSize < TILE_MIN || tileSize > TILE_MAX) tileSize = TILE_DEFAULT;

  const sizeRow = document.createElement("div");
  sizeRow.className = "fip-size-row";

  const sizeLabel = el("label", null, "Tile size:");
  const sizeSlider = document.createElement("input");
  sizeSlider.type  = "range";
  sizeSlider.className = "fip-size-slider";
  sizeSlider.min   = TILE_MIN;
  sizeSlider.max   = TILE_MAX;
  sizeSlider.step  = 10;
  sizeSlider.value = tileSize;

  const sizeVal = el("div", "fip-size-val", `${tileSize}px`);
  sizeRow.append(sizeLabel, sizeSlider, sizeVal);

  const status = document.createElement("div");
  status.className = "fip-status";
  status.textContent = "Run the workflow to generate images.";

  const grid = document.createElement("div");
  grid.className = "fip-grid";

  const empty = document.createElement("div");
  empty.className = "fip-empty";
  empty.innerHTML = "<strong>No images yet</strong>Queue a workflow to capture a batch.";
  grid.appendChild(empty);

  wrap.append(btns, sizeRow, status, grid);

  // ── column layout: 2–10 columns, width driven by tileSize slider ──
  const GAP = 6, MIN_COLS = 2, MAX_COLS = 10;
  function setColumns() {
    const w = grid.clientWidth;
    if (w === 0) return;
    const cols = Math.max(MIN_COLS, Math.min(MAX_COLS, Math.floor((w + GAP) / (tileSize + GAP))));
    const colW = Math.floor((w - (cols - 1) * GAP) / cols);
    grid.style.gridTemplateColumns = `repeat(${cols}, ${colW}px)`;
  }
  const _ro = new ResizeObserver(setColumns);
  _ro.observe(grid);

  // ── slider wiring ──
  sizeSlider.addEventListener("input", () => {
    tileSize = parseInt(sizeSlider.value, 10);
    sizeVal.textContent = `${tileSize}px`;
    localStorage.setItem(LS_KEY, tileSize);
    setColumns();
  });

  // ── state ──
  const sel = new Set();
  let total = 0;

  // ── helpers ──
  function updateStatus() {
    if (total === 0) {
      status.textContent = "Run the workflow to generate images.";
      proceedBtn.disabled = cancelBtn.disabled = selAllBtn.disabled = true;
    } else {
      status.textContent = `${sel.size} / ${total} selected`;
      proceedBtn.disabled = sel.size === 0;
      cancelBtn.disabled  = false;
      selAllBtn.disabled  = false;
      selAllBtn.textContent = sel.size === total ? "Deselect All" : "Select All";
    }
  }

  function reset() {
    grid.replaceChildren(empty);
    sel.clear();
    total = 0;
    proceedBtn.textContent = "▶  Proceed";
    updateStatus();
  }

  function populate(images) {
    if (!images?.length) return;
    setColumns();
    grid.replaceChildren();
    sel.clear();
    total = images.length;

    // Cache-bust so the browser always fetches the current files rather than
    // serving a stale cached version from the previous job (filenames repeat
    // across runs: frame_0000.png, frame_0001.png, …).
    const bust = Date.now();

    images.forEach((img, idx) => {
      const tile = document.createElement("div");
      tile.className = "fip-tile";

      const im  = document.createElement("img");
      im.src      = api.apiURL(`/view?filename=${enc(img.filename)}&subfolder=${enc(img.subfolder)}&type=${enc(img.type)}&t=${bust}`);
      im.alt      = `#${idx + 1}`;
      im.draggable = false;

      const num  = el("div", "fip-num",  `#${idx + 1}`);
      const tick = el("div", "fip-tick", "✓");

      tile.append(im, num, tick);
      tile.onclick = () => {
        sel.has(idx) ? (sel.delete(idx), tile.classList.remove("fip-sel"))
                     : (sel.add(idx),    tile.classList.add("fip-sel"));
        updateStatus();
      };
      grid.appendChild(tile);
    });
    updateStatus();
  }

  // ── Select All / Deselect All ──
  selAllBtn.onclick = () => {
    const tiles = [...grid.querySelectorAll(".fip-tile")];
    if (sel.size === total) {
      sel.clear();
      tiles.forEach(t => t.classList.remove("fip-sel"));
    } else {
      tiles.forEach((t, i) => { sel.add(i); t.classList.add("fip-sel"); });
    }
    updateStatus();
  };

  // ── Proceed ──
  // Simply POST the selection — the Python execution thread is blocking on a
  // sleep loop waiting for this. No second prompt submission is needed.
  proceedBtn.onclick = async () => {
    if (!sel.size) return;
    proceedBtn.disabled    = true;
    proceedBtn.textContent = "…";
    status.textContent     = "Processing…";
    try {
      const r = await fetch("/frog_picker/proceed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          node_id:   String(node.id),
          selection: [...sel].sort((a, b) => a - b),
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      reset();
    } catch (e) {
      console.error("[🐸 Image Picker] proceed:", e);
      proceedBtn.disabled    = false;
      proceedBtn.textContent = "▶  Proceed";
      status.textContent     = "⚠ Proceed failed — see browser console";
    }
  };

  // ── Cancel ──
  cancelBtn.onclick = async () => {
    try {
      await fetch("/frog_picker/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: String(node.id) }),
      });
    } catch (e) { console.error("[🐸 Image Picker] cancel:", e); }
    reset();
  };

  // ── Listen for WS events ──

  // C: explicit clear sent by Python before each new capture
  const onClear = ({ detail }) => {
    if (String(detail?.node_id) !== String(node.id)) return;
    reset();
  };

  const onCapture = ({ detail }) => {
    if (String(detail?.node_id) !== String(node.id)) return;
    populate(detail.images);
  };

  // New job started — reset the grid so stale thumbnails don't linger
  const onExecStart = () => {
    if (total > 0) {
      reset();
      status.textContent = "Generating…";
    }
  };

  api.addEventListener("frog_picker.clear",    onClear);
  api.addEventListener("frog_picker.captured", onCapture);
  api.addEventListener("execution_start",      onExecStart);

  const origRemoved = node.onRemoved;
  node.onRemoved = function (...a) {
    _ro.disconnect();
    api.removeEventListener("frog_picker.clear",    onClear);
    api.removeEventListener("frog_picker.captured", onCapture);
    api.removeEventListener("execution_start",      onExecStart);
    return origRemoved?.apply(this, a);
  };

  return wrap;
}

// ─── Tiny DOM helper ─────────────────────────────────────────────────────────

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls)  e.className   = cls;
  if (text) e.textContent = text;
  return e;
}

function enc(s) { return encodeURIComponent(s); }

// ─── Register extension ──────────────────────────────────────────────────────

app.registerExtension({
  name: "FrogNodePack.ImagePicker",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "FrogImagePicker") return;

    const orig = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = orig?.apply(this, arguments);
      const w = buildWidget(this);
      w.style.minHeight = "240px";
      w.style.width     = "100%";
      this.addDOMWidget("picker_grid", "FrogImagePickerGrid", w, {
        serialize:    false,
        hideOnZoom:   false,
        getMinHeight: () => 240,
        getValue:     () => "",
        setValue:     () => {},
      });
      this.size = [360, 440];
      this.setSize?.([360, 440]);
      return r;
    };
  },
});
