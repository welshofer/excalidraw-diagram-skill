# Excalidraw Diagram Skill — Deep Dive

> This file collects the optional/advanced sections of `SKILL.md`. Agents with
> tight context budgets can read the core Quick Start + Design Process from
> `SKILL.md` and fetch this file on demand when they need more depth.
>
> (Plan v2 item 6.1) The full SKILL.md content intentionally remains in
> `SKILL.md` itself; this file exists as a discoverable deep-dive reference
> that the skill frontmatter points to.

## When to read this file

- You are authoring a **large** diagram (50+ elements) and need the Multi-Zoom
  Architecture discussion, the Visual Pattern Library, or the Large Diagram
  Strategy section from SKILL.md.
- You are designing a **branded** diagram and want the Color-As-Meaning or
  Modern Aesthetics sections.
- You are unsure when to use a particular shape or layout -- consult Shape
  Meaning / Layout Principles.

## How to navigate SKILL.md

SKILL.md contains the following top-level sections (use them as table-of-
contents anchors):

- Quick Start -- minimum viable diagram
- Core Philosophy -- visual argument, not just boxes
- Design Process -- 5-step loop (Research -> Sketch -> JSON -> Render -> Lint)
- Research Mandate -- when and how to gather source evidence
- Evidence Artifacts -- anchoring claims to rendered proof
- Multi-Zoom Architecture -- diagrams that read at multiple zoom levels
- Visual Pattern Library -- fan-out, convergence, timeline, tree, cycle...
- Shape Meaning -- semantic intent of rectangle vs diamond vs ellipse
- Color as Meaning -- semantic role to palette mapping
- Modern Aesthetics -- typography, spacing, whitespace discipline
- Layout Principles -- alignment, hierarchy, flow direction
- Large Diagram Strategy -- sectioning, frames, progressive disclosure
- Common Mistakes -- the top ~10 pitfalls to avoid

## Companion references

- `element-templates.md` -- copy-paste blocks for every element type.
- `color-palette.md` -- default palette + Warm/Cool/HC/Minimal alternatives.
- `json-schema.md` -- field-by-field spec for the `.excalidraw` format.

## Tool usage deep-dive

**Render server mode (v2 1.1)** -- start once per session with
`python render_excalidraw.py --server &`, then POST diagrams to avoid
browser cold-start. See the "Render Server Mode" subsection in SKILL.md.

**Shortform DSL (v2 2.10)** -- when token budget is tight, write
compact YAML-ish lines and pipe through `--from-shortform`:

```
shape: rect id: a text: "Input"  at: [0, 0]   size: [160, 80] role: primary
shape: rect id: b text: "Output" at: [240, 0] size: [160, 80] role: accent
arrow: from: a to: b
```

**Mermaid import (v2 2.7)** -- if you already have a Mermaid `graph LR`
diagram, convert it directly with `python convert_mermaid.py input.mmd`.

**Themes (v2 2.6)** -- reuse the same diagram across brand contexts with
`--theme warm|cool|high-contrast|minimal`.

**Stats (v2 2.8)** -- audit a diagram's visual-vocabulary health with
`python lint_excalidraw.py diagram.excalidraw --stats` -- reports element
mix, colour diversity, bound-vs-free arrow ratios, and size distribution.
