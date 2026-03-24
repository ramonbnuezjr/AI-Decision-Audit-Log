# Dashboard Design System — Synthetic Sentinel

**Project:** AI Decision Audit Log  
**Dashboard:** `dashboard/index.html` + `dashboard/server.py`  
**Status:** Implemented — see `dashboard/` for the running version

## Reference Assets

| Asset | Location | Description |
|---|---|---|
| Mockup screenshot | [`docs/assets/dashboard-mockup.png`](assets/dashboard-mockup.png) | Original visual target for the Synthetic Sentinel design |
| Mockup source HTML | [`docs/assets/dashboard-mockup.html`](assets/dashboard-mockup.html) | Static HTML reference provided by designer |
| Implementation | [`dashboard/index.html`](../dashboard/index.html) | Live FastAPI-served frontend |

## Implementation Map

| Design token / rule | Where implemented |
|---|---|
| Color palette (`#060e20` surface, `#a7a5ff` primary, etc.) | CSS `:root` vars in `dashboard/index.html` |
| Space Grotesk + Inter fonts | Google Fonts `<link>` in `dashboard/index.html` |
| No-line rule (tonal layering only) | All section separators use background shifts, no `border` |
| Pip status indicators | Provider Health section — 10×10px `div` tiles |
| Sharp edges (`border-radius: 2px`) | All cards, badges, and buttons |
| KPI display-lg numbers (3rem) | KPI card `.kpi-value` class |
| Incident card left-border accent | `.incident-card { border-left: 3px solid var(--error) }` |

---

# Design System Document: AI Governance & Oversight

## 1. Overview & Creative North Star

### Creative North Star: "The Synthetic Sentinel"
This design system moves beyond the typical dashboard by adopting a "Synthetic Sentinel" aesthetic. It is designed to feel like an authoritative, high-performance command center—precise, analytical, and uncompromising. We eschew the "bubbly" consumer web in favor of a sophisticated, editorial approach to AI data.

To achieve this, the system breaks the "template" look through **Tonal Monoliths**—large blocks of color that define regions without the need for borders—and **Intentional Asymmetry**. By utilizing extreme typographic scale shifts and "nested glass" containers, we create a high-tech environment that feels like a singular, unified piece of hardware rather than a collection of widgets.

---

## 2. Colors

The palette is anchored in deep, atmospheric charcoals, using vibrant neon-leaning accents to highlight critical AI performance metrics.

### Surface Hierarchy & Nesting
Instead of a flat grid, we treat the UI as a series of physical layers. Use the `surface-container` tiers to define depth:
*   **Base Layer:** `surface` (#060e20) for the primary application background.
*   **Secondary Regions:** `surface-container-low` (#091328) for sidebar or navigation zones.
*   **Interactive Cards:** `surface-container-highest` (#192540) to make data modules pop against the base.

### The "No-Line" Rule
**Prohibit 1px solid borders for sectioning.** Boundaries must be defined solely through background color shifts. For instance, a `surface-container-high` card should sit on a `surface-container-low` background. The change in hex code provides enough contrast to signify a boundary without visual clutter.

### The "Glass & Gradient" Rule
For high-priority alerts or floating modals, utilize a "Glassmorphism" effect. Use a semi-transparent `surface-variant` with a 20px backdrop-blur.
*   **Signature Textures:** For main CTAs and "Healthy" status bars, use a subtle linear gradient from `primary` (#a7a5ff) to `primary-container` (#9795ff) at a 135-degree angle. This adds a "lithographic" soul to the UI.

---

## 3. Typography

The system utilizes a dual-font strategy to balance technical precision with high-end editorial flair.

*   **Display & Headline (Space Grotesk):** This typeface provides a futuristic, geometric edge. Use `display-lg` (3.5rem) for high-level "North Star" metrics (e.g., Total Tokens) to give them an authoritative presence.
*   **Body & Labels (Inter):** Chosen for its unparalleled readability at small sizes. All data tables and technical logs must use `body-md` or `label-sm` to maintain a "clean-room" aesthetic.

**Hierarchy as Identity:** Use `title-lg` (1.375rem) in `primary` (#a7a5ff) to label major dashboard sections. Use `on-surface-variant` (#a3aac4) for metadata and units to create a clear visual "recession" of secondary information.

---

## 4. Elevation & Depth

We avoid traditional "drop shadows" which can feel dated and muddy. Instead, we use **Tonal Layering**.

*   **The Layering Principle:** Depth is achieved by "stacking." A `surface-container-highest` card should be placed on a `surface` background. The inherent contrast creates a soft, natural lift.
*   **Ambient Shadows:** If a floating element (like a filter dropdown) requires a shadow, use a large blur (32px) at a very low opacity (6%) using the `surface-container-lowest` (#000000) color.
*   **The "Ghost Border" Fallback:** If a layout feels too "bleary," apply a 1px border using `outline-variant` (#40485d) at **15% opacity**. This provides a "suggestion" of a boundary without the harshness of a solid line.

---

## 5. Components

### Cards & Data Modules
*   **Style:** Sharp edges (use `roundedness.sm` - 0.125rem) for a high-tech feel.
*   **Separation:** Forbid the use of divider lines. Use `spacing.6` (1.3rem) of white space or subtle background shifts between rows in a table.

### Buttons
*   **Primary:** Solid `primary` (#a7a5ff) with `on-primary` (#1c00a0) text.
*   **Secondary:** No fill, `ghost-border` (outline-variant at 20%), with `primary` text.
*   **Interaction:** On hover, increase the opacity of the ghost border to 100%.

### Input Fields
*   **Background:** `surface-container-lowest` (#000000).
*   **Border:** `outline-variant` (#40485d) at 20% opacity.
*   **Focus:** A 1px solid `secondary` (#53ddfc) border with no outer glow.

### Interactive Data Visualizations
*   **Charts:** Use `secondary` (cool blue) for standard trends, `tertiary` (purple) for AI-specific logic paths, and `error` (#ff6e84) for anomalies.
*   **Status Indicators:** Small, vibrant "pips" using `secondary` for "Active" and `error` for "Incident." Avoid text labels where a color-coded pip suffices.

---

## 6. Do's and Don'ts

### Do:
*   **Use High Contrast for Metrics:** Let the `display-lg` numbers be the hero.
*   **Embrace Negative Space:** Use `spacing.12` or `spacing.16` between major modules to let the data "breathe."
*   **Layer Surfaces:** Place dark elements on darker backgrounds to create a sense of infinite depth.

### Don't:
*   **Don't use 100% white text:** Always use `on-surface` (#dee5ff) or `on-surface-variant` (#a3aac4). Pure white is too harsh for dark themes and causes "halation" (glowing) on OLED screens.
*   **Don't use rounded corners:** Avoid `roundedness.xl` or `roundedness.full` unless it's a specific status chip. The dashboard should feel "architectural" and sharp.
*   **Don't use grid lines:** In tables, let the alignment of text and the `spacing` scale create the grid, not visible lines.
