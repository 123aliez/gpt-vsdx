# Native connector implementation

## Straight connectors

Use this recipe for standalone native straight 1-D shapes, not as a replacement for all valid connector masters. Store lengths in inches, angles in radians. Keep cached V values consistent with F formulas.

| Cell | Formula / value |
| --- | --- |
| PinX | `(BeginX+EndX)/2` |
| PinY | `(BeginY+EndY)/2` |
| Width | `SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)` |
| Height | `0` |
| LocPinX | `Width*0.5` |
| LocPinY | `0` |
| Angle | `ATAN2(EndY-BeginY,EndX-BeginX)` |
| Geometry.0 | MoveTo `(0,0)` → LineTo `(Width,0)` |
| Geometry.0.NoFill | `1` |
| FillPattern | `0` |
| BeginArrow / EndArrow | Choose native style indices to match this task |
| BeginArrowSize / EndArrowSize | Choose each endpoint independently |
| LineColor / LineWeight / LinePattern | Match this task; line weight is inches |
| ObjType | `2` for the helper's routable line |
| ConFixedCode | `1` (reroute as needed) for this straight-line recipe |
| ShapeRouteStyle | `2` (straight) for this recipe |
| NoLiveDynamics | `0` |

Do not use Width=EndX-BeginX for this local geometry. A vertical line needs positive length with a rotated local x-axis. Do not use GUARD(0DA) or another fixed Angle while expecting endpoints to move freely. Avoid protection that blocks intended editing.

Use EndArrow instead of a second geometry triangle or separate head object. Native arrowhead style and size are separate properties; change both only as required. Native sizes scale with line weight, so inspect the rendered result rather than translating pixel triangle dimensions literally.

## Glue both endpoints

For target shape ID S, connection row zero-based index i, and normalized local anchor (rx, ry):

```xml
<Section N="Connection">
  <Row IX="0">
    <Cell N="X" V="..." F="Width*0.5"/>
    <Cell N="Y" V="..." F="Height*1"/>
    <Cell N="DirX" V="0"/>
    <Cell N="DirY" V="1"/>
    <Cell N="Type" V="0"/>
  </Row>
</Section>
```

Use Connections.X{i+1} and Connections.Y{i+1} in formulas. XML row IX is zero based; ShapeSheet positional suffix is one based. For named or inherited rows, resolve the actual universal row reference rather than guessing an index.

For BeginX/BeginY of a connector in its parent's coordinate system:

```text
P = LOCTOPAR(PNT(Sheet.S!Connections.X1,Sheet.S!Connections.Y1),Sheet.S!Width,Width)
BeginX = PNTX(P)
BeginY = PNTY(P)
BegTrigger = _XFTRIGGER(Sheet.S!EventXFMod)
```

Substitute the full expression for P (it is notation, not a declared ShapeSheet variable). Apply equivalent EndX/EndY and EndTrigger formulas. LOCTOPAR handles coordinate transformations including rotations and flips; both shapes must be on the same page. The helper supports only top-level shapes; retain proper group transforms when extending it.

Add matching page-level connection records:

```xml
<Connect FromSheet="C" FromCell="BeginX" FromPart="9"
         ToSheet="S" ToCell="Connections.X1" ToPart="100"/>
<Connect FromSheet="C" FromCell="EndX" FromPart="12"
         ToSheet="T" ToCell="Connections.X2" ToPart="101"/>
```

For this ordinary connection-point convention use ToPart=100+i. Preserve valid alternative conventions when editing existing diagrams. If one end is deliberately free, keep its coordinates editable and omit only that endpoint's glue record.

Keep formula references, connection records, connection rows, cached values and event triggers consistent. Adding Connects records alone does not compute correct coordinates.

## Dynamic routing and repair

For right-angle or curved connectors, prefer native Visio automation or a validated standard connector master with its routing behavior and labels. Preserve functional formulas and geometry inheritance. Do not combine an arbitrary master with overridden fixed transforms, copied vertices and a second arrowhead.

Investigate ConFixedCode, route style, jump settings and protection before changing them. Values 0–3 of ConFixedCode are documented rerouting choices; do not copy undocumented/internal numbers as a portable recipe. A genuine requirement to keep a manually routed path may justify different settings.

Before rebuilding a broken line, record endpoint targets, labels, styling, layers, names and ID. Remove only the conflicting master/geometry/formulas in a narrowly scoped repair. A working dynamic connector does not need replacing by the helper's simpler straight connector.

## Sources

Use primary references to check unfamiliar cells or extend the implementation:

- [EndArrow](https://learn.microsoft.com/en-us/office/client-developer/visio/endarrow-cell-line-format-section)
- [EndArrowSize](https://learn.microsoft.com/en-us/office/client-developer/visio/endarrowsize-cell-line-format-section)
- [ATAN2](https://learn.microsoft.com/en-us/office/client-developer/visio/atan2-function)
- [LOCTOPAR](https://learn.microsoft.com/en-us/office/client-developer/visio/loctopar-function)
- [ConFixedCode](https://learn.microsoft.com/en-us/office/client-developer/visio/confixedcode-cell-shape-layout-section)
- [Cell.GlueTo](https://learn.microsoft.com/en-us/office/vba/api/visio.cell.glueto)
