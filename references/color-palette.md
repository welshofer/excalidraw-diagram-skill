# Color Palette & Brand Style

**This is the single source of truth for all colors and brand-specific styles.** To customize diagrams for your own brand, edit this file — everything else in the skill is universal.

---

## Shape Colors (Semantic)

Colors encode meaning, not decoration. Each semantic purpose has a fill/stroke pair.

| Semantic Purpose | Fill | Stroke |
|------------------|------|--------|
| Primary/Neutral | `#3b82f6` | `#1e3a5f` |
| Secondary | `#60a5fa` | `#1e3a5f` |
| Tertiary | `#93c5fd` | `#1e3a5f` |
| Start/Trigger | `#fed7aa` | `#c2410c` |
| End/Success | `#a7f3d0` | `#047857` |
| Warning/Reset | `#fee2e2` | `#dc2626` |
| Decision | `#fef3c7` | `#b45309` |
| AI/LLM | `#ddd6fe` | `#6d28d9` |
| Inactive/Disabled | `#dbeafe` | `#1e40af` (use dashed stroke) |
| Error | `#fecaca` | `#b91c1c` |

**Rule**: Always pair a darker stroke with a lighter fill for contrast.

---

## Text Colors (Hierarchy)

Use color on free-floating text to create visual hierarchy without containers.

| Level | Color | Use For |
|-------|-------|---------|
| Title | `#1e40af` | Section headings, major labels |
| Subtitle | `#3b82f6` | Subheadings, secondary labels |
| Body/Detail | `#64748b` | Descriptions, annotations, metadata |
| On light fills | `#374151` | Text inside light-colored shapes |
| On dark fills | `#ffffff` | Text inside dark-colored shapes |

---

## Evidence Artifact Colors

Used for code snippets, data examples, and other concrete evidence inside technical diagrams.

| Artifact | Background | Text Color |
|----------|-----------|------------|
| Code snippet | `#1e293b` | Syntax-colored (language-appropriate) |
| JSON/data example | `#1e293b` | `#22c55e` (green) |

---

## Default Stroke & Line Colors

| Element | Color |
|---------|-------|
| Arrows | Use the stroke color of the source element's semantic purpose |
| Structural lines (dividers, trees, timelines) | Primary stroke (`#1e3a5f`) or Slate (`#64748b`) |
| Marker dots (fill + stroke) | Primary fill (`#3b82f6`) |

---

## Background

| Property | Value |
|----------|-------|
| Canvas background | `#ffffff` |

---

## Dark Mode Colors

Use these when rendering with `--dark` mode. The semantic meanings stay the same, but fills and strokes are adjusted for dark backgrounds.

| Semantic Purpose | Fill | Stroke |
|------------------|------|--------|
| Primary/Neutral | `#1e3a5f` | `#60a5fa` |
| Secondary | `#1e3a5f` | `#93c5fd` |
| Start/Trigger | `#7c2d12` | `#fed7aa` |
| End/Success | `#064e3b` | `#a7f3d0` |
| Warning/Reset | `#7f1d1d` | `#fecaca` |
| Decision | `#78350f` | `#fef3c7` |
| AI/LLM | `#4c1d95` | `#ddd6fe` |
| Error | `#7f1d1d` | `#fecaca` |

| Text Level | Color |
|------------|-------|
| Title | `#93c5fd` |
| Subtitle | `#60a5fa` |
| Body/Detail | `#94a3b8` |
| On dark fills | `#e2e8f0` |

| Property | Value |
|----------|-------|
| Canvas background (dark) | `#1e1e1e` |

---

## Alternative Palettes

For different visual styles, consider these palette variants. Create a copy of this file and swap the Shape Colors table.

### Warm Palette
| Purpose | Fill | Stroke |
|---------|------|--------|
| Primary | `#f97316` | `#9a3412` |
| Secondary | `#fb923c` | `#9a3412` |
| Accent | `#fbbf24` | `#92400e` |

### Cool Palette
| Purpose | Fill | Stroke |
|---------|------|--------|
| Primary | `#06b6d4` | `#164e63` |
| Secondary | `#22d3ee` | `#164e63` |
| Accent | `#a78bfa` | `#4c1d95` |

### High-Contrast Accessibility Palette
| Purpose | Fill | Stroke |
|---------|------|--------|
| Primary | `#2563eb` | `#000000` |
| Secondary | `#16a34a` | `#000000` |
| Warning | `#dc2626` | `#000000` |
| Neutral | `#f3f4f6` | `#000000` |

### Minimal / Grayscale Palette
| Purpose | Fill | Stroke |
|---------|------|--------|
| Primary | `#f3f4f6` | `#374151` |
| Secondary | `#e5e7eb` | `#374151` |
| Accent | `#d1d5db` | `#1f2937` |
| Emphasis | `#374151` | `#111827` |
