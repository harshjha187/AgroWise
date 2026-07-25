# AgroWise — Design System

**Status: LOCKED.** This is the canonical, finalized visual design for both frontends, matched to an explicit reference design the project owner provided. Do not restyle, retheme, or "improve" this design without an explicit new request to change it — see `rules.md` § 3 for the enforcement rule. This file should always reflect exactly what's shipping; if you change a token in code, update it here in the same pass.

Color, theme, and typography reference for both frontends. Companion to [ARCHITECTURE.md](ARCHITECTURE.md) (structure) and [rules.md](rules.md) (§3 Frontend conventions). All values below are pulled directly from `web-dashboard/index.html` and `mobile-app/index.html`'s `:root` blocks — this file documents what's actually shipping, not an aspirational palette.

---

## 1. One unified visual language, two layouts

Both frontends now share **the same color palette, the same font (Inter), and the same card/shadow/chip design language**. They are not two different-themed apps — they're one design system expressed across two different screen contexts:

| | Web dashboard | Mobile app ("AgroWise Field") |
|---|---|---|
| **Background** | Light gray (`#F5F7FA`) | Light gray (`#F5F7FA`) — same token |
| **Font** | Inter | Inter (same import, same weights) |
| **Layout** | Persistent dark-navy sidebar nav + multi-column card grid | Bottom tab nav + single-column stack (no sidebar — no room on a phone) |
| **Brand text shown** | "AgroWise" (sidebar wordmark) | "AgroWise Field" (the PWA's install/app name) |

The only real *structural* difference is the sidebar (a desktop affordance that doesn't fit a phone screen, replaced by the bottom nav) — not a competing color scheme. If you're about to introduce a new color, font, or shadow value in either app, it should come from this shared palette, not a new one-off.

(Earlier in this project's history the mobile app used a separate dark "field instrument" theme — Space Grotesk + IBM Plex Mono, olive/ochre/clay palette. That was deliberately retired and replaced with this unified light theme; don't resurrect it.)

---

## 2. Color Palette (shared by both apps)

### Base / neutrals
| Token | Hex | Usage |
|---|---|---|
| `--bg` | `#F5F7FA` | Page background |
| `--panel` | `#FFFFFF` | Card/panel surfaces |
| `--line` | `#E5E9F0` | Borders, dividers |
| `--line-soft` | `#EEF1F6` | Subtle backgrounds (recommendation rows, table header) |
| `--text` | `#1F2937` | Primary text |
| `--muted` | `#6B7280` | Secondary text, labels |
| `--faint` | `#9CA3AF` | Tertiary/disabled text |

### Dashboard-only: sidebar (dark, inset into the light theme)
| Token | Hex | Usage |
|---|---|---|
| `--sidebar` | `#111827` | Sidebar background |
| `--sidebar-hover` | `#1F2937` | Sidebar item hover |
| `--sidebar-line` | `#1F2937` | Sidebar dividers |

The mobile app has no sidebar, so it has no equivalent tokens — its bottom nav uses the shared `--panel`/`--line` tokens instead (a translucent white bar).

### Semantic / accent colors
Each accent has a **base**, a **-dim** (tinted background for chips/badges), and a text-on-dim color for accessible contrast.

| Color | Base | Dim (bg) | Text-on-dim | Used for |
|---|---|---|---|---|
| Sage (primary/success) | `#10B981` | `#D1FAE5` | `#065F46` | Nitrogen, FERTILE, "good"/"ok" status, primary actions, active nav |
| Blue | `#3B82F6` | `#DBEAFE` | `#1E40AF` | Phosphorus, info states |
| Purple | `#8B5CF6` | `#EDE9FE` | `#5B21B6` | Potassium |
| Cyan | `#06B6D4` | `#CFFAFE` | `#155E75` | Moisture |
| Amber (warning) | `#F59E0B` | `#FEF3C7` | `#92400E` | MODERATE, warning alerts, "low" chips |
| Orange | `#F97316` | `#FED7AA` | `#9A3412` | Temperature |
| Red (critical) | `#EF4444` | `#FEE2E2` | `#991B1B` | BARREN, critical alerts, "high"/"crit" chips, destructive actions |
| Rose | `#F43F5E` | — | — | Dashboard-only: "Add Reading" quick action |
| pH blue (one-off) | `#5B9BD5` | — | `#2E5C8A` | Soil pH icon/chart line on the dashboard (not a named CSS var — see note) |

**Naming note:** the dashboard defines these as CSS custom properties (`--sage`, `--sage-dim`, `--sage-text`, etc.). The mobile app defines the *same hex values* under differently-named variables for historical reasons (`--ochre` = amber, `--clay` = red, `--info` = blue) — don't be confused by the name mismatch; the colors are identical. If you touch one, check both files.

### Classification → color mapping (same in both apps now)
| Class | Color |
|---|---|
| FERTILE | sage `#10B981` |
| MODERATE | amber `#F59E0B` |
| BARREN | red `#EF4444` |

(Previously the two apps used different hex values for this mapping — that's no longer true. Both now use the exact same three hex values, confirmed via each app's `CLS_COLOR`/classification CSS.)

### Chart series colors (Chart.js trend chart, dashboard only)
| Series | Color |
|---|---|
| Nitrogen | `#10B981` (sage) |
| Phosphorus | `#3B82F6` (blue) |
| Potassium | `#8B5CF6` (purple) |
| Moisture % | `#06B6D4` (cyan) |
| Soil pH | `#5B9BD5` (one-off pH blue, plotted on a secondary 0–14 axis since its scale differs wildly from the others) |

### Quick Actions button colors (dashboard)
| Button | Color class |
|---|---|
| Export Data (CSV) | `.act-blue` |
| Generate Report (PDF) | `.act-sage` |
| View Full History | `.act-purple` |
| Calibrate Sensors | `.act-orange` |
| Simulate ESP32 | `.act-teal` (`#0EA5E9`→`#0284C7` gradient) |
| Add Reading | `.act-rose` (`#F43F5E`→`#E11D48` gradient) |

---

## 3. Dark mode (opt-in — light stays the locked default)

Both apps now have a real dark mode, toggled from Settings (dashboard) / Setup (mobile) and persisted to `localStorage` (`agrowise-theme`). **This does not violate the design lock** — light is still the default for every new visitor; dark is an additive, user-chosen alternative, not a replacement. Applied via `:root[data-theme="dark"]` overriding the same CSS variable names (so component CSS needs zero changes — everything already reads from variables).

| Token | Light | Dark |
|---|---|---|
| `--bg` | `#F5F7FA` | `#0B1120` |
| `--panel` | `#FFFFFF` | `#131B2E` |
| `--line` | `#E5E9F0` | `#22304A` |
| `--text` | `#1F2937` | `#E5E7EB` |
| `--sage-text` (and other `-text` vars) | dark-on-light (e.g. `#065F46`) | brightened for dark backgrounds (e.g. `#6EE7B7`) |
| `-dim` accent backgrounds | solid light tints (e.g. `#D1FAE5`) | translucent (e.g. `rgba(16,185,129,.16)`) |
| `--shadow` / `--shadow-lg` | low-opacity (`.05–.14`) | higher-opacity (`.25–.5`) — shadows read lighter against dark backgrounds |

A small number of selectors couldn't be covered by variables alone and get explicit `[data-theme="dark"]` overrides: `.class-illust` variants and the pH stat/chart color (dashboard), `.cls`/`.btn` border colors and the `.top`/`nav` translucent backgrounds (mobile). The brand mark's icon gradient (`#065F46`→`#10B981`) is intentionally **not** theme-tied — it's a fixed brand treatment, same as its light-mode-only origin before dark mode existed.

An early inline `<script>` in `<head>` applies the saved theme before first paint (reading `localStorage` synchronously) to avoid a flash of the wrong theme.

---

## 4. Typography

**Both apps use Inter, and only Inter.** Loaded via Google Fonts with `weights: 400;500;600;700;800`, falling back to `system-ui, sans-serif`. The mobile app previously used Space Grotesk + IBM Plex Mono in a deliberately distinct "field instrument" style — that's been retired in favor of this shared typography.

- **Dashboard base size:** `14px`, `line-height:1.5`.
- **Mobile base size:** `15px`, `line-height:1.5` (slightly larger — phone reading distance).
- **Weight usage:** 500 (labels/nav), 600 (card titles, buttons, chips), 700 (stat values), 800 (brand wordmark only).
- **Scale in use (dashboard):** 11px (chip labels) · 12px (meta/labels) · 13–13.5px (body/buttons) · 14px (base) · 15px (card titles) · 16px (nav-adjacent headings) · 22px (icon-in-circle text) · 24px (page `<h1>`) · 26px (gauge value, classification badge) · 36px (score readout).
- **Scale in use (mobile):** 9px (nav labels, eyebrows, uppercase micro-labels — always paired with `letter-spacing` 0.5–1.2px) · 10–11px (hints, timestamps, chip text) · 12–13px (body, recommendation titles) · 14px (inputs) · 16px (page heading) · 20–22px (tile values, stat numbers) · 42px (score readout).
- Uppercase micro-labels (eyebrows, chip text, nav labels) always carry `letter-spacing` — never uppercase without added tracking.
- Numeric/data values are visually weighted heavier (600–700) than the labels next to them.

Both apps still declare separate `--sans`/`--mono` CSS variables internally for historical reasons, but **both now point to `'Inter', system-ui, sans-serif`** in both files — there is no monospace font loaded anywhere in the project anymore.

---

## 5. Elevation (shadows)

Both apps now use the **same two-tier shadow scale**:

| Token | Value |
|---|---|
| `--shadow` (resting) | `0 4px 10px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.05)` |
| `--shadow-lg` (hover/elevated) | `0 20px 45px rgba(0,0,0,.14), 0 6px 14px rgba(0,0,0,.08)` |

(Previously the mobile app used much higher-opacity shadows tuned for its dark background — those values are gone along with the dark theme.)

**Buttons** additionally get a "raised lip" shadow (`0 4px 0 <dark>, 0 8px 18px <soft>`) that collapses toward `0 1px 0 ...` on `:active`, simulating a physical press. See `rules.md` § 3 for the interaction system this feeds into (mouse-tracked tilt + press animation) — that system is unchanged by this reskin.

**Toasts** are the one deliberate exception to the light theme: both apps use a dark `#111827` background with white text for toast/snackbar notifications, for contrast and because dark toasts over light content is a standard, recognizable pattern (Material, iOS, etc.) — don't "fix" this to be light-on-light.

---

## 6. Border Radius Scale

Both apps use a consistent small→large radius scale rather than one fixed value:

| Radius | Used for |
|---|---|
| 4px | Small chip corners (dashboard) |
| 6px | Chips/badges (dashboard) |
| 8px | Buttons, sidebar nav items (dashboard) |
| 9–10px | Icon marks, small tiles |
| 12px | Cards, stat tiles, buttons (mobile), inputs |
| 14px | Tiles, stats (mobile) |
| 16px | Cards (mobile) |
| 99px / 999px | Fully-rounded pills — status badges, chips, nav dots |

---

## 7. Iconography

- All icons are **inline SVG**, stroke-based (`fill:none; stroke:currentColor; stroke-width:2` on web, `1.7` on mobile), never an icon font or external icon library.
- Sized 18–24px inline with text, or up to 64–110px for illustrative marks (brand mark, classification illustration).
- Icons inherit `currentColor` so they recolor automatically with their semantic context (sage for good, red for critical, etc.) — don't hardcode icon stroke colors.
- The brand mark (leaf-in-soil icon) is now identical in construction between both apps: a `linear-gradient(135deg,#065F46,#10B981)` rounded-square badge with a white stem, mint-green (`#A7F3D0`/`#6EE7B7`) leaf fills, and brown (`#78350F`/`#57210A`) soil bars.

---

## 8. Motion

- Resting → hover/press transitions use `cubic-bezier(.2,.8,.3,1)` for the "settle" motion (cards, tiles, nav) at `~0.3–0.45s`, and a fast linear `~0.05–0.08s` during active pointer tracking / press, per the tilt system in `rules.md` § 3.
- `@media (prefers-reduced-motion: reduce)` disables all transform/transition animation project-wide — required on any new animated component, not optional.
- Unchanged by this reskin — the interaction/motion system is independent of the color/theme work.

---

## 9. Brand text — resolved to "AgroWise" everywhere

Both apps now consistently use the **"AgroWise"** product name: the dashboard sidebar shows a plain "AgroWise" wordmark (device ID `ESP32-AW-001`), and the mobile app shows "AgroWise Field" (its PWA install/home-screen name, from `manifest.json`).

For a brief period during the initial reskin, the dashboard sidebar showed "SMART SOIL SYSTEM" (matching a reference design's literal wordmark) while the mobile app kept "AgroWise Field" — an intentionally scoped, contained inconsistency at the time. That was reverted by explicit request; "AgroWise" is now the single brand name used across both frontends. If a rename away from "AgroWise" is wanted again, treat it the same way: confirm scope (does it touch `README.md`/`PRD.md`/`manifest.json`/docs, or just the in-app wordmark?) before propagating it.

---

## 10. Applying this system to new UI

1. Reuse an existing CSS custom property — never hardcode a hex value that already has a token, in **either** app.
2. If a genuinely new semantic color is needed, add it as a `base` / `-dim` / `-text` (or equivalent) trio, matching the existing pattern, and add it to both apps' `:root` blocks so they stay in sync.
3. The two apps' palettes are now **the same** — do not reintroduce a second, different palette for the mobile app. If you're about to pick a mobile-only color, stop and check whether the dashboard already has a token for it.
4. Pick font weight from the existing scale (§ 3) rather than an arbitrary value — the Google Fonts import only loads specific weights (400/500/600/700/800), so an unlisted weight will silently fall back to the nearest loaded one.
5. This design is **locked** (see top of file). A request to "improve," "modernize," or "restyle" the UI in general terms should not be treated as license to change these tokens — confirm explicitly first, per `rules.md` § 3.
