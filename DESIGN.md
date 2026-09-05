---
name: Precision Mobile NLE
colors:
  surface: '#111316'
  surface-dim: '#111316'
  surface-bright: '#37393d'
  surface-container-lowest: '#0c0e11'
  surface-container-low: '#1a1c1f'
  surface-container: '#1e2023'
  surface-container-high: '#282a2d'
  surface-container-highest: '#333538'
  on-surface: '#e2e2e6'
  on-surface-variant: '#bac9cc'
  inverse-surface: '#e2e2e6'
  inverse-on-surface: '#2f3034'
  outline: '#849396'
  outline-variant: '#3b494c'
  surface-tint: '#00daf3'
  primary: '#c3f5ff'
  on-primary: '#00363d'
  primary-container: '#00e5ff'
  on-primary-container: '#00626e'
  inverse-primary: '#006875'
  secondary: '#ddb7ff'
  on-secondary: '#490080'
  secondary-container: '#6f00be'
  on-secondary-container: '#d6a9ff'
  tertiary: '#ffecb9'
  on-tertiary: '#3c2f00'
  tertiary-container: '#facc15'
  on-tertiary-container: '#6c5700'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#9cf0ff'
  primary-fixed-dim: '#00daf3'
  on-primary-fixed: '#001f24'
  on-primary-fixed-variant: '#004f58'
  secondary-fixed: '#f0dbff'
  secondary-fixed-dim: '#ddb7ff'
  on-secondary-fixed: '#2c0051'
  on-secondary-fixed-variant: '#6900b3'
  tertiary-fixed: '#ffe083'
  tertiary-fixed-dim: '#eec200'
  on-tertiary-fixed: '#231b00'
  on-tertiary-fixed-variant: '#574500'
  background: '#111316'
  on-background: '#e2e2e6'
  surface-variant: '#333538'
typography:
  display-timecode:
    fontFamily: JetBrains Mono
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.02em
  display-timecode-mobile:
    fontFamily: JetBrains Mono
    fontSize: 22px
    fontWeight: '700'
    lineHeight: 26px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 30px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-mono-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.02em
  label-mono-xs:
    fontFamily: JetBrains Mono
    fontSize: 9px
    fontWeight: '600'
    lineHeight: 12px
    letterSpacing: 0.04em
  action-button:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.01em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  track-gutter: 0.25rem
  track-padding-x: 0.5rem
  lane-height-video: 4.25rem
  lane-height-audio: 2.75rem
  lane-height-overlay: 2.25rem
  playhead-width: 0.125rem
  scrubber-head-size: 1.125rem
  handle-touch-target: 2.75rem
  drawer-collapsed-height: 3.5rem
  spacing-xxs: 0.125rem
  spacing-xs: 0.25rem
  spacing-sm: 0.5rem
  spacing-md: 0.75rem
  spacing-lg: 1rem
  spacing-xl: 1.5rem
---

## Brand & Style
This design system targets modern mobile video creators, social-first cinematographers, and mobile editors demanding desktop-grade nonlinear editing power on handheld touchscreens. The aesthetic fuses professional NLE utility (reminiscent of Premiere Pro and DaVinci Resolve) with the fluid tactile ergonomics of CapCut and Lumafusion.

The visual direction centers on **High-Contrast Precision Utility**. Interfaces are dense, dark-biased by default to preserve color accuracy of visual content, razor-sharp in alignment, and accented with high-chroma tool signifiers. Primary interactions favor micro-haptics, crisp pixel boundaries, optical grid snaps, and high-visibility scrubbing markers. Light mode translates this technical rigor into a clean industrial grey architectural workspace, preventing color pollution while retaining instant legibility under bright outdoor shooting environments.

## Colors
The color palette uses distinct functional chromatic lanes for instantaneous media identification across multi-layer timelines:

- **Primary (`#00E5FF` Cyan)**: Active clip selections, trimming bounding boxes, scrubber handle head, active tool modes, and primary interactive states.
- **Secondary (`#A855F7` Electric Purple)**: Audio track waveforms, sound-fx clips, voiceover indicators, and acoustic dynamic badges.
- **Tertiary (`#FACC15` Signal Yellow)**: Scrubber playhead needle, timecode frame markers, split markers, keyframe diamonds, and render cues.
- **Track Semantic Accents**:
  - Video Track Containers: Deep Slate Slate with bright cyan borders on focus (`#00B4D8`).
  - Overlay / Graphic PIP Lanes: Vibrant Emerald (`#10B981`) for sticker/text/PiP indicators.
  - Caution / Inactive: Crimson (`#EF4444`) for clipping warnings and mute/delete confirmations.

### Theme Modes
- **Dark Mode (Default)**: Workspace background `#0A0B0E`, track gutters `#16181D`, lane canvas `#1E2229`, tool elevated sheets `#262B34`, high contrast typography `#F8FAFC`.
- **Light Mode**: Workspace background `#E2E8F0`, track gutters `#CBD5E1`, lane canvas `#FFFFFF`, tool elevated sheets `#F1F5F9`, high contrast typography `#0F172A`. Audio and clip accent colors maintain identical hue families with adjusted luminance to preserve contrast ratios above 4.5:1.

## Typography
Typography reinforces technical precision:
- **JetBrains Mono** is mandatory for all temporal metrics: SMPTE timecodes (`00:14:28:12`), audio decibel outputs (`-6.2 dB`), clip frame counts, timeline tick headers, and playback speeds (`1.5x`). Monospace tabular alignment prevents layout jitter during high-speed timeline scrubbing.
- **Space Grotesk** serves as the headline and category anchor for asset drawers, modal titles, and export configurations, offering a mechanical, forward-looking edge.
- **Geist** handles standard UI labels, metadata descriptions, clip names, and inspector parameter lists for maximal density and legibility at tiny scale.

## Layout & Spacing
The layout follows a strict vertical tri-pane workstation optimized for mobile viewports:

1. **Monitor Canvas (Top 35-40% Viewport)**: Fixed aspect ratio video player surrounded by edge safety guides and floating overlay transport badges.
2. **Scrubber Ruler & Action Bar (Center 8-10% Viewport)**: Central timecode readout, split tool, undo/redo, play/pause trigger, and magnetic snap toggle.
3. **Multi-Track Timeline Deck (Bottom 50-55% Viewport)**: Horizontal panning canvas partitioned into persistent vertical lanes:
   - Upper PIP / Subtitle tracks.
   - Core Video Track with filmstrip thumbnail generation.
   - Audio Waveform lanes with decibel reference midlines.
4. **Docked Tool Drawer & Inspector (Bottom Slide-over)**: Tabbed asset shelves and parametric adjustment sliders that collapse to a compact 56px command strip when scrubbing.

Touch targets enforce an absolute minimum of 44x44px. Drag handles expand their active touch receptor box beyond visual clipping borders to ensure seamless single-finger trimming without visual occlusion.

## Elevation & Depth
Depth conveys editing hierarchy through stacked tonal layers and sharp micro-outlines:

- **Level 0 (Canvas Base)**: Deep non-reflective matte (`#0A0B0E`). Houses the background tracks and timeline empty lanes.
- **Level 1 (Track Lanes & Inactive Clips)**: Matte cards with 1px dark interior borders (`rgba(255, 255, 255, 0.08)`). Semi-transparent checkerboard underlays for alpha-channel assets.
- **Level 2 (Selected Active Clip & Trimming Bounding Box)**: Elevated +2px Z-index, wrapped with an illuminated 2px solid cyan border (`#00E5FF`), equipped with prominent high-friction grab nodes.
- **Level 3 (Playhead Scrubber Line & Connectors)**: Positioned above all video tiers with a piercing 2px yellow needle, dropped shadow (`0 0 10px rgba(250, 204, 21, 0.45)`), and yellow teardrop timecode pin.
- **Level 4 (Inspector Drawers & Tool Popovers)**: High-density surface glass (`rgba(22, 24, 29, 0.92)`) backed by a 24px backdrop blur and crisp top-edge highlight stroke (`rgba(255, 255, 255, 0.12)`).

## Shapes
A tight **Soft (`1`)** shape language governs the system to maximize timeline density and provide a precise tooling aesthetic:
- Clips within tracks adopt subtle `4px` (`rounded-sm`) corner radiuses to delineate cut points clearly without breaking temporal linearity.
- Clip connector chips and plus icons use `4px` squares rotated 45 degrees or compact roundels.
- Scrubber playhead marker uses a downward-pointing pentagon/teardrop pin.
- Trimming drag handles feature embossed vertical grip dots (`6-dot matrix`) aligned flush with clip outer edges.
- Tool buttons and segmented controls use clean `6px` (`rounded-md`) rectangles to convey solid tactile interaction.

## Components

### 1. Video Timeline Track & Clip Cells
- **Default State**: Horizontal frame filmstrip encapsulated in a 4px rounded bounding container with persistent clip label badge, mute/lock indicators, and duration chip.
- **Selected State**: 2px `#00E5FF` high-voltage border with dual edge trimming bars. Left and right grip wings extend tactile hit regions by 16px beyond visible clip boundaries.
- **Connectors**: Micro inline circle with central `+` icon positioned exactly at the edit seam between consecutive clips to trigger transition menus.

### 2. Audio Waveform Track
- **Styling**: Solid electric purple (`#A855F7`) fill with dynamic high-resolution peak waveforms rendered in high contrast white or neon lilac.
- **Controls**: Includes horizontal centerline reference for 0dB gain and embedded micro volume automation nodes (keyframes).

### 3. Scrubber Playhead
- **Design**: 2px `#FACC15` vertical razor line running continuously across every track down through the timeline floor.
- **Scrubber Pin**: Golden tactile thumb tab docked on the SMPTE tick header containing a live updating millisecond-accurate timecode callout bubble.

### 4. Transport & Editing Quick-Bar
- Centered play/pause circular toggle flanked by frame-by-frame jog nudge buttons (`-1f`, `+1f`), dynamic split (blade) shortcut, and delete action.
- Haptic feedback trigger on each playhead notch passing a clip transition or snap point.

### 5. Drawer & Parameter Inspector
- Bottom-docked expandable drawer with tab switches: *Media, Audio, Transitions, FX, Text, Adjust*.
- Color grading wheel mini-cards, numerical scrub sliders with live tick marks, and keyframe add/remove diamond toggles.

### 6. Buttons, Chips & Fields
- **Primary Tool Button**: Solid cyan fill with stark obsidian icon/text.
- **Secondary Icon Actions**: Frameless high-contrast glyphs encased in 36x36px hover/tap highlight zones.
- **Input Fields**: Monospaced tabular entry boxes for direct numerical timecode or aspect ratio typing.