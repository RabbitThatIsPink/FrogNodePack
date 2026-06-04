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
}
.fip-btn {
  padding: 5px 12px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
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
`;

let _cssAdded = false;
function injectCSS() {
  if (_cssAdded) return;
  _cssAdded = true;
  const s = document.createElement("style");
  s.textContent = CSS;
  document.head.appendChild(s);
}

// ─── Serialise graph ─────────────────────────────────────────────────────────

async function getPrompt() {
  try {
    const r = await app.graphToPrompt();
    return r?.output ?? r ?? null;
  } catch (e) {
    console.warn("[🐸 Image Picker] graphToPrompt:", e);
    return null;
  }
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

  const status = document.createElement("div");
  status.className = "fip-status";
  status.textContent = "Run the workflow to generate images.";

  const grid = document.createElement("div");
  grid.className = "fip-grid";

  const empty = document.createElement("div");
  empty.className = "fip-empty";
  empty.innerHTML = "<strong>No images yet</strong>Queue a workflow to capture a batch.";
  grid.appendChild(empty);

  wrap.append(btns, status, grid);

  // ── column layout: 2–10 columns, each at most 150 px ──
  const GAP = 6, TILE = 150, MIN_COLS = 2, MAX_COLS = 10;
  function setColumns() {
    const w = grid.clientWidth;
    if (w === 0) return;
    const cols = Math.max(MIN_COLS, Math.min(MAX_COLS, Math.floor((w + GAP) / (TILE + GAP))));
    const colW = Math.floor((w - (cols - 1) * GAP) / cols);
    grid.style.gridTemplateColumns = `repeat(${cols}, ${colW}px)`;
  }
  const _ro = new ResizeObserver(setColumns);
  _ro.observe(grid);

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

    images.forEach((img, idx) => {
      const tile = document.createElement("div");
      tile.className = "fip-tile";

      const im  = document.createElement("img");
      im.src      = api.apiURL(`/view?filename=${enc(img.filename)}&subfolder=${enc(img.subfolder)}&type=${enc(img.type)}`);
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
  proceedBtn.onclick = async () => {
    if (!sel.size) return;
    proceedBtn.disabled    = true;
    proceedBtn.textContent = "…";
    status.textContent     = "Queuing…";
    try {
      const prompt = await getPrompt();
      const r = await fetch("/frog_picker/proceed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          node_id:   String(node.id),
          selection: [...sel].sort((a, b) => a - b),
          prompt,
          client_id: api.clientId ?? "",
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      if (!j.queued) {
        // Server-side queue unavailable — fall back to full workflow
        console.warn("[🐸 Image Picker] server queue failed, falling back to app.queuePrompt");
        await app.queuePrompt(0, 1);
      }
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

  // ── Listen for captured-batch WS event ──
  const onCapture = ({ detail }) => {
    if (String(detail?.node_id) !== String(node.id)) return;
    populate(detail.images);
  };
  api.addEventListener("frog_picker.captured", onCapture);

  const origRemoved = node.onRemoved;
  node.onRemoved = function (...a) {
    _ro.disconnect();
    api.removeEventListener("frog_picker.captured", onCapture);
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
