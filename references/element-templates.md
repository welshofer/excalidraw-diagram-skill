# Element Templates

Copy-paste JSON templates for each Excalidraw element type. The `strokeColor` and `backgroundColor` values are placeholders — always pull actual colors from `color-palette.md` based on the element's semantic purpose.

## Free-Floating Text (no container)
```json
{
  "type": "text",
  "id": "label1",
  "x": 100, "y": 100,
  "width": 200, "height": 25,
  "text": "Section Title",
  "originalText": "Section Title",
  "fontSize": 20,
  "fontFamily": 3,
  "textAlign": "left",
  "verticalAlign": "top",
  "strokeColor": "<title color from palette>",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 1,
  "strokeStyle": "solid",
  "roughness": 0,
  "opacity": 100,
  "angle": 0,
  "seed": 11111,
  "version": 1,
  "versionNonce": 22222,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": null,
  "link": null,
  "locked": false,
  "containerId": null,
  "lineHeight": 1.25
}
```

## Line (structural, not arrow)
```json
{
  "type": "line",
  "id": "line1",
  "x": 100, "y": 100,
  "width": 0, "height": 200,
  "strokeColor": "<structural line color from palette>",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 0,
  "opacity": 100,
  "angle": 0,
  "seed": 44444,
  "version": 1,
  "versionNonce": 55555,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": null,
  "link": null,
  "locked": false,
  "points": [[0, 0], [0, 200]]
}
```

## Small Marker Dot
```json
{
  "type": "ellipse",
  "id": "dot1",
  "x": 94, "y": 94,
  "width": 12, "height": 12,
  "strokeColor": "<marker dot color from palette>",
  "backgroundColor": "<marker dot color from palette>",
  "fillStyle": "solid",
  "strokeWidth": 1,
  "strokeStyle": "solid",
  "roughness": 0,
  "opacity": 100,
  "angle": 0,
  "seed": 66666,
  "version": 1,
  "versionNonce": 77777,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": null,
  "link": null,
  "locked": false
}
```

## Rectangle
```json
{
  "type": "rectangle",
  "id": "elem1",
  "x": 100, "y": 100, "width": 180, "height": 90,
  "strokeColor": "<stroke from palette based on semantic purpose>",
  "backgroundColor": "<fill from palette based on semantic purpose>",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 0,
  "opacity": 100,
  "angle": 0,
  "seed": 12345,
  "version": 1,
  "versionNonce": 67890,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": [{"id": "text1", "type": "text"}],
  "link": null,
  "locked": false,
  "roundness": {"type": 3}
}
```

## Text (centered in shape)
```json
{
  "type": "text",
  "id": "text1",
  "x": 130, "y": 132,
  "width": 120, "height": 25,
  "text": "Process",
  "originalText": "Process",
  "fontSize": 16,
  "fontFamily": 3,
  "textAlign": "center",
  "verticalAlign": "middle",
  "strokeColor": "<text color — match parent shape's stroke or use 'on light/dark fills' from palette>",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 1,
  "strokeStyle": "solid",
  "roughness": 0,
  "opacity": 100,
  "angle": 0,
  "seed": 11111,
  "version": 1,
  "versionNonce": 22222,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": null,
  "link": null,
  "locked": false,
  "containerId": "elem1",
  "lineHeight": 1.25
}
```

## Arrow
```json
{
  "type": "arrow",
  "id": "arrow1",
  "x": 282, "y": 145, "width": 118, "height": 0,
  "strokeColor": "<arrow color — typically matches source element's stroke from palette>",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 0,
  "opacity": 100,
  "angle": 0,
  "seed": 33333,
  "version": 1,
  "versionNonce": 44444,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": null,
  "link": null,
  "locked": false,
  "points": [[0, 0], [118, 0]],
  "startBinding": {"elementId": "elem1", "focus": 0, "gap": 2},
  "endBinding": {"elementId": "elem2", "focus": 0, "gap": 2},
  "startArrowhead": null,
  "endArrowhead": "arrow"
}
```

For curves: use 3+ points in `points` array.

## Ellipse (standard size, with text)

Use for entry/exit points, external systems, or abstract states. Pair with a text element using `containerId`.

```json
{
  "type": "ellipse",
  "id": "ellipse1",
  "x": 100, "y": 100,
  "width": 140, "height": 70,
  "strokeColor": "<stroke from palette based on semantic purpose>",
  "backgroundColor": "<fill from palette based on semantic purpose>",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 0,
  "opacity": 100,
  "angle": 0,
  "seed": 88888,
  "version": 1,
  "versionNonce": 99999,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": [{"id": "ellipse1_text", "type": "text"}],
  "link": null,
  "locked": false
}
```

Text inside the ellipse:
```json
{
  "type": "text",
  "id": "ellipse1_text",
  "x": 120, "y": 123,
  "width": 100, "height": 25,
  "text": "Start",
  "originalText": "Start",
  "fontSize": 18,
  "fontFamily": 3,
  "textAlign": "center",
  "verticalAlign": "middle",
  "strokeColor": "<text color>",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 1,
  "strokeStyle": "solid",
  "roughness": 0,
  "opacity": 100,
  "angle": 0,
  "seed": 88889,
  "version": 1,
  "versionNonce": 99998,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": null,
  "link": null,
  "locked": false,
  "containerId": "ellipse1",
  "lineHeight": 1.25
}
```

## Diamond (decision)

Use for decisions, conditionals, and branching points. The classic diamond shape.

```json
{
  "type": "diamond",
  "id": "decision1",
  "x": 100, "y": 100,
  "width": 140, "height": 100,
  "strokeColor": "<Decision stroke from palette (#b45309)>",
  "backgroundColor": "<Decision fill from palette (#fef3c7)>",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 0,
  "opacity": 100,
  "angle": 0,
  "seed": 55555,
  "version": 1,
  "versionNonce": 55556,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": [
    {"id": "decision1_text", "type": "text"},
    {"id": "arrow_yes", "type": "arrow"},
    {"id": "arrow_no", "type": "arrow"}
  ],
  "link": null,
  "locked": false
}
```

Text inside the diamond:
```json
{
  "type": "text",
  "id": "decision1_text",
  "x": 120, "y": 138,
  "width": 100, "height": 25,
  "text": "Condition?",
  "originalText": "Condition?",
  "fontSize": 16,
  "fontFamily": 3,
  "textAlign": "center",
  "verticalAlign": "middle",
  "strokeColor": "<Decision stroke from palette (#b45309)>",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 1,
  "strokeStyle": "solid",
  "roughness": 0,
  "opacity": 100,
  "angle": 0,
  "seed": 55557,
  "version": 1,
  "versionNonce": 55558,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": null,
  "link": null,
  "locked": false,
  "containerId": "decision1",
  "lineHeight": 1.25
}
```

## Frame (section boundary / group)

Use frames to create labeled section boundaries that visually group related components. Add child element IDs via `groupIds` on the child elements matching the frame's group.

```json
{
  "type": "frame",
  "id": "section_backend",
  "x": 50, "y": 50,
  "width": 500, "height": 400,
  "name": "Backend Services",
  "strokeColor": "#1e3a5f",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 1,
  "strokeStyle": "solid",
  "roughness": 0,
  "opacity": 100,
  "angle": 0,
  "seed": 77777,
  "version": 1,
  "versionNonce": 77778,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": null,
  "link": null,
  "locked": false
}
```

To place elements inside a frame, add the frame's group ID to each child element's `groupIds` array:
```json
{
  "type": "rectangle",
  "id": "api_server",
  "groupIds": ["section_backend_group"],
  ...
}
```

**Tip**: Use a consistent naming convention like `"section_NAME_group"` for group IDs that match frames.

## Fill Style Variants

All shapes support different fill styles for visual variety:

**Solid fill** (default, clean look):
```json
"fillStyle": "solid"
```

**Hachure fill** (hand-drawn diagonal lines, good for "in-progress" or "draft" elements):
```json
"fillStyle": "hachure"
```

**Cross-hatch fill** (crossed diagonal lines, good for emphasis or category distinction):
```json
"fillStyle": "cross-hatch"
```

## Font Family Options

Excalidraw supports three font families:

| Value | Font | Use For |
|-------|------|---------|
| `1` | Virgil (hand-drawn) | Informal, creative, brainstorming diagrams |
| `2` | Helvetica (normal) | Business, professional, presentation diagrams |
| `3` | Monospace (code) | Technical, code-focused diagrams (default) |

Choose the font family that matches your diagram's purpose:
```json
"fontFamily": 1  // hand-drawn feel
"fontFamily": 2  // clean professional
"fontFamily": 3  // technical/code (recommended default)
```

## Compound Shape Icons (Visual Vocabulary)

Excalidraw has no built-in icon library, but you can build recognizable icons from basic shapes. Use these compound patterns to enrich your diagrams with domain-specific symbols.

### Database Cylinder (stacked ellipses + rectangle)

Build a cylinder from a rectangle body with ellipses at top and bottom. Group them via `groupIds`.

```json
[
  {
    "type": "ellipse",
    "id": "db_top",
    "x": 100, "y": 90,
    "width": 100, "height": 30,
    "strokeColor": "#047857",
    "backgroundColor": "#a7f3d0",
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 70001,
    "version": 1,
    "versionNonce": 70002,
    "isDeleted": false,
    "groupIds": ["db_icon_group"],
    "boundElements": null,
    "link": null,
    "locked": false
  },
  {
    "type": "rectangle",
    "id": "db_body",
    "x": 100, "y": 105,
    "width": 100, "height": 50,
    "strokeColor": "#047857",
    "backgroundColor": "#a7f3d0",
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 70003,
    "version": 1,
    "versionNonce": 70004,
    "isDeleted": false,
    "groupIds": ["db_icon_group"],
    "boundElements": [{"id": "db_label", "type": "text"}],
    "link": null,
    "locked": false
  },
  {
    "type": "ellipse",
    "id": "db_bottom",
    "x": 100, "y": 140,
    "width": 100, "height": 30,
    "strokeColor": "#047857",
    "backgroundColor": "#a7f3d0",
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 70005,
    "version": 1,
    "versionNonce": 70006,
    "isDeleted": false,
    "groupIds": ["db_icon_group"],
    "boundElements": null,
    "link": null,
    "locked": false
  },
  {
    "type": "text",
    "id": "db_label",
    "x": 115, "y": 118,
    "width": 70, "height": 25,
    "text": "DB",
    "originalText": "DB",
    "fontSize": 16,
    "fontFamily": 3,
    "textAlign": "center",
    "verticalAlign": "middle",
    "strokeColor": "#047857",
    "backgroundColor": "transparent",
    "fillStyle": "solid",
    "strokeWidth": 1,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 70007,
    "version": 1,
    "versionNonce": 70008,
    "isDeleted": false,
    "groupIds": ["db_icon_group"],
    "boundElements": null,
    "link": null,
    "locked": false,
    "containerId": "db_body",
    "lineHeight": 1.25
  }
]
```

### Cloud Shape (overlapping ellipses)

Approximate a cloud using 3-4 overlapping ellipses grouped together.

```json
[
  {
    "type": "ellipse",
    "id": "cloud_1",
    "x": 100, "y": 110,
    "width": 80, "height": 50,
    "strokeColor": "#0369a1",
    "backgroundColor": "#bae6fd",
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 71001,
    "version": 1,
    "versionNonce": 71002,
    "isDeleted": false,
    "groupIds": ["cloud_group"],
    "boundElements": null,
    "link": null,
    "locked": false
  },
  {
    "type": "ellipse",
    "id": "cloud_2",
    "x": 130, "y": 90,
    "width": 90, "height": 55,
    "strokeColor": "#0369a1",
    "backgroundColor": "#bae6fd",
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 71003,
    "version": 1,
    "versionNonce": 71004,
    "isDeleted": false,
    "groupIds": ["cloud_group"],
    "boundElements": null,
    "link": null,
    "locked": false
  },
  {
    "type": "ellipse",
    "id": "cloud_3",
    "x": 175, "y": 100,
    "width": 80, "height": 55,
    "strokeColor": "#0369a1",
    "backgroundColor": "#bae6fd",
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 71005,
    "version": 1,
    "versionNonce": 71006,
    "isDeleted": false,
    "groupIds": ["cloud_group"],
    "boundElements": null,
    "link": null,
    "locked": false
  },
  {
    "type": "text",
    "id": "cloud_label",
    "x": 135, "y": 115,
    "width": 80, "height": 25,
    "text": "Cloud",
    "originalText": "Cloud",
    "fontSize": 16,
    "fontFamily": 3,
    "textAlign": "center",
    "verticalAlign": "middle",
    "strokeColor": "#0369a1",
    "backgroundColor": "transparent",
    "fillStyle": "solid",
    "strokeWidth": 1,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 71007,
    "version": 1,
    "versionNonce": 71008,
    "isDeleted": false,
    "groupIds": ["cloud_group"],
    "boundElements": null,
    "link": null,
    "locked": false,
    "containerId": null,
    "lineHeight": 1.25
  }
]
```

### User Silhouette (circle head + trapezoid body)

A simple person icon using a circle for the head and a wider rectangle for the body.

```json
[
  {
    "type": "ellipse",
    "id": "user_head",
    "x": 130, "y": 80,
    "width": 40, "height": 40,
    "strokeColor": "#7c3aed",
    "backgroundColor": "#ede9fe",
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 72001,
    "version": 1,
    "versionNonce": 72002,
    "isDeleted": false,
    "groupIds": ["user_icon_group"],
    "boundElements": null,
    "link": null,
    "locked": false
  },
  {
    "type": "rectangle",
    "id": "user_body",
    "x": 115, "y": 125,
    "width": 70, "height": 50,
    "strokeColor": "#7c3aed",
    "backgroundColor": "#ede9fe",
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 72003,
    "version": 1,
    "versionNonce": 72004,
    "isDeleted": false,
    "groupIds": ["user_icon_group"],
    "boundElements": null,
    "link": null,
    "locked": false,
    "roundness": {"type": 3}
  },
  {
    "type": "text",
    "id": "user_icon_label",
    "x": 115, "y": 180,
    "width": 70, "height": 20,
    "text": "User",
    "originalText": "User",
    "fontSize": 14,
    "fontFamily": 3,
    "textAlign": "center",
    "verticalAlign": "top",
    "strokeColor": "#7c3aed",
    "backgroundColor": "transparent",
    "fillStyle": "solid",
    "strokeWidth": 1,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 72005,
    "version": 1,
    "versionNonce": 72006,
    "isDeleted": false,
    "groupIds": ["user_icon_group"],
    "boundElements": null,
    "link": null,
    "locked": false,
    "containerId": null,
    "lineHeight": 1.25
  }
]
```

### Lock Icon (rectangle + ellipse keyhole)

Represent security or authentication with a lock shape.

```json
[
  {
    "type": "rectangle",
    "id": "lock_body",
    "x": 120, "y": 120,
    "width": 60, "height": 50,
    "strokeColor": "#b45309",
    "backgroundColor": "#fef3c7",
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 73001,
    "version": 1,
    "versionNonce": 73002,
    "isDeleted": false,
    "groupIds": ["lock_group"],
    "boundElements": null,
    "link": null,
    "locked": false,
    "roundness": {"type": 3}
  },
  {
    "type": "ellipse",
    "id": "lock_shackle",
    "x": 130, "y": 95,
    "width": 40, "height": 35,
    "strokeColor": "#b45309",
    "backgroundColor": "transparent",
    "fillStyle": "solid",
    "strokeWidth": 3,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 73003,
    "version": 1,
    "versionNonce": 73004,
    "isDeleted": false,
    "groupIds": ["lock_group"],
    "boundElements": null,
    "link": null,
    "locked": false
  },
  {
    "type": "ellipse",
    "id": "lock_keyhole",
    "x": 143, "y": 133,
    "width": 14, "height": 14,
    "strokeColor": "#b45309",
    "backgroundColor": "#b45309",
    "fillStyle": "solid",
    "strokeWidth": 1,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 73005,
    "version": 1,
    "versionNonce": 73006,
    "isDeleted": false,
    "groupIds": ["lock_group"],
    "boundElements": null,
    "link": null,
    "locked": false
  }
]
```

### Gear Icon (ellipse + rotated rectangles)

Represent settings or processing with a central circle and surrounding teeth.

```json
[
  {
    "type": "ellipse",
    "id": "gear_center",
    "x": 130, "y": 110,
    "width": 40, "height": 40,
    "strokeColor": "#6b7280",
    "backgroundColor": "#e5e7eb",
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 74001,
    "version": 1,
    "versionNonce": 74002,
    "isDeleted": false,
    "groupIds": ["gear_group"],
    "boundElements": null,
    "link": null,
    "locked": false
  },
  {
    "type": "ellipse",
    "id": "gear_outer",
    "x": 118, "y": 98,
    "width": 64, "height": 64,
    "strokeColor": "#6b7280",
    "backgroundColor": "transparent",
    "fillStyle": "solid",
    "strokeWidth": 4,
    "strokeStyle": "solid",
    "roughness": 0,
    "opacity": 100,
    "angle": 0,
    "seed": 74003,
    "version": 1,
    "versionNonce": 74004,
    "isDeleted": false,
    "groupIds": ["gear_group"],
    "boundElements": null,
    "link": null,
    "locked": false
  }
]
```

### Unicode/Emoji Text Elements

For quick visual enrichment, use Unicode symbols as text elements:

| Symbol | Unicode | Use For |
|--------|---------|---------|
| `⚡` | Lightning | Event, trigger, fast |
| `🔒` | Lock | Security, auth |
| `🗄️` | Cabinet | Database, storage |
| `☁️` | Cloud | Cloud service |
| `👤` | Person | User, actor |
| `⚙️` | Gear | Config, processing |
| `📧` | Email | Notifications |
| `🔔` | Bell | Alerts |
| `📊` | Chart | Analytics, metrics |
| `🔑` | Key | Auth, API key |

```json
{
  "type": "text",
  "id": "icon_db",
  "x": 100, "y": 100,
  "width": 30, "height": 30,
  "text": "🗄️",
  "originalText": "🗄️",
  "fontSize": 24,
  "fontFamily": 1,
  "textAlign": "center",
  "verticalAlign": "middle",
  "strokeColor": "#000000",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 1,
  "strokeStyle": "solid",
  "roughness": 0,
  "opacity": 100,
  "angle": 0,
  "seed": 75001,
  "version": 1,
  "versionNonce": 75002,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": null,
  "link": null,
  "locked": false,
  "containerId": null,
  "lineHeight": 1.25
}
```

**Tip**: Place a Unicode symbol text element above or inside a shape to give it an icon. Use `fontFamily: 1` (Virgil) for best emoji rendering.
