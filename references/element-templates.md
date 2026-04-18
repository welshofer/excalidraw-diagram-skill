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
