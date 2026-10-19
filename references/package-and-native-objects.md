# Document package, coordinates and native objects

## Package handling

Treat VSDX as an OPC package with linked parts, not an arbitrary ZIP of XML. Preserve content-type declarations, root relationships, document relationships, page manifests, page relationships, styles and referenced masters. Resolve internal relationship targets relative to their owning part; ignore the _rels directory when resolving the base path. Do not leave dangling IDs or targets when deleting a resource.

Retain the default namespaces of OPC Types and Relationships manifests. Prefixes can be XML-equivalent yet cause importer differences; a prefixed OPC variant failed the auxiliary import check while its default-namespace equivalent loaded. Preserve the seed's manifest serialization and validate changes with an actual importer.

Use assets/blank.vsdx only as a neutral new-document foundation. It contains an empty page, neutral base style and no diagram content, custom palette, master or user metadata. It is a sanitized structural seed, not a visual template. Select style attributes in the scene or native shape cells. Its structural and auxiliary-render checks do not establish Microsoft Visio interaction compatibility.

For existing files, copy the original bytes of untouched members. Do not rebuild a multi-page document with the single-page helper or delete unknown metadata, themes, layers, hyperlinks or masters simply because the helper does not use them. Never inherit an unrelated connector master merely to obtain a valid package.

Visio 2012 namespace: http://schemas.microsoft.com/office/visio/2012/main.
OPC relationships namespace: http://schemas.openxmlformats.org/package/2006/relationships.
Office relationship reference namespace: http://schemas.openxmlformats.org/officeDocument/2006/relationships.

## Coordinates

- Store shape coordinates and line weights in inches. Convert points by /72, CSS pixels by /96, millimetres by /25.4. Do not interpret a stored numeric value as points because its display unit is PT.
- For a top-left source rectangle (x,y,w,h) on source page height H, set PinX=(x+w/2)/scale, PinY=(H-y-h/2)/scale, Width=w/scale, Height=h/scale, LocPinX=Width*0.5, LocPinY=Height*0.5.
- Keep scalable rectangle vertices dependent on Width/Height. Use native rounding and line patterns when adequate. Do not bake every dash into independent fragments unless precise reproduction requires it and editing remains usable.
- Separate global, parent and local coordinates when nesting shapes. A group is a coordinate system; adding offsets without rotations/flips/scales is insufficient.

## Text and styling

Use native Text plus Character/Paragraph sections. Register used fonts in document FaceNames; preserve text as Unicode. Set font sizes in inches (font_pt/72), foreground color, weight, alignment and margins explicitly where inherited defaults are unsuitable.

Use independently selectable native text shapes when requested. For moving a box and several labels as one unit, use editable grouping or an appropriate native shape text block; explain the selection model only if it matters to the user. Do not turn text into path outlines.

Inspect reference palette at both document and shape level: color tables alone may omit literal shape colors, master properties, theme colors or overrides. Read effective styling before extracting a shared palette. Apply the requested visual style through parameters; do not distribute an entire user reference drawing as a generic skill asset.

Check actual installed fonts with a font resolver. Install an appropriate licensed font or use a deliberate preview substitution when necessary. Record when preview metrics differ from the intended Visio environment. Do not infer successful typography from an SVG preview produced through a different renderer.

## Original-file preservation

For an edit, snapshot original files, object IDs, texts, transforms, endpoints and relevant properties before mutation. Compare changed package members and object properties afterward. Expected changes may include endpoint formulas, native end formatting, caches and connection rows; an unrelated text/layout change is a regression unless requested.

## Primary references

- [Visio file format overview](https://learn.microsoft.com/en-us/office/client-developer/visio/introduction-to-the-visio-file-formatvsdx)
- [Visio XML reference](https://learn.microsoft.com/en-us/office/client-developer/visio/visio-xml-reference)
- [Cell element](https://learn.microsoft.com/en-us/office/client-developer/visio/cell-elementvisio-xml)
