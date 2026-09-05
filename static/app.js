/* ClipFlow PRO — Merge Studio
   Wires the NLE-styled UI to the existing Flask /api/merge backend.
   Mockup regions map to real features:
     Project Bin  -> imported media (videos / image / audio)
     Monitor      -> preview of the selected clip
     Inspector    -> output name, duration, loop count, loop mode, stitch
     Timeline     -> visual of clips + soundtrack
     Export/Create-> POST /api/merge
*/

const VIDEO_EXT = ["mp4", "mov", "avi", "mkv", "webm", "m4v"];
const AUDIO_EXT = ["mp3", "wav", "m4a", "aac", "flac", "ogg", "opus"];
const IMAGE_EXT = ["jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"];

let uid = 0;
const state = {
  media: [],        // {id, file, kind, url, name, size, duration, width, height}
  selectedId: null,
  filter: "all",
  muted: false,
};

/* ---------- element refs ---------- */
const $ = (id) => document.getElementById(id);
const importInput = $("import-input");
const binGrid = $("bin-grid");
const binEmpty = $("bin-empty");
const monitorVideo = $("monitor-video");
const monitorImage = $("monitor-image");
const monitorAudio = $("monitor-audio");
const monitorPlaceholder = $("monitor-placeholder");
const playBtn = $("play-btn");
const projectNameInput = $("project-name");
const filenameInput = $("filename-input");
const durationInput = $("duration-input");
const loopCountInput = $("loopcount-input");
const loopSection = $("loop-section");
const stitchSection = $("stitch-section");
const stitchToggle = $("stitch-toggle");
const sourceAudioSection = $("source-audio-section");
const loopRadios = () => document.querySelectorAll('input[name="loop_mode"]');
const sourceAudioValue = () => document.querySelector('input[name="source_audio"]:checked')?.value || "keep";
const resolutionInput = $("resolution-input");
const fpsInput = $("fps-input");
const aspectInput = $("aspect-input");
const qualityValue = () => document.querySelector('#quality-toggle .quality-btn.active')?.dataset.quality || "high";
const fitValue = () => document.querySelector('#fit-toggle .fit-btn.active')?.dataset.fit || "letterbox";
const trimInInput = $("trim-in");
const trimOutInput = $("trim-out");
const round1 = (n) => Math.round(n * 10) / 10;
const selectedMedia = () => state.media.find((x) => x.id === state.selectedId) || null;
function effDuration(m) {
  if (!m || m.kind !== "video" || m.duration == null) return m ? (m.duration || 0) : 0;
  const s = m.trimIn || 0;
  const e = m.trimOut != null ? m.trimOut : m.duration;
  return Math.max(0.05, e - s);
}

/* Dedicated audio element for previewing audio-only files */
const audioEl = new Audio();
audioEl.preload = "metadata";
let activeEl = null; // the element currently driving the transport

/* ---------- helpers ---------- */
function kindOf(file) {
  const type = (file.type || "").toLowerCase();
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (type.startsWith("video/") || VIDEO_EXT.includes(ext)) return "video";
  if (type.startsWith("image/") || IMAGE_EXT.includes(ext)) return "image";
  if (type.startsWith("audio/") || AUDIO_EXT.includes(ext)) return "audio";
  return null;
}

function videos() { return state.media.filter((m) => m.kind === "video"); }
function image() { return state.media.find((m) => m.kind === "image") || null; }
function audio() { return state.media.find((m) => m.kind === "audio") || null; }

function fmtTC(sec) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  const ms = Math.floor((sec - Math.floor(sec)) * 1000);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
}

function fmtSize(bytes) {
  if (!bytes) return "—";
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(bytes / 1024).toFixed(0)} KB`;
}

/* ---------- toast ---------- */
let toastTimer = null;
function toast(msg, type = "info", { spinner = false, sticky = false, progress = null } = {}) {
  const el = $("toast");
  const existingLink = document.getElementById("toast-download");
  if (existingLink) existingLink.remove();
  $("toast-msg").textContent = msg;
  $("toast-spinner").classList.toggle("hidden", !spinner);
  $("toast-icon").classList.toggle("hidden", spinner);
  $("toast-icon").textContent = type === "error" ? "error" : type === "success" ? "check_circle" : "info";
  setToastProgress(progress);
  el.className = `fixed bottom-5 left-1/2 -translate-x-1/2 z-[60] show toast-${type}`;
  clearTimeout(toastTimer);
  if (!sticky) toastTimer = setTimeout(() => el.classList.remove("show"), 4200);
}
function hideToast() { clearTimeout(toastTimer); $("toast").classList.remove("show"); }

function setToastProgress(progress) {
  const wrap = $("toast-progress-wrap");
  const bar = $("toast-progress-bar");
  const pctEl = $("toast-pct");
  if (progress == null || !isFinite(progress)) {
    wrap.classList.add("hidden");
    pctEl.classList.add("hidden");
    bar.style.width = "0%";
    return;
  }
  const pct = Math.max(0, Math.min(100, Number(progress)));
  wrap.classList.remove("hidden");
  pctEl.classList.remove("hidden");
  bar.style.width = `${pct}%`;
  pctEl.textContent = `${Math.round(pct)}%`;
}

/* ---------- media management ---------- */
function addMedia(file, kind) {
  const item = {
    id: `m${++uid}`,
    file,
    kind,
    url: URL.createObjectURL(file),
    name: file.name,
    size: file.size,
    duration: null,
    width: null,
    height: null,
    trimIn: null,   // seconds; null = from start
    trimOut: null,  // seconds; null = to end
  };
  state.media.push(item);
  loadMeta(item);
  return item;
}

function removeKind(kind) {
  state.media = state.media.filter((m) => {
    if (m.kind === kind) { URL.revokeObjectURL(m.url); return false; }
    return true;
  });
}

function removeMedia(id) {
  const m = state.media.find((x) => x.id === id);
  if (m) URL.revokeObjectURL(m.url);
  state.media = state.media.filter((x) => x.id !== id);
  if (state.selectedId === id) {
    stopPlayback();
    state.selectedId = state.media[0]?.id || null;
  }
  renderAll();
  if (state.selectedId) selectMedia(state.selectedId, false);
  else clearMonitor();
}

/** Reorder a video among other videos. ``place`` is "before" or "after" targetId. */
function reorderVideo(dragId, targetId, place = "before") {
  if (!dragId || dragId === targetId) return false;
  const drag = state.media.find((m) => m.id === dragId);
  const target = state.media.find((m) => m.id === targetId);
  if (!drag || drag.kind !== "video" || !target || target.kind !== "video") return false;

  const without = state.media.filter((m) => m.id !== dragId);
  let insertAt = without.findIndex((m) => m.id === targetId);
  if (insertAt < 0) return false;
  if (place === "after") insertAt += 1;
  without.splice(insertAt, 0, drag);
  state.media = without;
  return true;
}

function videoOrderIndex(id) {
  return videos().findIndex((m) => m.id === id);
}

function loadMeta(item) {
  if (item.kind === "image") {
    const img = new Image();
    img.onload = () => { item.width = img.naturalWidth; item.height = img.naturalHeight; renderAll(); };
    img.src = item.url;
    return;
  }
  const el = document.createElement(item.kind === "video" ? "video" : "audio");
  el.preload = "metadata";
  el.onloadedmetadata = () => {
    item.duration = el.duration;
    if (item.kind === "video") { item.width = el.videoWidth; item.height = el.videoHeight; }
    renderAll();
  };
  el.src = item.url;
}

function addFiles(fileList) {
  const files = Array.from(fileList || []).filter(Boolean);
  if (!files.length) return;
  const incoming = files.map((f) => ({ f, kind: kindOf(f) }));
  const hasIncomingVideo = incoming.some((x) => x.kind === "video");

  let firstNew = null;
  for (const { f, kind } of incoming) {
    if (!kind) { toast(`Unsupported file: ${f.name}`, "error"); continue; }
    if (kind === "video") {
      removeKind("image");                 // video and image are mutually exclusive
      firstNew = addMedia(f, "video");
    } else if (kind === "image") {
      if (hasIncomingVideo || videos().length) { toast("Using video(s) — still image skipped.", "info"); continue; }
      removeKind("image");
      firstNew = addMedia(f, "image");
    } else if (kind === "audio") {
      removeKind("audio");                  // single soundtrack
      firstNew = addMedia(f, "audio");
    }
  }
  if (firstNew) { state.selectedId = firstNew.id; }
  renderAll();
  if (state.selectedId) selectMedia(state.selectedId, false);
}

function clearAll() {
  stopPlayback();
  state.media.forEach((m) => URL.revokeObjectURL(m.url));
  state.media = [];
  state.selectedId = null;
  clearMonitor();
  renderAll();
  toast("Cleared all media.", "info");
}

/** Reset the program monitor to the empty placeholder state. */
function clearMonitor() {
  stopPlayback();
  activeEl = null;
  try { monitorVideo.pause(); } catch (e) {}
  monitorVideo.removeAttribute("src");
  monitorVideo.load();
  monitorImage.removeAttribute("src");
  try { audioEl.pause(); } catch (e) {}
  audioEl.removeAttribute("src");

  monitorVideo.classList.add("hidden");
  monitorImage.classList.add("hidden");
  monitorAudio.classList.add("hidden");
  monitorAudio.classList.remove("flex");
  monitorPlaceholder.classList.remove("hidden");

  $("monitor-source").textContent = "No clip selected";
  $("monitor-kind").textContent = "—";
  $("tc-current").textContent = "00:00.000";
  $("tc-total").textContent = "00:00.000";
  playBtn.disabled = true;
  setPlayIcon(false);
}

/* ---------- rendering ---------- */
function renderAll() {
  renderBin();
  renderTimeline();
  renderInfo();
  renderInspectorState();
  renderTrimState();
  renderHeader();
}

function renderBin() {
  const items = state.media.filter((m) => state.filter === "all" || m.kind === state.filter);
  $("count-all").textContent = state.media.length;
  binEmpty.classList.toggle("hidden", state.media.length > 0);
  binGrid.classList.toggle("hidden", state.media.length === 0);
  binGrid.innerHTML = "";
  const canReorder = videos().length >= 2;

  for (const m of items) {
    const card = document.createElement("div");
    card.className = `bin-card${m.id === state.selectedId ? " selected" : ""}${m.kind === "video" && canReorder ? " reorderable" : ""}`;
    card.dataset.id = m.id;
    card.dataset.kind = m.kind;
    if (m.kind === "video" && canReorder) {
      card.draggable = true;
      card.title = "Drag to reorder play order";
    }

    let thumbInner;
    if (m.kind === "image") thumbInner = `<img src="${m.url}" alt="">`;
    else if (m.kind === "video") thumbInner = `<video src="${m.url}" muted preload="metadata"></video>`;
    else thumbInner = `<span class="material-symbols-outlined text-secondary-fixed-dim text-[28px]">graphic_eq</span>`;

    const dur = m.duration != null ? fmtTC(m.duration) : (m.kind === "image" ? "still" : "…");
    const order = m.kind === "video" && canReorder ? videoOrderIndex(m.id) + 1 : 0;
    const orderBadge = order
      ? `<span class="order-badge" title="Play order">${order}</span>`
      : "";
    card.innerHTML = `
      <div class="thumb">
        ${thumbInner}
        <span class="kind-badge kind-${m.kind}">${m.kind}</span>
        ${orderBadge}
        <span class="dur-badge">${dur}</span>
        <button class="remove-btn" title="Remove" data-remove="${m.id}"><span class="material-symbols-outlined text-[13px]">close</span></button>
        <div class="selected-check"><span class="material-symbols-outlined text-primary-container text-[22px] drop-shadow">check_circle</span></div>
      </div>
      <div class="meta">
        <span class="block font-label-mono-sm text-[11px] truncate ${m.id === state.selectedId ? "text-primary-container font-semibold" : "text-on-surface"}">${m.name}</span>
        <span class="block font-body-sm text-[10px] text-on-surface-variant">${m.width && m.height ? `${m.width}×${m.height}` : fmtSize(m.size)}</span>
      </div>`;
    binGrid.appendChild(card);
  }
}

function projectDuration() {
  const vids = videos();
  const vidTotal = vids.reduce((a, m) => a + effDuration(m), 0);
  const aud = audio();
  const audDur = aud ? aud.duration || 0 : 0;
  const img = image();
  const base = img ? audDur : Math.max(vidTotal, audDur);
  return base || 0;
}

function renderTimeline() {
  const v1 = $("track-v1");
  const a1 = $("track-a1");
  const vids = videos();
  const img = image();
  v1.innerHTML = "";
  a1.innerHTML = "";

  // V1 — scale by source duration so trimmed clips visibly shrink (edge-drag works).
  $("v1-empty").classList.toggle("hidden", vids.length > 0 || !!img);
  if (img) {
    v1.appendChild(clipTile(img, 1, "still"));
  } else {
    const sourceTotal = vids.reduce((a, m) => a + (m.duration || 1), 0) || 1;
    let acc = 0;
    vids.forEach((m) => {
      const d = effDuration(m) || sourceTotal / vids.length;
      const tile = clipTile(m, d / sourceTotal, `${fmtTC(acc)}`);
      v1.appendChild(tile);
      acc += d;
    });
  }

  // A1
  const aud = audio();
  $("a1-empty").classList.toggle("hidden", !aud);
  if (aud) {
    const lane = document.createElement("div");
    lane.className = "wave-lane bin-card-none";
    lane.dataset.id = aud.id;
    lane.style.cursor = "pointer";
    if (aud.id === state.selectedId) { lane.style.outline = "2px solid #60a5fa"; lane.style.outlineOffset = "-2px"; }
    lane.innerHTML = `
      ${waveformSVG()}
      <div class="wave-label">
        <span class="material-symbols-outlined text-[13px] text-white">audiotrack</span>
        <span class="font-label-mono-xs text-[10px] text-white font-semibold truncate max-w-[220px]">${aud.name}</span>
      </div>
      <span class="absolute right-2 font-label-mono-xs text-[9px] text-white/90 bg-black/30 px-1 rounded">${aud.duration != null ? fmtTC(aud.duration) : "…"}</span>`;
    lane.addEventListener("click", () => selectMedia(aud.id));
    a1.appendChild(lane);
  }

  // ruler + totals (effective / export length)
  const total = projectDuration();
  $("deck-total").textContent = fmtTC(total);
  const ticks = $("ruler-ticks");
  ticks.innerHTML = "";
  const n = 7;
  for (let i = 0; i < n; i++) {
    const t = (total * i) / (n - 1);
    const span = document.createElement("span");
    span.className = "flex items-center gap-1";
    span.innerHTML = `<span class="h-2 w-px bg-outline-variant"></span>${fmtTC(t)}`;
    ticks.appendChild(span);
  }
}

function clipTile(m, flexRatio, label) {
  const el = document.createElement("div");
  const canReorder = m.kind === "video" && videos().length >= 2;
  el.className = `tl-clip${m.id === state.selectedId ? " selected" : ""}${canReorder ? " reorderable" : ""}`;
  el.style.flex = `0 0 ${Math.max(flexRatio * 100, 4)}%`;
  el.style.maxWidth = "100%";
  el.dataset.id = m.id;
  el.dataset.kind = m.kind;
  if (canReorder) {
    el.draggable = true;
    el.title = "Drag to reorder · edges trim In/Out";
  }
  const thumb = m.kind === "image"
    ? `<img class="tl-thumb" src="${m.url}" alt="">`
    : `<video class="tl-thumb" src="${m.url}" muted preload="metadata"></video>`;
  const durLabel = m.kind === "video" && m.duration != null
    ? ((m.trimIn != null || m.trimOut != null) ? fmtTC(effDuration(m)) : fmtTC(m.duration))
    : (m.duration != null ? fmtTC(m.duration) : label);
  const handles = m.kind === "video"
    ? `<div class="tl-handle tl-handle-in" data-trim="in" title="Drag to set In"></div>
       <div class="tl-handle tl-handle-out" data-trim="out" title="Drag to set Out"></div>`
    : "";
  const order = canReorder ? videoOrderIndex(m.id) + 1 : 0;
  const orderBadge = order ? `<span class="tl-order">${order}</span>` : "";
  el.innerHTML = `
    <div class="tl-check"></div>
    ${handles}
    ${orderBadge}
    <div class="relative z-10 flex items-center gap-1.5 pointer-events-none">
      ${thumb}
      <div class="flex flex-col overflow-hidden">
        <span class="font-label-mono-xs text-[10px] font-semibold truncate ${m.id === state.selectedId ? "text-primary-container" : "text-on-surface"}">${m.name}</span>
        <span class="tl-dur font-label-mono-xs text-[8px] text-on-surface-variant">${durLabel}</span>
      </div>
    </div>`;
  el.addEventListener("click", (e) => {
    if (e.target.closest(".tl-handle") || trimDrag.moved || clipReorder.moved) return;
    selectMedia(m.id);
  });
  if (m.kind === "video") {
    el.querySelectorAll(".tl-handle").forEach((h) => {
      h.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        // Don't let HTML5 reorder drag steal the trim gesture.
        el.draggable = false;
        startTrimDrag(m, h.dataset.trim, e, el);
      });
      h.addEventListener("pointerup", () => { if (canReorder) el.draggable = true; });
      h.addEventListener("pointercancel", () => { if (canReorder) el.draggable = true; });
    });
  }
  return el;
}

function waveformSVG() {
  // Deterministic pseudo-random waveform
  let path = "M0,23";
  let seed = 7;
  for (let x = 6; x <= 900; x += 6) {
    seed = (seed * 9301 + 49297) % 233280;
    const y = 6 + (seed / 233280) * 34;
    path += ` L${x},${y.toFixed(1)}`;
  }
  path += " L900,23 Z";
  return `<svg viewBox="0 0 900 46" preserveAspectRatio="none" fill="currentColor"><path d="${path}"></path></svg>
    <div class="absolute inset-x-0 top-1/2 -translate-y-1/2 h-px bg-white/20 pointer-events-none"></div>`;
}

function renderHeader() {
  const badge = $("sync-badge");
  const n = state.media.length;
  if (n === 0) {
    badge.innerHTML = `<span class="material-symbols-outlined text-outline text-[14px]">cloud_off</span><span>NO MEDIA</span>`;
  } else {
    badge.innerHTML = `<span class="material-symbols-outlined text-primary-container text-[14px]">cloud_done</span><span>${n} ITEM${n > 1 ? "S" : ""}</span>`;
  }
}

function renderInfo() {
  const m = state.media.find((x) => x.id === state.selectedId);
  const list = $("info-list");
  $("total-videos").textContent = videos().length;
  $("total-audio").textContent = audio() ? 1 : 0;
  if (!m) { list.innerHTML = `<p class="font-body-sm text-[11px] text-on-surface-variant">No clip selected.</p>`; return; }
  const rows = [
    ["Name", m.name],
    ["Type", m.kind.toUpperCase()],
    ["Duration", m.duration != null ? fmtTC(m.duration) : (m.kind === "image" ? "still" : "…")],
    ["Size", fmtSize(m.size)],
  ];
  if (m.width && m.height) rows.push(["Resolution", `${m.width}×${m.height}`]);
  list.innerHTML = rows.map(([k, v]) => `
    <div class="flex items-center justify-between gap-2 px-2 py-1 rounded bg-surface-container">
      <span class="font-label-mono-xs text-[9px] text-on-surface-variant uppercase tracking-widest">${k}</span>
      <span class="font-label-mono-sm text-[11px] text-on-surface truncate max-w-[130px]" title="${v}">${v}</span>
    </div>`).join("");
}

/* ---------- per-clip trim ---------- */
const trimDrag = {
  active: false,
  moved: false,
  mediaId: null,
  which: null,      // "in" | "out"
  startX: 0,
  startIn: 0,
  startOut: 0,
  pxPerSec: 1,
  tip: null,
};
const clipReorder = { dragId: null, moved: false };

function updateTrimLength(m) {
  const trimmed = m.trimIn != null || m.trimOut != null;
  $("trim-length").textContent = trimmed ? `trimmed · ${fmtTC(effDuration(m))}` : "full clip";
}

function renderTrimState() {
  const m = selectedMedia();
  const isVideo = !!m && m.kind === "video";
  $("trim-controls").classList.toggle("hidden", !isVideo);
  $("trim-hint").classList.toggle("hidden", isVideo);
  $("trim-clip-name").textContent = isVideo ? m.name : "no clip";
  if (!isVideo) return;
  trimInInput.value = m.trimIn != null ? round1(m.trimIn) : "";
  trimOutInput.value = m.trimOut != null ? round1(m.trimOut) : "";
  updateTrimLength(m);
}

/** Clamp and store in/out on a media item; syncs inspector when that clip is selected. */
function applyTrimValues(m, nextIn, nextOut, { refreshTimeline = true } = {}) {
  if (!m || m.kind !== "video") return;
  const dur = m.duration || 0;
  let tin = nextIn;
  let tout = nextOut;
  if (tin == null || !isFinite(tin) || tin <= 0) tin = null;
  else tin = Math.min(tin, Math.max(0, dur - 0.05));
  if (tout == null || !isFinite(tout) || tout <= 0) tout = null;
  else tout = dur ? Math.min(tout, dur) : tout;
  if (tin != null && tout != null && tout <= tin + 0.05) {
    // Keep a tiny usable window when dragging edges toward each other.
    if (trimDrag.which === "in") tin = Math.max(0, tout - 0.1);
    else tout = Math.min(dur || tin + 0.1, tin + 0.1);
  }
  m.trimIn = tin != null && tin > 0 ? tin : null;
  m.trimOut = tout != null && tout > 0 && (!dur || tout < dur - 0.02) ? tout : null;
  if (m.id === state.selectedId) {
    trimInInput.value = m.trimIn != null ? round1(m.trimIn) : "";
    trimOutInput.value = m.trimOut != null ? round1(m.trimOut) : "";
    updateTrimLength(m);
  }
  if (refreshTimeline) renderTimeline();
}

function commitTrim() {
  const m = selectedMedia();
  if (!m || m.kind !== "video") return;
  const ti = parseFloat(trimInInput.value);
  const to = parseFloat(trimOutInput.value);
  applyTrimValues(m, isFinite(ti) ? ti : null, isFinite(to) ? to : null);
}

function setTrimFromPlayhead(which) {
  const m = selectedMedia();
  if (!m || m.kind !== "video") return;
  const t = round1(monitorVideo.currentTime || 0);
  (which === "in" ? trimInInput : trimOutInput).value = t;
  commitTrim();
}

function ensureTrimTip() {
  let tip = document.getElementById("trim-drag-tip");
  if (!tip) {
    tip = document.createElement("div");
    tip.id = "trim-drag-tip";
    document.body.appendChild(tip);
  }
  return tip;
}

function startTrimDrag(m, which, e, tileEl) {
  if (!m.duration) return;
  // Select the clip so the inspector Trim panel tracks the drag.
  if (state.selectedId !== m.id) selectMedia(m.id, false);

  const track = $("track-v1");
  const sourceTotal = videos().reduce((a, x) => a + (x.duration || 1), 0) || 1;
  const trackW = track.clientWidth || 1;
  const pxPerSec = trackW / sourceTotal;

  trimDrag.active = true;
  trimDrag.moved = false;
  trimDrag.mediaId = m.id;
  trimDrag.which = which;
  trimDrag.startX = e.clientX;
  trimDrag.startIn = m.trimIn || 0;
  trimDrag.startOut = m.trimOut != null ? m.trimOut : m.duration;
  trimDrag.pxPerSec = Math.max(pxPerSec, 0.001);

  // selectMedia may have re-rendered — grab the live tile.
  const liveTile = () => document.querySelector(`.tl-clip[data-id="${m.id}"]`);
  liveTile()?.classList.add("trimming");
  document.body.classList.add("tl-trimming");

  const tip = ensureTrimTip();
  tip.textContent = which === "in"
    ? `IN ${fmtTC(trimDrag.startIn)}`
    : `OUT ${fmtTC(trimDrag.startOut)}`;
  tip.style.left = `${e.clientX + 12}px`;
  tip.style.top = `${e.clientY - 28}px`;

  try { e.target.setPointerCapture(e.pointerId); } catch (_) {}

  /** Live resize without full timeline rebuild (keeps handles under the cursor). */
  function paintLive() {
    const vids = videos();
    const total = vids.reduce((a, x) => a + (x.duration || 1), 0) || 1;
    vids.forEach((clip) => {
      const el = document.querySelector(`.tl-clip[data-id="${clip.id}"]`);
      if (!el) return;
      el.style.flex = `0 0 ${Math.max((effDuration(clip) / total) * 100, 4)}%`;
      const durEl = el.querySelector(".tl-dur");
      if (durEl) durEl.textContent = fmtTC(effDuration(clip));
    });
    $("deck-total").textContent = fmtTC(projectDuration());
    liveTile()?.classList.add("trimming");
  }

  const onMove = (ev) => {
    if (!trimDrag.active || trimDrag.mediaId !== m.id) return;
    const dx = ev.clientX - trimDrag.startX;
    if (Math.abs(dx) > 2) trimDrag.moved = true;
    const dSec = dx / trimDrag.pxPerSec;
    if (which === "in") {
      applyTrimValues(m, round1(trimDrag.startIn + dSec), trimDrag.startOut, { refreshTimeline: false });
    } else {
      applyTrimValues(m, trimDrag.startIn, round1(trimDrag.startOut + dSec), { refreshTimeline: false });
    }
    paintLive();
    tip.textContent = which === "in"
      ? `IN ${fmtTC(m.trimIn || 0)}`
      : `OUT ${fmtTC(m.trimOut != null ? m.trimOut : m.duration)}`;
    tip.style.left = `${ev.clientX + 12}px`;
    tip.style.top = `${ev.clientY - 28}px`;
  };

  const onUp = () => {
    trimDrag.active = false;
    document.body.classList.remove("tl-trimming");
    tip.remove();
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onUp);
    renderTimeline();
    renderTrimState();
    // Ignore the click that follows pointerup after a drag.
    setTimeout(() => { trimDrag.moved = false; }, 0);
  };

  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
  window.addEventListener("pointercancel", onUp);
}

/* ---------- inspector state / validation ---------- */
function renderInspectorState() {
  const vids = videos();
  const singleVideoAndAudio = vids.length === 1 && !!audio();
  const multiVideo = vids.length >= 2;

  loopSection.classList.toggle("disabled-section", !singleVideoAndAudio);
  loopRadios().forEach((r) => {
    r.disabled = !singleVideoAndAudio;
    if (!singleVideoAndAudio) r.checked = false;
  });

  stitchSection.classList.toggle("hidden", !multiVideo);
  if (!multiVideo) stitchToggle.checked = false;

  // Source-audio choice only matters when there is video but no soundtrack file.
  const noExternalAudio = vids.length >= 1 && !audio();
  sourceAudioSection.classList.toggle("hidden", !noExternalAudio);

  // loop note
  const note = $("loop-note");
  if (singleVideoAndAudio) note.textContent = "Pick how the single video pairs with your audio.";
  else if (multiVideo) note.textContent = "Drag clips in the bin or timeline to set play order. Enable stitch to join once instead of looping to audio.";
  else if (noExternalAudio) note.textContent = "No soundtrack added — choose whether to keep the clip's audio or mute it.";
  else note.textContent = "Add one video + an audio file to unlock loop modes.";

  const v = validate();
  $("mode-badge").textContent = `Mode: ${v.mode}`;
  $("inspector-badge").textContent = v.mode;
  const enabled = state.media.length > 0;
  $("create-btn").disabled = !enabled;
  $("export-btn").disabled = !enabled;
}

function validate() {
  const vids = videos();
  const img = image();
  const aud = audio();
  const duration = durationInput.value.trim();
  const loopCount = loopCountInput.value.trim();
  const loopMode = document.querySelector('input[name="loop_mode"]:checked');
  const stitch = vids.length >= 2 && stitchToggle.checked;

  if (!vids.length && !img && !aud) return { ok: false, mode: "idle", msg: "Add video(s), a still image, or audio." };
  if (vids.length && img) return { ok: false, mode: "conflict", msg: "Use video(s) or a still image, not both." };

  let mode = "merge";
  if (img && aud) mode = "image + audio";
  else if (img) mode = "still image";
  else if (vids.length >= 2) mode = stitch ? "stitch" : "sequence loop";
  else if (vids.length === 1 && aud) mode = "video + audio";
  else if (vids.length === 1) mode = "single video";
  else if (aud) mode = "audio only";

  if (img && !aud && !duration) return { ok: false, mode, msg: "Provide a target duration (minutes) for a still image." };
  if (vids.length === 1 && aud && !loopMode) return { ok: false, mode, msg: "Choose a loop mode (video / audio / both)." };
  if (stitch && vids.length < 2) return { ok: false, mode, msg: "Add at least two videos to stitch." };

  return { ok: true, mode, msg: "" };
}

/* ---------- monitor / transport ---------- */
function stopPlayback() {
  if (activeEl) { try { activeEl.pause(); } catch (e) {} }
  setPlayIcon(false);
}

function selectMedia(id, autoPreview = true) {
  state.selectedId = id;
  const m = state.media.find((x) => x.id === id);
  renderBin();
  renderTimeline();
  renderInfo();
  renderTrimState();
  if (!m) return;

  stopPlayback();
  monitorVideo.classList.add("hidden");
  monitorImage.classList.add("hidden");
  monitorAudio.classList.add("hidden");
  monitorAudio.classList.remove("flex");
  monitorPlaceholder.classList.add("hidden");
  $("monitor-source").textContent = m.name;
  $("monitor-kind").textContent = m.kind;

  if (m.kind === "video") {
    monitorVideo.src = m.url;
    monitorVideo.muted = state.muted;
    monitorVideo.classList.remove("hidden");
    activeEl = monitorVideo;
    playBtn.disabled = false;
  } else if (m.kind === "image") {
    monitorImage.src = m.url;
    monitorImage.classList.remove("hidden");
    activeEl = null;
    playBtn.disabled = true;
    $("tc-current").textContent = fmtTC(0);
    $("tc-total").textContent = "still";
  } else {
    $("monitor-audio-name").textContent = m.name;
    monitorAudio.classList.remove("hidden");
    monitorAudio.classList.add("flex");
    audioEl.src = m.url;
    audioEl.muted = state.muted;
    activeEl = audioEl;
    playBtn.disabled = false;
  }
  if (activeEl) {
    $("tc-current").textContent = fmtTC(0);
    $("tc-total").textContent = fmtTC(m.duration || 0);
  }
}

function setPlayIcon(playing) {
  playBtn.querySelector(".material-symbols-outlined").textContent = playing ? "pause" : "play_arrow";
}

function togglePlay() {
  if (!activeEl) return;
  if (activeEl.paused) { activeEl.play(); setPlayIcon(true); }
  else { activeEl.pause(); setPlayIcon(false); }
}

function bindTransportEvents(el) {
  el.addEventListener("timeupdate", () => { if (el === activeEl) $("tc-current").textContent = fmtTC(el.currentTime); });
  el.addEventListener("loadedmetadata", () => { if (el === activeEl) $("tc-total").textContent = fmtTC(el.duration); });
  el.addEventListener("ended", () => { if (el === activeEl) setPlayIcon(false); });
  el.addEventListener("play", () => { if (el === activeEl) setPlayIcon(true); });
  el.addEventListener("pause", () => { if (el === activeEl) setPlayIcon(false); });
}
bindTransportEvents(monitorVideo);
bindTransportEvents(audioEl);

/* ---------- submit ---------- */
async function submitMerge() {
  const v = validate();
  if (!v.ok) { toast(v.msg, "error"); return; }

  const vids = videos();
  const img = image();
  const aud = audio();
  const loopMode = document.querySelector('input[name="loop_mode"]:checked');
  const stitch = vids.length >= 2 && stitchToggle.checked;
  // Mute only applies when there is video but no external soundtrack.
  const mute = vids.length >= 1 && !aud && sourceAudioValue() === "mute";

  const fd = new FormData();
  vids.forEach((m) => fd.append("videos", m.file));
  if (img) fd.append("image", img.file);
  if (aud) fd.append("audio", aud.file);
  fd.append("duration_minutes", durationInput.value.trim());
  fd.append("loop_count", loopCountInput.value.trim());
  fd.append("output_filename", filenameInput.value.trim() || "my-video.mp4");
  if (loopMode) fd.append("loop_mode", loopMode.value);
  fd.append("resolution", resolutionInput.value || "original");
  fd.append("fps", fpsInput.value || "original");
  fd.append("quality", qualityValue());
  fd.append("aspect", aspectInput.value || "original");
  fd.append("fit", fitValue());
  // Per-clip trims aligned to the videos order (only sent if any are set).
  if (vids.some((m) => (m.trimIn && m.trimIn > 0) || (m.trimOut && m.trimOut > 0))) {
    const trims = vids.map((m) => ({ in: m.trimIn || 0, out: m.trimOut || null }));
    fd.append("trims", JSON.stringify(trims));
  }
  fd.append("mute", mute ? "1" : "0");
  if (stitch) {
    fd.append("stitch", "1");
    fd.append("keep_source_audio", mute ? "0" : "1");
  }

  $("create-btn").disabled = true;
  $("export-btn").disabled = true;
  toast("Uploading media…", "info", { spinner: true, sticky: true });

  let jobId;
  try {
    const res = await fetch("/api/merge", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) { toast(data.error || "Could not start the render.", "error"); reenableButtons(); return; }
    jobId = data.job_id;
  } catch (e) {
    toast("Could not reach the server. Is the app running?", "error");
    reenableButtons();
    return;
  }
  pollJob(jobId);
}

function reenableButtons() {
  renderInspectorState();
}

function pollJob(jobId) {
  const poll = async () => {
    let data;
    try {
      const res = await fetch(`/api/job/${jobId}`);
      data = await res.json();
      if (!res.ok) { toast(data.error || "Lost track of the render job.", "error"); reenableButtons(); return; }
    } catch (e) {
      setTimeout(poll, 3000); // transient network hiccup — keep trying
      return;
    }
    if (data.status === "queued") {
      toast("Queued — waiting for a free render worker…", "info", { spinner: true, sticky: true, progress: 0 });
      setTimeout(poll, 1500);
    } else if (data.status === "processing") {
      const pct = data.progress != null ? Number(data.progress) : 0;
      const msg = data.message || (pct > 0 ? `Rendering… ${Math.round(pct)}%` : "Rendering…");
      toast(msg, "info", { spinner: true, sticky: true, progress: pct });
      setTimeout(poll, 800);
    } else if (data.status === "done") {
      setToastProgress(100);
      showDownload(data);
      reenableButtons();
    } else if (data.status === "error") {
      toast(data.error || "Rendering failed.", "error", { sticky: true });
      reenableButtons();
    } else {
      setTimeout(poll, 2000);
    }
  };
  poll();
}

function showDownload(data) {
  const el = $("toast");
  clearTimeout(toastTimer);
  $("toast-spinner").classList.add("hidden");
  $("toast-icon").classList.remove("hidden");
  $("toast-icon").textContent = "check_circle";
  $("toast-msg").textContent = `Ready: ${data.filename}`;
  setToastProgress(null);
  let link = document.getElementById("toast-download");
  if (!link) {
    link = document.createElement("a");
    link.id = "toast-download";
    link.className = "ml-1 flex items-center gap-1 px-2.5 py-1 rounded-lg bg-primary-container text-on-primary font-action-button text-[12px] font-semibold hover:brightness-110";
    link.innerHTML = '<span class="material-symbols-outlined text-[16px]">download</span>Download';
    $("toast-row").appendChild(link);
  }
  link.href = data.download_url;
  link.setAttribute("download", data.filename || "");
  el.className = "fixed bottom-5 left-1/2 -translate-x-1/2 z-[60] show toast-success";
  try { link.click(); } catch (e) {}  // best-effort auto-start; button stays as fallback
}

/* ---------- wiring ---------- */
function openPicker() { importInput.click(); }

/* ---------- clip reorder (bin + timeline) ---------- */
function clearDropIndicators() {
  document.querySelectorAll(".drop-before, .drop-after").forEach((el) => {
    el.classList.remove("drop-before", "drop-after");
  });
}

function clearReorderDrag() {
  clearDropIndicators();
  document.querySelectorAll(".is-dragging").forEach((el) => el.classList.remove("is-dragging"));
}

function dropPlaceFor(el, clientX, clientY) {
  const rect = el.getBoundingClientRect();
  // Timeline is horizontal; bin is a 2-col grid — use the dominant axis.
  if (el.classList.contains("tl-clip")) {
    return clientX < rect.left + rect.width / 2 ? "before" : "after";
  }
  return clientY < rect.top + rect.height / 2 ? "before" : "after";
}

function bindReorderSurface(root, itemSelector) {
  root.addEventListener("dragstart", (e) => {
    if (trimDrag.active) { e.preventDefault(); return; }
    const item = e.target.closest(itemSelector);
    if (!item || !item.draggable || item.dataset.kind !== "video") return;
    if (e.target.closest(".tl-handle, .remove-btn")) { e.preventDefault(); return; }
    clipReorder.dragId = item.dataset.id;
    clipReorder.moved = false;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", item.dataset.id);
    requestAnimationFrame(() => item.classList.add("is-dragging"));
  });

  root.addEventListener("dragend", () => {
    clearReorderDrag();
    clipReorder.dragId = null;
    setTimeout(() => { clipReorder.moved = false; }, 0);
  });

  root.addEventListener("dragover", (e) => {
    if (!clipReorder.dragId) return;
    const item = e.target.closest(itemSelector);
    if (!item || item.dataset.kind !== "video" || item.dataset.id === clipReorder.dragId) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    clearDropIndicators();
    const place = dropPlaceFor(item, e.clientX, e.clientY);
    item.classList.add(place === "before" ? "drop-before" : "drop-after");
  });

  root.addEventListener("dragleave", (e) => {
    const item = e.target.closest(itemSelector);
    if (!item) return;
    if (item.contains(e.relatedTarget)) return;
    item.classList.remove("drop-before", "drop-after");
  });

  root.addEventListener("drop", (e) => {
    if (!clipReorder.dragId) return;
    const item = e.target.closest(itemSelector);
    if (!item || item.dataset.kind !== "video") return;
    e.preventDefault();
    const place = dropPlaceFor(item, e.clientX, e.clientY);
    const changed = reorderVideo(clipReorder.dragId, item.dataset.id, place);
    clearReorderDrag();
    clipReorder.dragId = null;
    if (changed) {
      clipReorder.moved = true;
      renderAll();
      if (state.selectedId) selectMedia(state.selectedId, false);
    }
  });
}

bindReorderSurface(binGrid, ".bin-card");
bindReorderSurface($("track-v1"), ".tl-clip");

importInput.addEventListener("change", () => { addFiles(importInput.files); importInput.value = ""; });
$("import-btn").addEventListener("click", openPicker);
$("shelf-import").addEventListener("click", openPicker);
binEmpty.addEventListener("click", openPicker);

const dz = $("bin-dropzone");
dz.addEventListener("click", openPicker);
["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("border-primary-container"); }));
["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("border-primary-container"); }));
dz.addEventListener("drop", (e) => { if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files); });

// Whole page drag/drop
["dragover"].forEach((ev) => window.addEventListener(ev, (e) => e.preventDefault()));
window.addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.target.closest("#bin-dropzone")) return; // handled above
  if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
});

// Bin card clicks (select / remove)
binGrid.addEventListener("click", (e) => {
  const rm = e.target.closest("[data-remove]");
  if (rm) { e.stopPropagation(); removeMedia(rm.dataset.remove); return; }
  const card = e.target.closest(".bin-card");
  if (card) selectMedia(card.dataset.id);
});

// Filter chips
$("bin-filters").addEventListener("click", (e) => {
  const chip = e.target.closest(".filter-chip");
  if (!chip) return;
  state.filter = chip.dataset.filter;
  document.querySelectorAll(".filter-chip").forEach((c) => c.classList.toggle("active", c === chip));
  renderBin();
});

// Inspector tabs
$("inspector-tabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".tab-btn");
  if (!btn) return;
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
  document.querySelectorAll("[data-panel]").forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== btn.dataset.tab));
});

// Quality vs Speed toggle
const QUALITY_NOTES = {
  draft: "Fastest render, smaller file — great for quick previews.",
  balanced: "Solid quality with a noticeably faster render.",
  high: "Best quality (visually lossless). Slower render, larger file.",
};
function renderQualityNote() {
  const note = $("quality-note");
  if (note) note.textContent = QUALITY_NOTES[qualityValue()] || "";
}
$("quality-toggle").addEventListener("click", (e) => {
  const btn = e.target.closest(".quality-btn");
  if (!btn) return;
  document.querySelectorAll("#quality-toggle .quality-btn")
    .forEach((b) => b.classList.toggle("active", b === btn));
  renderQualityNote();
});

// Aspect / orientation + fit
const FIT_NOTES = {
  letterbox: "Fits the whole frame with black bars — nothing is cut off.",
  crop: "Fills the frame and crops the overflow — no bars.",
};
function renderAspectState() {
  const value = aspectInput.value || "original";
  const reframed = value !== "original";
  $("fit-row").classList.toggle("hidden", !reframed);
  const note = $("fit-note");
  if (note) note.textContent = reframed ? (FIT_NOTES[fitValue()] || "") : "";
  document.querySelectorAll("#preview-aspect .preview-aspect-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.aspect === value);
  });
}
aspectInput.addEventListener("change", renderAspectState);
$("fit-toggle").addEventListener("click", (e) => {
  const btn = e.target.closest(".fit-btn");
  if (!btn) return;
  document.querySelectorAll("#fit-toggle .fit-btn")
    .forEach((b) => b.classList.toggle("active", b === btn));
  renderAspectState();
});
$("preview-aspect").addEventListener("click", (e) => {
  const btn = e.target.closest(".preview-aspect-btn");
  if (!btn) return;
  // Click active again → back to original (keep source).
  const next = (aspectInput.value === btn.dataset.aspect) ? "original" : btn.dataset.aspect;
  aspectInput.value = next;
  renderAspectState();
});

// Per-clip trim
trimInInput.addEventListener("change", commitTrim);
trimOutInput.addEventListener("change", commitTrim);
$("trim-in-set").addEventListener("click", () => setTrimFromPlayhead("in"));
$("trim-out-set").addEventListener("click", () => setTrimFromPlayhead("out"));
$("trim-clear").addEventListener("click", () => {
  const m = selectedMedia();
  if (!m) return;
  m.trimIn = null;
  m.trimOut = null;
  renderTrimState();
  renderTimeline();
});

// Transport
playBtn.addEventListener("click", togglePlay);
$("seek-start").addEventListener("click", () => { if (activeEl) activeEl.currentTime = 0; });
$("seek-end").addEventListener("click", () => { if (activeEl && isFinite(activeEl.duration)) activeEl.currentTime = activeEl.duration; });
$("seek-back").addEventListener("click", () => { if (activeEl) activeEl.currentTime = Math.max(0, activeEl.currentTime - 5); });
$("seek-fwd").addEventListener("click", () => { if (activeEl) activeEl.currentTime = Math.min(activeEl.duration || 0, activeEl.currentTime + 5); });
$("mute-btn").addEventListener("click", () => {
  state.muted = !state.muted;
  monitorVideo.muted = state.muted;
  audioEl.muted = state.muted;
  $("mute-btn").querySelector(".material-symbols-outlined").textContent = state.muted ? "volume_off" : "volume_up";
});

// Filename sync (two inputs)
function syncName(from, to) { to.value = from.value; }
projectNameInput.addEventListener("input", () => syncName(projectNameInput, filenameInput));
filenameInput.addEventListener("input", () => syncName(filenameInput, projectNameInput));
filenameInput.value = projectNameInput.value;

// Settings that affect validation
[durationInput, loopCountInput, stitchToggle].forEach((el) => el.addEventListener("input", renderInspectorState));
document.addEventListener("change", (e) => {
  if (e.target.name === "loop_mode" || e.target === stitchToggle) renderInspectorState();
});

// Create / export / clear / reset
$("create-btn").addEventListener("click", submitMerge);
$("export-btn").addEventListener("click", submitMerge);
$("clear-all-btn").addEventListener("click", clearAll);
$("shelf-clear").addEventListener("click", clearAll);
$("reset-btn").addEventListener("click", () => {
  durationInput.value = "";
  loopCountInput.value = "";
  loopRadios().forEach((r) => (r.checked = false));
  stitchToggle.checked = false;
  const keepRadio = document.querySelector('input[name="source_audio"][value="keep"]');
  if (keepRadio) keepRadio.checked = true;
  resolutionInput.value = "original";
  fpsInput.value = "original";
  aspectInput.value = "original";
  document.querySelectorAll("#quality-toggle .quality-btn")
    .forEach((b) => b.classList.toggle("active", b.dataset.quality === "high"));
  document.querySelectorAll("#fit-toggle .fit-btn")
    .forEach((b) => b.classList.toggle("active", b.dataset.fit === "letterbox"));
  renderQualityNote();
  renderAspectState();
  renderInspectorState();
  toast("Settings reset.", "info");
});

// Theme toggle
$("theme-btn").addEventListener("click", () => {
  const dark = document.documentElement.classList.toggle("dark");
  $("theme-btn").querySelector(".material-symbols-outlined").textContent = dark ? "dark_mode" : "light_mode";
});

/* ---------- accent color switch ---------- */
const DEFAULT_ACCENT = "#00e5ff";
const ACCENT_PRESETS = [
  { name: "Cyan", value: "#00e5ff" },
  { name: "Blue", value: "#3b82f6" },
  { name: "Violet", value: "#8b5cf6" },
  { name: "Emerald", value: "#10b981" },
  { name: "Amber", value: "#f59e0b" },
  { name: "Rose", value: "#f43f5e" },
];
const ACCENT_KEY = "cf-accent";

// Pick black-ish or white text for readable contrast on the accent.
function contrastOn(hex) {
  const c = hex.replace("#", "");
  if (c.length < 6) return "#0c0e11";
  const r = parseInt(c.slice(0, 2), 16);
  const g = parseInt(c.slice(2, 4), 16);
  const b = parseInt(c.slice(4, 6), 16);
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.55 ? "#0c0e11" : "#ffffff";
}

function applyAccent(hex, persist = true) {
  const root = document.documentElement;
  root.style.setProperty("--accent", hex);
  root.style.setProperty("--on-accent", contrastOn(hex));
  if (persist) { try { localStorage.setItem(ACCENT_KEY, hex); } catch (e) {} }
  const custom = $("accent-custom");
  if (custom) custom.value = hex;
  document.querySelectorAll("#accent-swatches [data-accent]").forEach((el) => {
    el.classList.toggle("ring-2", el.dataset.accent.toLowerCase() === hex.toLowerCase());
  });
}

function buildAccentSwatches() {
  const wrap = $("accent-swatches");
  wrap.innerHTML = "";
  ACCENT_PRESETS.forEach((p) => {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.accent = p.value;
    b.title = p.name;
    b.className = "w-7 h-7 rounded-full ring-offset-2 ring-offset-surface-container-high ring-white transition-transform hover:scale-110";
    b.style.background = p.value;
    b.addEventListener("click", () => applyAccent(p.value));
    wrap.appendChild(b);
  });
}

const accentBtn = $("accent-btn");
const accentMenu = $("accent-menu");
accentBtn.addEventListener("click", (e) => { e.stopPropagation(); accentMenu.classList.toggle("hidden"); });
document.addEventListener("click", (e) => {
  if (!accentMenu.classList.contains("hidden") &&
      !accentMenu.contains(e.target) && !accentBtn.contains(e.target)) {
    accentMenu.classList.add("hidden");
  }
});
$("accent-custom").addEventListener("input", (e) => applyAccent(e.target.value));
$("accent-reset").addEventListener("click", () => applyAccent(DEFAULT_ACCENT));

buildAccentSwatches();
let savedAccent = DEFAULT_ACCENT;
try { savedAccent = localStorage.getItem(ACCENT_KEY) || DEFAULT_ACCENT; } catch (e) {}
applyAccent(savedAccent, false);
renderQualityNote();
renderAspectState();

// Keyboard: space toggles play
document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) {
    e.preventDefault();
    togglePlay();
  }
});

renderAll();
