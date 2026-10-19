"""Small native VSDX writer: top-level shapes and glued straight connectors.

Use a neutral package seed; do not apply this new-document writer to existing
multi-page drawings. All public geometry coordinates use a top-left page origin.
Connection anchors alone use normalized local coordinates with y upward.
"""
import math
import os
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as E
import zipfile

V = 'http://schemas.microsoft.com/office/visio/2012/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
E.register_namespace('', V)
E.register_namespace('r', R)
q = lambda name: '{' + V + '}' + name
UNITS = {'in': 1.0, 'px': 96.0, 'pt': 72.0, 'mm': 25.4}
TRANSFORMS = {
    'PinX': '(BeginX+EndX)/2', 'PinY': '(BeginY+EndY)/2',
    'Width': 'SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)',
    'LocPinX': 'Width*0.5', 'Angle': 'ATAN2(EndY-BeginY,EndX-BeginX)',
}


def finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Non-finite numeric value')
    return number


def fmt(value):
    return format(value, '.15g') if isinstance(value, (int, float)) else str(value)


def cell(parent, name, value, formula=None):
    found = parent.find(f"{q('Cell')}[@N='{name}']")
    if found is None:
        found = E.SubElement(parent, q('Cell'), N=name)
    found.set('V', fmt(value))
    found.attrib.pop('F', None)
    if formula is not None:
        found.set('F', formula)
    return found


def number(parent, name, default=None):
    found = parent.find(f"{q('Cell')}[@N='{name}']")
    if found is None:
        if default is None:
            raise ValueError(f'Missing explicit cell {name}')
        return default
    return finite(found.get('V'))


def hex_color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', value):
        raise ValueError(f'Expected #RRGGBB color, got {value!r}')
    return value.upper()


def xml(root):
    return E.tostring(root, encoding='utf-8', xml_declaration=True)


def local_point(shape, rx, ry, changes=None):
    """Transform a proportional anchor on a top-level shape to page inches."""
    vals = {n: number(shape, n, 0) for n in
            ('PinX', 'PinY', 'Width', 'Height', 'LocPinX', 'LocPinY',
             'Angle', 'FlipX', 'FlipY')}
    changes = changes or {}
    vals.update(changes)
    for axis, dimension in [('X', 'Width'), ('Y', 'Height')]:
        if dimension in changes:
            c = shape.find(f"{q('Cell')}[@N='LocPin{axis}']")
            if c is None or c.get('F') != dimension + '*0.5':
                raise ValueError('Unsupported resize: local pin is not proportional')
            vals['LocPin' + axis] = vals[dimension] * .5
    dx = (vals['Width'] * rx - vals['LocPinX']) * (-1 if vals['FlipX'] else 1)
    dy = (vals['Height'] * ry - vals['LocPinY']) * (-1 if vals['FlipY'] else 1)
    co, si = math.cos(vals['Angle']), math.sin(vals['Angle'])
    return vals['PinX'] + co * dx - si * dy, vals['PinY'] + si * dx + co * dy


def frame_connector(shape, start, end):
    bx, by = start
    ex, ey = end
    length = math.hypot(ex-bx, ey-by)
    vals = {'PinX': (bx+ex)/2, 'PinY': (by+ey)/2, 'Width': length,
            'Height': 0, 'LocPinX': length/2, 'LocPinY': 0,
            'Angle': math.atan2(ey-by, ex-bx)}
    for n, v in vals.items():
        cell(shape, n, v, TRANSFORMS.get(n))
    line = shape.find(f"{q('Section')}[@N='Geometry']/{q('Row')}[@IX='2']")
    if line is not None:
        cell(line, 'X', length, 'Width')


class Drawing:
    def __init__(self, width, height, unit='px', name='Diagram'):
        self.scale = UNITS[unit]
        self.width, self.height = finite(width)/self.scale, finite(height)/self.scale
        if min(self.width, self.height) <= 0:
            raise ValueError('Page dimensions must be positive')
        self.name = str(name)
        template = Path(__file__).resolve().parent.parent / 'assets/blank.vsdx'
        with zipfile.ZipFile(template) as z:
            self.parts = {n: z.read(n) for n in z.namelist()}
        self.page = E.Element(q('PageContents'), {'{http://www.w3.org/XML/1998/namespace}space': 'preserve'})
        self.shapes = E.SubElement(self.page, q('Shapes'))
        self.connects = E.SubElement(self.page, q('Connects'))
        self.byid = {}
        self.fonts = set()

    def _new(self, sid, name):
        sid = str(sid)
        if not sid.isdigit() or int(sid) < 1 or sid in self.byid:
            raise ValueError(f'Invalid or duplicate native ID {sid!r}')
        shape = E.SubElement(self.shapes, q('Shape'), ID=sid, NameU='Shape.'+sid,
                             Name=str(name), Type='Shape', LineStyle='0', FillStyle='0', TextStyle='0')
        for n in ('LockSelect', 'LockMoveX', 'LockMoveY', 'LockRotate',
                  'LockTextEdit', 'LockBegin', 'LockEnd', 'NoLiveDynamics'):
            cell(shape, n, 0)
        self.byid[sid] = shape
        return shape

    def box(self, sid, x, y, width, height, name='', fill='#FFFFFF',
            stroke='#000000', stroke_pt=1, radius=0, line_pattern=1,
            angle_deg=0, flip_x=False, flip_y=False, vertices=None):
        x, y, w, h = [finite(n)/self.scale for n in (x, y, width, height)]
        if min(w, h) <= 0 or finite(stroke_pt) < 0 or finite(radius) < 0:
            raise ValueError('Invalid shape dimensions or line width/radius')
        s = self._new(sid, name or f'Box {sid}')
        for n, val, formula in [
            ('PinX', x+w/2, None), ('PinY', self.height-y-h/2, None),
            ('Width', w, None), ('Height', h, None), ('LocPinX', w/2, 'Width*0.5'),
            ('LocPinY', h/2, 'Height*0.5'), ('Angle', math.radians(finite(angle_deg)), None),
            ('FlipX', int(bool(flip_x)), None), ('FlipY', int(bool(flip_y)), None),
            ('FillPattern', int(fill is not None), None), ('FillForegnd', hex_color(fill) if fill else '#FFFFFF', None),
            ('LinePattern', int(line_pattern) if stroke is not None else 0, None),
            ('LineColor', hex_color(stroke) if stroke else '#000000', None),
            ('LineWeight', finite(stroke_pt)/72, None),
            ('Rounding', min(finite(radius)/self.scale, w/2, h/2), None),
            ('BeginArrow', 0, None), ('EndArrow', 0, None),
        ]:
            cell(s, n, val, formula)
        vertices = vertices if vertices is not None else [(0, 0), (1, 0), (1, 1), (0, 1)]
        if len(vertices) < 3:
            raise ValueError('A polygon needs at least three vertices')
        points = [(finite(a), finite(b)) for a, b in vertices]
        if points[-1] != points[0]:
            points.append(points[0])
        g = E.SubElement(s, q('Section'), N='Geometry', IX='0')
        cell(g, 'NoFill', int(fill is None))
        cell(g, 'NoLine', int(stroke is None))
        for i, (a, b) in enumerate(points, 1):
            r = E.SubElement(g, q('Row'), IX=str(i), T='MoveTo' if i == 1 else 'LineTo')
            cell(r, 'X', w*a, 'Width*'+fmt(a))
            cell(r, 'Y', h*b, 'Height*'+fmt(b))
        return s

    def text(self, sid, x, y, width, height, text, font='Arial', font_pt=12,
             color='#000000', bold=False, align='center', vertical='center',
             padding_pt=0, angle_deg=0, flip_x=False, flip_y=False, name=''):
        if finite(font_pt) <= 0 or finite(padding_pt) < 0:
            raise ValueError('Font size must be positive and padding nonnegative')
        s = self.box(sid, x, y, width, height, name=name or str(text),
                     fill=None, stroke=None, angle_deg=angle_deg,
                     flip_x=flip_x, flip_y=flip_y)
        for n in ('LeftMargin', 'RightMargin', 'TopMargin', 'BottomMargin'):
            cell(s, n, finite(padding_pt)/72)
        cell(s, 'VerticalAlign', {'top': 0, 'center': 1, 'bottom': 2}[vertical])
        cell(s, 'TextBkgndTrans', 1)
        section = E.SubElement(s, q('Section'), N='Character')
        row = E.SubElement(section, q('Row'), IX='0')
        self.fonts.add(str(font))
        for n, value in [('Font', font), ('AsianFont', font), ('Color', hex_color(color)),
                         ('Size', finite(font_pt)/72), ('Style', int(bool(bold))), ('FontScale', 1)]:
            cell(row, n, value)
        row = E.SubElement(E.SubElement(s, q('Section'), N='Paragraph'), q('Row'), IX='0')
        for n, val in [('HorzAlign', {'left': 0, 'center': 1, 'right': 2}[align]),
                       ('IndFirst', 0), ('IndLeft', 0), ('IndRight', 0),
                       ('SpBefore', 0), ('SpAfter', 0), ('SpLine', -1)]:
            cell(row, n, val)
        tx = E.SubElement(s, q('Text'))
        E.SubElement(tx, q('cp'), IX='0')
        E.SubElement(tx, q('pp'), IX='0').tail = str(text)
        return s

    def _endpoint(self, connector, which, spec):
        if set(spec) == {'point'}:
            x, y = spec['point']
            return finite(x)/self.scale, self.height-finite(y)/self.scale
        if set(spec) - {'shape', 'anchor'} or 'shape' not in spec:
            raise ValueError('Endpoint must contain shape/anchor or point')
        sid = str(spec['shape'])
        target = self.byid[sid]
        if target.find(f"{q('Cell')}[@N='BeginX']") is not None:
            raise ValueError('Connector targets must be ordinary shapes')
        rx, ry = [finite(n) for n in spec.get('anchor', (.5, .5))]
        sec = target.find(f"{q('Section')}[@N='Connection']")
        if sec is None:
            sec = E.SubElement(target, q('Section'), N='Connection')
        ix = max([int(r.get('IX')) for r in sec.findall(q('Row'))], default=-1)+1
        row = E.SubElement(sec, q('Row'), IX=str(ix))
        for axis, dimension, ratio in [('X', 'Width', rx), ('Y', 'Height', ry)]:
            cell(row, axis, number(target, dimension)*ratio, dimension+'*'+fmt(ratio))
        for n, val in [('DirX', -1 if rx == 0 else 1 if rx == 1 else 0),
                       ('DirY', -1 if ry == 0 else 1 if ry == 1 else 0), ('Type', 0)]:
            cell(row, n, val)
        p = f'LOCTOPAR(PNT(Sheet.{sid}!Connections.X{ix+1},Sheet.{sid}!Connections.Y{ix+1}),Sheet.{sid}!Width,Width)'
        coords = local_point(target, rx, ry)
        for axis, val in zip(('X', 'Y'), coords):
            cell(connector, which+axis, val, f'PNT{axis}({p})')
        cell(connector, 'BegTrigger' if which == 'Begin' else 'EndTrigger', 2,
             f'_XFTRIGGER(Sheet.{sid}!EventXFMod)')
        E.SubElement(self.connects, q('Connect'), FromSheet=connector.get('ID'),
                     FromCell=which+'X', FromPart='9' if which == 'Begin' else '12',
                     ToSheet=sid, ToCell=f'Connections.X{ix+1}', ToPart=str(100+ix))
        return coords

    def connector(self, sid, start, end, name='', color='#000000', stroke_pt=1,
                  line_pattern=1, begin_arrow=0, end_arrow=4, arrow_size=2,
                  begin_arrow_size=None, end_arrow_size=None):
        if finite(stroke_pt) < 0:
            raise ValueError('Negative line width')
        sizes = [arrow_size if x is None else x for x in (begin_arrow_size, end_arrow_size)]
        if any(int(x) != x or not 0 <= x <= 6 for x in sizes):
            raise ValueError('Native arrow sizes must be integers 0..6')
        if any(int(x) != x or not 0 <= x <= 45 for x in (begin_arrow, end_arrow)):
            raise ValueError('Native arrow styles must be integers 0..45')
        s = self._new(sid, name or f'Connector {sid}')
        for n, value in [('LineColor', hex_color(color)), ('LineWeight', finite(stroke_pt)/72),
                         ('LinePattern', int(line_pattern)), ('FillPattern', 0),
                         ('BeginArrow', begin_arrow), ('EndArrow', end_arrow),
                         ('BeginArrowSize', sizes[0]), ('EndArrowSize', sizes[1]),
                         ('ObjType', 2), ('GlueType', 0), ('ConFixedCode', 1), ('ShapeRouteStyle', 2)]:
            cell(s, n, value)
        ends = []
        for which, spec in [('Begin', start), ('End', end)]:
            coords = self._endpoint(s, which, spec)
            for axis, val in zip(('X', 'Y'), coords):
                if s.find(f"{q('Cell')}[@N='{which+axis}']") is None:
                    cell(s, which+axis, val)
            ends.append(coords)
        g = E.SubElement(s, q('Section'), N='Geometry', IX='0')
        cell(g, 'NoFill', 1)
        cell(g, 'NoLine', 0)
        for i, typ in [(1, 'MoveTo'), (2, 'LineTo')]:
            row = E.SubElement(g, q('Row'), IX=str(i), T=typ)
            cell(row, 'X', 0, '0' if i == 1 else 'Width')
            cell(row, 'Y', 0, '0')
        frame_connector(s, *ends)
        return s

    def save(self, destination, overwrite=False):
        destination = Path(destination)
        if destination.exists() and not overwrite:
            raise FileExistsError(f'{destination} already exists; use --overwrite deliberately')
        doc = E.fromstring(self.parts['visio/document.xml'])
        faces = doc.find(q('FaceNames'))
        if faces is None:
            raise ValueError('Seed has no FaceNames section')
        for font in sorted(self.fonts):
            if not any(e.get('NameU') == font for e in faces):
                E.SubElement(faces, q('FaceName'), NameU=font)
        self.parts['visio/document.xml'] = xml(doc)
        pages = E.fromstring(self.parts['visio/pages/pages.xml'])
        pg = pages.find(q('Page'))
        pg.set('Name', self.name)
        pg.set('NameU', self.name)
        pg.set('ViewCenterX', fmt(self.width/2))
        pg.set('ViewCenterY', fmt(self.height/2))
        sheet = pg.find(q('PageSheet'))
        for n, val in [('PageWidth', self.width), ('PageHeight', self.height),
                       ('DrawingSizeType', 0), ('DrawingResizeType', 0),
                       ('PrintPageOrientation', 2 if self.width > self.height else 1)]:
            cell(sheet, n, val)
        self.parts['visio/pages/pages.xml'] = xml(pages)
        self.parts['visio/pages/page1.xml'] = xml(self.page)
        core = E.fromstring(self.parts['docProps/core.xml'])
        title = core.find('{http://purl.org/dc/elements/1.1/}title')
        if title is not None:
            title.text = self.name
        self.parts['docProps/core.xml'] = xml(core)
        destination.parent.mkdir(parents=True, exist_ok=True)
        handle, tmp = tempfile.mkstemp(dir=destination.parent, suffix='.vsdx')
        os.close(handle)
        try:
            with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
                for n, data in self.parts.items():
                    z.writestr(n, data)
            os.replace(tmp, destination)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def build_scene(scene, destination, overwrite=False):
    if set(scene) != {'page', 'objects'}:
        raise ValueError('Scene requires only page and objects')
    drawing = Drawing(**scene['page'])
    objects = scene['objects']
    ids = [o['id'] for o in objects]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Object IDs must be unique, nonempty strings')
    mapping = {alias: i+1 for i, alias in enumerate(ids)}
    for connectors in (False, True):
        for obj in objects:
            opts = dict(obj)
            alias, kind = opts.pop('id'), opts.pop('kind')
            if (kind == 'connector') != connectors:
                continue
            if kind not in ('box', 'text', 'connector'):
                raise ValueError(f'Unsupported object kind {kind!r}')
            if connectors:
                for end in ('start', 'end'):
                    opts[end] = dict(opts[end])
                    if 'shape' in opts[end]:
                        opts[end]['shape'] = mapping[opts[end]['shape']]
            getattr(drawing, kind)(mapping[alias], **opts)
    # Construction is dependency ordered; paint order follows the input array.
    for shape in list(drawing.shapes):
        drawing.shapes.remove(shape)
    for alias in ids:
        drawing.shapes.append(drawing.byid[str(mapping[alias])])
    drawing.save(destination, overwrite=overwrite)
    return mapping
