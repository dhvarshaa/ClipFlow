# ClipFlow — Product & Engineering Plan

This is a living plan. It has three parts:
1. **Deployment stages** (infrastructure maturity) — already underway.
2. **Feature roadmap** (what the product does) — new.
3. **UI direction** (how it looks) — new, based on the latest mockup.
4. **Accent color switch** — a small, high-value UI feature spec.

> Status today: the app is a **one-shot merge tool** (upload video(s)/image + audio →
> loop/stitch → single ffmpeg render → download). It is deployed on a Google Cloud VM
> via Docker (web + worker). The mockup below is aspirational — a full non-destructive
> editor — so features are phased by how much of that engine they require.

---

## 1. Deployment stages (unchanged)

- **Stage 1 — make it deployable (first hundreds):** async job queue + object storage +
  signed download URLs + gunicorn + Docker with ffmpeg + a worker or two. *(Done.)*
- **Stage 2 — scale to thousands:** Redis + RQ/Celery worker pool with autoscaling, media
  on S3/R2 + CDN, hardware-accelerated encoding, cleanup/quotas/auth.
- **Stage 3 — become a true editor:** timeline-JSON model, browser preview
  (Canvas/WebGL + Web Audio), proxy generation. Bigger build; only when moving beyond
  merge/loop into interactive editing.

---

## 2. Feature roadmap

Grouped by how much engine work they need, so we can ship value early.

### Tier A — Quick wins on the current one-shot merge (no timeline engine)
These extend the existing render pipeline; each is a bounded change.

- **Accent color switch** (see §4) — swap the cyan theme accent; persists per user. - done
- **Export presets** — resolution (720p/1080p/4K/original), fps, and a
  **Quality vs Speed** selector (Draft / Balanced / High) mapping to CRF + preset.
  Directly controls cost/render time. - done
- **Aspect / orientation** — 16:9, 9:16 (Shorts/Reels), 1:1, with letterbox/crop choice. - done
- **Per-clip trim (in/out)** before merge — set start/end on each bin clip. - done
- **Clip reordering** — drag clips in the bin/timeline to set play order for stitch/stage. - done
- **Per-clip + soundtrack volume** — gain sliders; **fade in/out** on the soundtrack.
- **Auto audio ducking** — lower music under a voiceover automatically.
- **Simple transitions** — crossfade/dissolve between stitched clips (duration control).
- **Overlay** — a watermark/logo image or a text title (position, size, opacity).
- **Live progress %** — parse ffmpeg progress so the status card shows a real bar/ETA,
  not just "processing".
- **Project save/load** — remember the last setup (localStorage now; per-account later).
- **Render history** — list recent outputs with re-download links (until retention purge).

### Tier B — Toward a real editor (needs the timeline-JSON model + preview)
These are the mockup's core; they depend on Stage 3 groundwork.

- **Multi-track timeline** — V2 overlay, V1 main video, A1 music, A2 dialogue lanes.
- **Editing tools** — Select (V), **Razor/blade split** (B), **Ripple** (R), **Snap** toggle.
- **Split at playhead**, trim handles, drag to move/reorder on the timeline.
- **Per-clip speed / retime** — 0.5×–2× with pitch-preserve option.
- **Keyframes** — animatable opacity/scale/position and audio gain (diamond nodes).
- **Color grading (LUT)** — apply a look + intensity per clip (mockup "Color LUT" tab).
- **Transform** — scale, position, rotation, opacity per clip (Inspector "Video" tab).
- **Real-time preview** — Canvas/WebGL compositing + Web Audio mixing, low-res proxies
  for smooth scrubbing; render only bakes the final at Export.
- **Track controls** — mute/solo/lock, visibility per lane.

### Tier C — Platform / product
- **Accounts & auth**, per-user projects and quotas.
- **Rate limiting & usage dashboard** (protects render cost).
- **Shareable output links** (already have signed URLs — expose a "copy link").
- **Templates / presets** — starter timelines for common formats.
- **Team/collaboration** (much later).

### Suggested near-term order
1. Accent color switch (small, visible, unblocks theming).
2. Export presets (quality/speed) + aspect/orientation.
3. Live progress %.
4. Per-clip trim + reorder + volume/fades + ducking.
5. Overlay (logo/text) and crossfade transitions.
6. Then evaluate Stage 3 (timeline engine) if the product is heading to a real editor.

---

## 3. UI direction (from the latest mockup)

Keep the current ClipFlow dark aesthetic; grow the layout toward the mockup as Tier B lands.

- **Top bar:** brand + editable project name + autosave indicator; page tabs
  (Timeline Editor / Media Stitcher / Audio Mixer / Color Grading); right side:
  sync/status, **theme (light/dark) toggle**, **accent color switch (new)**, Export.
- **Left rail:** tool icons (Select, Razor, Ripple, Slip, Hand, Text) + snap/settings.
- **Project Assets (left panel):** searchable media bin with filter chips
  (All / 4K Video / Audio / Overlays), thumbnails, durations, type badges.
- **Program monitor (center):** preview with proxy indicator, zoom-fit, in/out marks,
  transport (jog, play/pause, loop), live timecode.
- **Inspector (right panel):** tabbed — **Video** (Transform & Scale, Opacity),
  **Color LUT** (look + intensity), **Audio** (level, mute), **Speed** (retime, pitch).
- **Timeline deck (bottom):** ruler + playhead; lanes V2 overlay / V1 main video /
  A1 music / A2 dialogue; per-lane visibility/lock; selection actions bar
  (Split at Playhead, Speed, Volume, Sync A/V, Auto Ducking, Export).
- **Modes:** Light Studio Mode + Dark; accent color user-selectable (§4).

Interim (before the full timeline exists), the current 3-pane layout stays; Tier A
features slot into the existing Inspector tabs (Output / Loop / Info) and a new
**Export** section.

---

## 4. Accent color switch (spec — to implement on approval)

**Goal:** let the user replace the cyan accent (`#00E5FF`) with another color; the whole
UI's highlights update live and the choice persists.

**Where cyan lives today (needs centralizing):**
- Tailwind token `primary-container: #00E5FF` (index.html config) — most buttons/highlights.
- Hardcoded `#00e5ff` in `static/style.css` (chips, tabs, loop-option outlines, focus rings).
- `accent-[#00e5ff]` on form radios/checkboxes in `static/index.html`.

**Design:**
1. **Single source of truth:** introduce CSS custom properties on `:root`
   — `--accent` (the color) and `--on-accent` (readable text/icon color on top of it).
   Refactor the scattered cyan usages to reference these variables (Tailwind's
   `primary-container` maps to `var(--accent)`; style.css and `accent-*` inputs use it too).
2. **Control (UI):** a small color button in the top bar next to the theme toggle. Opens a
   popover with **preset swatches** (Cyan default, Purple, Emerald, Amber, Rose, Blue) plus
   a **custom hex / native color picker**.
3. **Behavior:** selecting a color sets `--accent` (and computes `--on-accent` for contrast),
   updates instantly, and saves to `localStorage` so it survives reloads. Works alongside
   the existing light/dark toggle.
4. **Scope:** purely presentational — no backend change. ~1 small JS module + a CSS-variable
   refactor of the existing accent usages.

*(Not yet implemented — per instruction, this section is the plan only.)*

---

## Open questions
- Are we committing to the full **timeline editor (Tier B / Stage 3)**, or staying a
  fast **merge/format tool** and investing in Tier A polish + scale? This decides how much
  of the mockup we build.
- Priority of **accounts/quotas** (Tier C) vs. features — depends on going public vs. trial.
