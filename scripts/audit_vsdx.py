#!/usr/bin/env python3
"""Audit VSDX structure and optionally simulate recognized straight connectors.

This is not an XSD validator, a general ShapeSheet evaluator, or a Visio engine.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote
import xml.etree.ElementTree as E
import zipfile
from native_vsdx import V, R, q, number, local_point, TRANSFORMS

P = 'http://schemas.openxmlformats.org/package/2006/relationships'
C = 'http://schemas.openxmlformats.org/package/2006/content-types'


def relationship_owner(path):
    if path == '_rels/.rels':
        return ''
    folder, leaf = posixpath.split(path)
    return posixpath.join(posixpath.dirname(folder), leaf[:-5])


def rel_target(owner, target):
    return posixpath.normpath(posixpath.join(posixpath.dirname(owner), unquote(target))) if not target.startswith('/') else unquote(target).lstrip('/')


def simulate(shape, top, connections):
    """Return coverage, cases, numeric error, and consistency failures."""
    failures = []
    if shape.get('Master') is not None:
        return {'covered': False, 'reason': 'Inherited connector master requires another evaluator'}, failures
    for n, formula in TRANSFORMS.items():
        c = shape.find(f"{q('Cell')}[@N='{n}']")
        if c is None or c.get('F') != formula:
            return {'covered': False, 'reason': 'Unrecognized transform formula: '+n}, failures
    try:
        if number(shape, 'Height') != 0 or number(shape, 'LocPinY') != 0:
            return {'covered': False, 'reason': 'Nonzero local connector height'}, failures
        geometry = shape.findall(f"{q('Section')}[@N='Geometry']")
        if len(geometry) != 1:
            return {'covered': False, 'reason': 'Multiple or inherited geometries'}, failures
        rows = geometry[0].findall(q('Row'))
        if len(rows) != 2 or [r.get('T') for r in rows] != ['MoveTo', 'LineTo']:
            return {'covered': False, 'reason': 'Non-straight geometry'}, failures
        if number(rows[0], 'X') != 0 or number(rows[0], 'Y') != 0 or number(rows[1], 'Y') != 0:
            return {'covered': False, 'reason': 'Unrecognized geometry endpoints'}, failures
        line_x = rows[1].find(f"{q('Cell')}[@N='X']")
        if line_x.get('F') != 'Width':
            return {'covered': False, 'reason': 'Unrecognized line-length formula'}, failures
        specs = []
        for which in ('Begin', 'End'):
            cs = [shape.find(f"{q('Cell')}[@N='{which+axis}']") for axis in ('X', 'Y')]
            if any(c is None for c in cs):
                return {'covered': False, 'reason': 'Missing explicit endpoints'}, failures
            if all(not c.get('F') or c.get('F') == 'No Formula' for c in cs):
                if (shape.get('ID'), which+'X') in connections:
                    failures.append(which+' has a glue record but constant endpoint coordinates')
                specs.append({'point': tuple(float(c.get('V')) for c in cs)})
                continue
            parsed = []
            for axis, c in zip(('X', 'Y'), cs):
                pattern = (r'PNT'+axis+r'\(LOCTOPAR\(PNT\(Sheet\.(\d+)!Connections\.X(\d+),'
                           r'Sheet\.\1!Connections\.Y\2\),Sheet\.\1!Width,Width\)\)')
                m = re.fullmatch(pattern, c.get('F', ''))
                if not m:
                    return {'covered': False, 'reason': 'Unrecognized endpoint formula'}, failures
                parsed.append((m[1], int(m[2])-1))
            if parsed[0] != parsed[1]:
                failures.append(which+' X/Y reference different anchors')
                return {'covered': False, 'reason': 'Mismatched anchor references'}, failures
            target, ix = parsed[0]
            if target not in top:
                return {'covered': False, 'reason': 'Target is absent or nested in a group'}, failures
            cp = top[target].find(f"{q('Section')}[@N='Connection']/{q('Row')}[@IX='{ix}']")
            if cp is None:
                failures.append(which+' references a missing explicit connection row')
                return {'covered': False, 'reason': 'Missing connection row'}, failures
            ratios = []
            for axis, dim in [('X', 'Width'), ('Y', 'Height')]:
                c = cp.find(f"{q('Cell')}[@N='{axis}']")
                m = re.fullmatch(dim+r'\*([-+0-9.eE]+)', c.get('F', '') if c is not None else '')
                if not m:
                    return {'covered': False, 'reason': 'Connection point is not a recognized proportional formula'}, failures
                ratio = float(m[1])
                if abs(number(cp, axis)-number(top[target], dim)*ratio) > 1e-8:
                    failures.append(which+' connection-row cached coordinate differs from formula')
                ratios.append(ratio)
            record = connections.get((shape.get('ID'), which+'X'))
            if record is None or record.get('ToSheet') != target or record.get('ToCell') != f'Connections.X{ix+1}':
                failures.append(which+' glue record differs from endpoint formula')
            specs.append({'shape': target, 'ratios': ratios})
        def endpoints(changes):
            return [spec['point'] if 'point' in spec else local_point(top[spec['shape']], *spec['ratios'], changes.get(spec['shape'])) for spec in specs]
        start, end = endpoints({})
        for which, p in [('Begin', start), ('End', end)]:
            if math.dist(p, (number(shape, which+'X'), number(shape, which+'Y'))) > 1e-8:
                failures.append(which+' cached endpoint differs from anchor')
        length = math.dist(start, end)
        expect = {'PinX': (start[0]+end[0])/2, 'PinY': (start[1]+end[1])/2,
                  'Width': length, 'LocPinX': length/2,
                  'Angle': math.atan2(end[1]-start[1], end[0]-start[0])}
        for n, expected in expect.items():
            if abs(number(shape, n)-expected) > 1e-8:
                failures.append('Cached transform differs from endpoints: '+n)
        if abs(number(rows[1], 'X')-length) > 1e-8:
            failures.append('Cached geometry length differs from endpoints')
        targets = list(dict.fromkeys(s['shape'] for s in specs if 'shape' in s))
        scenarios = [{}]
        for sid in targets:
            s = top[sid]
            scenarios.extend([
                {sid: {'PinX': number(s, 'PinX')+.7, 'PinY': number(s, 'PinY')-.4}},
                {sid: {'Width': number(s, 'Width')*1.3, 'Height': number(s, 'Height')*.75}},
                {sid: {'Angle': .65}},
                {sid: {'FlipX': 1-number(s, 'FlipX', 0), 'FlipY': 1-number(s, 'FlipY', 0)}},
                {sid: {'PinX': -number(s, 'PinX')-1, 'PinY': number(s, 'PinY')+1.2}},
            ])
        max_error = 0
        for changes in scenarios:
            a, b = endpoints(changes)
            width = math.dist(a, b)
            angle = math.atan2(b[1]-a[1], b[0]-a[0])
            cx, cy = (a[0]+b[0])/2, (a[1]+b[1])/2
            co, si = math.cos(angle), math.sin(angle)
            ends = [(cx+co*t, cy+si*t) for t in (-width/2, width/2)]
            max_error = max(max_error, math.dist(a, ends[0]), math.dist(b, ends[1]))
        if max_error > 1e-8:
            failures.append('Simulated line transform does not reach endpoints')
        return {'covered': True, 'cases': len(scenarios), 'max_error_in': max_error}, failures
    except (ValueError, KeyError, TypeError) as exc:
        return {'covered': False, 'reason': str(exc)}, failures


def audit(path, simulate_connectors=False):
    report = {'file': str(Path(path).resolve()), 'errors': [], 'warnings': [], 'pages': [],
              'media_parts': [], 'visio_open_tested': False, 'visio_drag_tested': False,
              'scope': 'Structural lint and recognized-formula numeric simulation; no XSD or Visio engine'}
    errors, warnings = report['errors'], report['warnings']
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        bad = z.testzip()
        if bad:
            errors.append('ZIP CRC failure: '+bad)
        if len(names) != len(set(names)):
            errors.append('Duplicate ZIP members')
        parts = {n: z.read(n) for n in names if not n.endswith('/')}
    required = {'[Content_Types].xml', '_rels/.rels', 'visio/document.xml', 'visio/pages/pages.xml'}
    for n in sorted(required-set(parts)):
        errors.append('Missing required part: '+n)
    roots = {}
    for n, data in parts.items():
        if n.endswith(('.xml', '.rels')) or n == '[Content_Types].xml':
            try:
                roots[n] = E.fromstring(data)
            except E.ParseError as exc:
                errors.append(f'XML parse error in {n}: {exc}')
    if not required.issubset(roots):
        return report
    types = roots['[Content_Types].xml']
    defaults = {e.get('Extension') for e in types.findall('{'+C+'}Default')}
    overrides = {e.get('PartName', '').lstrip('/') for e in types.findall('{'+C+'}Override')}
    for n in parts:
        if n != '[Content_Types].xml' and n not in overrides and n.rsplit('.', 1)[-1] not in defaults:
            errors.append('No content-type declaration: '+n)
    for n in overrides-set(parts):
        errors.append('Content-type override for missing part: '+n)
    relationships = {}
    for n, root in roots.items():
        if not n.endswith('.rels'):
            continue
        owner = relationship_owner(n)
        byid = {}
        if owner and owner not in parts:
            errors.append('Relationships for nonexistent owner: '+owner)
        for rel in root.findall('{'+P+'}Relationship'):
            rid = rel.get('Id')
            if not rid or rid in byid:
                errors.append('Missing/duplicate relationship ID: '+n)
            byid[rid] = rel
            if rel.get('TargetMode') != 'External':
                target = rel_target(owner, rel.get('Target', ''))
                if target not in parts:
                    errors.append(f'Missing relationship target: {owner} -> {target}')
        relationships[owner] = byid
    for n, root in roots.items():
        if n.endswith('.rels'):
            continue
        for el in root.iter():
            for attr, val in el.attrib.items():
                if attr.startswith('{'+R+'}') and val not in relationships.get(n, {}):
                    errors.append(f'Unresolved XML relationship: {n} {val}')
            if el.tag == q('Cell') and any(t in el.get('F', '') for t in ('#REF!', '#DIV/0!', '#NAME?')):
                errors.append(f'Formula error in {n}: {el.get("N")}')
    document = roots['visio/document.xml']
    if document.tag != q('VisioDocument'):
        errors.append('Wrong Visio document root/namespace')
    styles = {s.get('ID') for s in document.findall(q('StyleSheets')+'/'+q('StyleSheet'))}
    report['style_ids'] = sorted(styles)
    report['document_palette'] = [dict(c.attrib) for c in document.findall(q('Colors')+'/'+q('ColorEntry'))]
    report['declared_fonts'] = [dict(c.attrib) for c in document.findall(q('FaceNames')+'/'+q('FaceName'))]
    master_root = roots.get('visio/masters/masters.xml')
    masters = set() if master_root is None else {m.get('ID') for m in master_root.findall(q('Master'))}
    for n, root in roots.items():
        if n.endswith('.rels'):
            continue
        for el in root.iter():
            for key in ('LineStyle', 'FillStyle', 'TextStyle'):
                if key in el.attrib and el.get(key) not in styles:
                    errors.append(f'Unresolved {key} {el.get(key)} in {n}')
            if el.tag == q('Shape') and el.get('Master') is not None and el.get('Master') not in masters:
                errors.append(f'Unresolved master {el.get("Master")} in {n}')
    report['media_parts'] = [n for n in parts if '/media/' in n]
    manifest = roots['visio/pages/pages.xml']
    page_ids = [p.get('ID') for p in manifest.findall(q('Page'))]
    if len(page_ids) != len(set(page_ids)):
        errors.append('Duplicate page IDs')
    for entry in manifest.findall(q('Page')):
        rr = entry.find(q('Rel'))
        rid = rr.get('{'+R+'}id') if rr is not None else None
        relation = relationships.get('visio/pages/pages.xml', {}).get(rid)
        if relation is None:
            errors.append('Page manifest has no valid content relationship')
            continue
        part = rel_target('visio/pages/pages.xml', relation.get('Target', ''))
        root = roots.get(part)
        if root is None:
            errors.append('Page XML missing or invalid: '+part)
            continue
        all_shapes = root.findall('.//'+q('Shape'))
        top = {s.get('ID'): s for s in root.findall(q('Shapes')+'/'+q('Shape'))}
        byid = {s.get('ID'): s for s in all_shapes}
        if len(all_shapes) != len(byid) or None in byid:
            errors.append('Missing/duplicate shape ID in '+part)
        records = root.findall(q('Connects')+'/'+q('Connect'))
        conmap = {}
        for rec in records:
            source, target = rec.get('FromSheet'), rec.get('ToSheet')
            key = (source, rec.get('FromCell'))
            if key in conmap:
                warnings.append(f'Duplicate connection record {part} {key}')
            conmap[key] = rec
            if source not in byid or target not in byid:
                errors.append(f'Connection references missing shape in {part}: {source}->{target}')
            elif re.fullmatch(r'Connections\.X\d+', rec.get('ToCell', '')):
                ix = int(rec.get('ToCell').split('X')[-1])-1
                cp = byid[target].find(f"{q('Section')}[@N='Connection']/{q('Row')}[@IX='{ix}']")
                if cp is None:
                    if byid[target].get('Master') is not None:
                        warnings.append(f'Inherited connection row requires master resolution: {part} #{target}')
                    else:
                        errors.append(f'Connection references missing row in {part}: #{target} IX={ix}')
        texts, palette = [], Counter()
        info = {'name': entry.get('Name'), 'part': part, 'shapes': len(all_shapes),
                'connection_records': len(records), 'foreign_shapes': 0, 'connectors': [], 'texts': texts}
        for sid, s in byid.items():
            if s.get('Type') == 'Foreign' or s.find(q('ForeignData')) is not None:
                info['foreign_shapes'] += 1
            text = s.find(q('Text'))
            if text is not None:
                texts.append({'id': sid, 'text': ''.join(text.itertext())})
            for c in s.iter(q('Cell')):
                if re.fullmatch(r'#[0-9A-Fa-f]{6}', c.get('V', '')):
                    palette[c.get('V').upper()] += 1
            if s.find(f"{q('Cell')}[@N='BeginX']") is None:
                if s.get('Master') is not None:
                    warnings.append(f'Inherited shape {part} #{sid}: master behavior not evaluated')
                continue
            cinfo = {'id': sid}
            angle = s.find(f"{q('Cell')}[@N='Angle']")
            if angle is not None and ('ATAN2' not in angle.get('F', '').upper()):
                warnings.append(f'Connector {part} #{sid} has a fixed/unrecognized Angle; review edit behavior')
            if simulate_connectors:
                sim, failures = simulate(s, top, conmap)
                cinfo['simulation'] = sim
                errors.extend(f'{part} connector #{sid}: {f}' for f in failures)
                if not sim['covered']:
                    warnings.append(f'Connector {part} #{sid} not simulated: '+sim['reason'])
            info['connectors'].append(cinfo)
        info['explicit_palette'] = dict(palette)
        report['pages'].append(info)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--simulate-connectors', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.file, args.simulate_connectors)
    except (zipfile.BadZipFile, OSError, ValueError, TypeError, KeyError) as exc:
        result = {'file': str(args.file), 'errors': [str(exc)], 'warnings': [],
                  'visio_open_tested': False, 'visio_drag_tested': False}
    content = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content+'\n', encoding='utf-8')
    print(content)
    raise SystemExit(1 if result['errors'] else 0)


if __name__ == '__main__':
    main()
