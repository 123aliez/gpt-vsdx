# Basic scene builder

Use this format for new single-page diagrams made from top-level rectangles, polygons, text and straight connectors. It is a basic writing path, not an automatic image-to-diagram conversion. Transcribe exact content and choose layout/style from the current request before constructing JSON.

```json
{
  "page": {"width": 1000, "height": 600, "unit": "px", "name": "Workflow"},
  "objects": [
    {"id":"a", "kind":"box", "x":80, "y":180, "width":280, "height":150,
     "fill":"#FFFFFF", "stroke":"#000000", "stroke_pt":1.5, "radius":12},
    {"id":"label-a", "kind":"text", "x":90, "y":205, "width":260, "height":100,
     "text":"Input", "font":"Arial", "font_pt":24, "color":"#000000"},
    {"id":"b", "kind":"box", "x":620, "y":180, "width":280, "height":150,
     "fill":"#FFFFFF", "stroke":"#000000", "stroke_pt":1.5},
    {"id":"label-b", "kind":"text", "x":630, "y":205, "width":260, "height":100,
     "text":"Output", "font":"Arial", "font_pt":24},
    {"id":"flow", "kind":"connector",
     "start":{"shape":"a","anchor":[1,0.5]},
     "end":{"shape":"b","anchor":[0,0.5]},
     "color":"#000000", "stroke_pt":1.5, "end_arrow":4, "arrow_size":2}
  ]
}
```

Treat the example's neutral styling as illustration, not a recommended theme. Explicitly supply this task's visual choices.

- Require page.width, page.height; allow unit px, pt, mm, in (default px). Use top-left x/y and page units for geometry/radius. Require unique nonempty object IDs. The builder maps them to native numeric IDs and prints the mapping.
- Require positive width/height for boxes and text. box supports fill/stroke as hex color or null, stroke_pt, radius, line_pattern, angle_deg, flip_x, flip_y. For polygon boxes supply vertices: normalized local [x,y] vertices with y measured upward from the local bottom. The builder closes the path automatically. Use a rectangle when omitted.
- text requires text and supports font, font_pt, color, bold, align (left,center,right), vertical (top,center,bottom), padding_pt and the box transform options. Text is a separate native shape. It does not automatically follow a different box on move; add proper grouping with a more capable implementation when required.
- connector supports start and end as either {"shape":"id","anchor":[rx,ry]} or {"point":[x,y]}. Anchors use **local normalized coordinates with y upward**, so bottom center is [0.5,0], top center [0.5,1]. Free points use page top-left coordinates.
- Supply connector color, stroke_pt, line_pattern, begin_arrow, end_arrow, arrow_size, and optional independent begin_arrow_size / end_arrow_size. Native arrow indices and sizes are Visio formatting choices, not pixel dimensions. Defaults are convenience fallbacks only.
- Preserve object array order for drawing order. Endpoint shape references may point forward; targets must be boxes or text, not other connectors. Separate decorative lines from semantic process connections.
- Do not use the helper to flatten groups, replace curved/orthogonal lines, silently discard pages, or restyle incoming VSDX. Preserve and modify existing package parts or use native automation for those tasks.

Read scripts/native_vsdx.py to extend native geometry deliberately. Validate extensions rather than assuming generic support.
