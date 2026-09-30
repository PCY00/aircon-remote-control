"""Export reviewable JLC BOM/CPL from FINAL user artwork, without modifying CAD.

Example (run only after routing/review and setting the drill/place origin):
  python scripts/hardware/export_user_jlc.py \
    --pcb <artwork-current>/IR_ESP32H2.kicad_pcb \
    --sch <artwork-current>/IR_ESP32H2.kicad_sch \
    --mapping tmp/user-bom-audit-20260920/part-mapping.json \
    --out <artwork-current>/manufacturing/assembly \
    --expected-origin 64.5 94 --kicad-cli <path-to-kicad-cli>

Only BT1/D1 are excluded. Do not filter all through-hole pads: J1 is hybrid.
Positions come from KiCad's native CSV export in mm, using drill/place origin.
The raw export is retained; no JLC rotation correction is guessed. Footprint
origin/centroid and component orientation MUST be checked in the JLC preview.
--self-test runs pure in-memory checks; it does not load/export the live board.

Primary method references (checked 2026-09-20):
https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad
https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly
https://jlcpcb.com/blog/files-needed-for-pcb-assembly
https://docs.kicad.org/10.0/en/cli/cli.html
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

from kicad_sexpr import child, children, read

MANUAL = frozenset({'BT1', 'D1'})
EXPECTED_COMPONENTS = 40
EXPECTED_GROUPS = 27
TOL_MM = 0.00001
BOM_COLUMNS = ['Comment', 'Designator', 'Footprint', 'LCSC Part #']
CPL_COLUMNS = ['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation']
REVIEW_COLUMNS = [
    'Designator', 'MPN', 'LCSC Part #', 'Schematic Value', 'KiCad Footprint',
    'KiCad X mm', 'KiCad Y mm', 'KiCad Rotation deg',
    'CPL Mid X mm', 'CPL Mid Y mm', 'CPL Rotation deg', 'Layer',
    'Pin1 identifier', 'Pin1 KiCad positions mm JSON', 'Pin1 CPL positions mm JSON',
    'Selection note', 'Preview required',
]
OUTPUT_NAMES = (
    'jlc-bom.csv', 'jlc-cpl.csv', 'kicad-position-raw.csv',
    'assembly-review.csv', 'assembly-export.json', 'README-assembly.md',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ref_order(ref):
    return tuple(int(x) if x.isdigit() else x for x in re.split(r'(\d+)', ref))


def props(node):
    return {p[1]: p[2] for p in children(node, 'property')}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value, field):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field}: expected a plain numeric mm/degree value, got {value!r}') from exc
    require(math.isfinite(result), f'{field}: non-finite number')
    return result


def fmt(value):
    value = round(value, 6)
    return f'{0.0 if value == 0 else value:.6f}'.rstrip('0').rstrip('.')


def close(a, b):
    return abs(a - b) <= TOL_MM


def rotation_equal(a, b):
    return abs((a - b + 180) % 360 - 180) <= TOL_MM


def insert_unique(target, ref, value, source):
    require(bool(ref) and not re.search(r'[\s,;]', ref), f'{source}: invalid reference {ref!r}')
    require(ref not in target, f'{source}: duplicate reference {ref}')
    target[ref] = value


def matching_refs(left, right, label):
    require(set(left) == set(right),
            f'{label}: missing={sorted(set(left)-set(right), key=ref_order)}, '
            f'extra={sorted(set(right)-set(left), key=ref_order)}')


def parse_schematic(path):
    doc = read(path)
    require(not children(doc, 'sheet'), 'Hierarchical sheets are not supported; do not silently omit child components')
    result = {}
    for symbol in children(doc, 'symbol'):
        fields = props(symbol)
        ref = fields.get('Reference', '')
        if ref.startswith('#'):
            continue
        insert_unique(result, ref, {'fields': fields, 'node': symbol}, 'schematic')
    return result


def parse_pcb(path, expected_origin):
    doc = read(path)
    setup = child(doc, 'setup', [])
    axis = child(setup, 'aux_axis_origin')
    require(axis is not None and len(axis) == 3,
            'Explicit aux_axis_origin is missing. grid_origin is NOT the drill/place origin; set it in the final PCB first')
    origin = tuple(number(x, 'aux_axis_origin') for x in axis[1:])
    require(all(close(a, b) for a, b in zip(origin, expected_origin)),
            f'Drill/place origin {origin} != required origin {tuple(expected_origin)}')
    result = {}
    for footprint in children(doc, 'footprint'):
        fields = props(footprint)
        ref = fields.get('Reference', '')
        at = child(footprint, 'at')
        require(at is not None and len(at) in (3, 4), f'{ref}: invalid footprint location')
        insert_unique(result, ref, {
            'fields': fields, 'node': footprint, 'footprint': footprint[1],
            'x': number(at[1], ref+' X'), 'y': number(at[2], ref+' Y'),
            'rotation': number(at[3], ref+' rotation') if len(at) == 4 else 0.0,
            'layer': child(footprint, 'layer', ['', ''])[1],
            'attributes': set(child(footprint, 'attr', [])[1:]),
        }, 'PCB')
    return result, origin


def parse_mapping(path):
    rows = json.loads(path.read_text(encoding='utf-8-sig'))
    require(isinstance(rows, list), 'Mapping must be a JSON list of grouped parts')
    result = {}
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get('refs'), list), 'Invalid mapping row')
        require(row.get('mpn'), 'Each mapping row needs an exact MPN')
        for ref in row['refs']:
            insert_unique(result, ref, row, 'mapping')
            if ref in MANUAL:
                require(not row.get('lcsc'), f'{ref}: manual exclusions must not also have a JLC placement code')
            else:
                require(re.fullmatch(r'C\d+', str(row.get('lcsc', ''))) is not None,
                        f'{ref}: missing or invalid LCSC code')
    return result


def check_sources(schematic, pcb, mapping):
    matching_refs(schematic, pcb, 'schematic -> PCB')
    matching_refs(schematic, mapping, 'schematic -> mapping')
    require(MANUAL <= set(schematic), 'Expected manual parts BT1 and D1 are missing')
    refs = sorted(set(schematic)-MANUAL, key=ref_order)
    require(len(refs) == EXPECTED_COMPONENTS, f'Expected {EXPECTED_COMPONENTS} assembled parts, got {len(refs)}')
    for ref in refs:
        sch, fp, part = schematic[ref], pcb[ref], mapping[ref]
        require(fp['layer'] == 'F.Cu', f'{ref}: this exporter is top-only, found {fp["layer"]}')
        forbidden = {'dnp', 'exclude_from_bom', 'exclude_from_pos_files'} & fp['attributes']
        require(not forbidden, f'{ref}: PCB assembly exclusion attributes {sorted(forbidden)}')
        for tag in ('in_bom', 'on_board', 'in_pos_files'):
            require(child(sch['node'], tag, ['', 'yes'])[1] != 'no', f'{ref}: schematic {tag}=no')
        require(child(sch['node'], 'dnp', ['', 'no'])[1] != 'yes', f'{ref}: schematic DNP')
        require(sch['fields'].get('Value') == fp['fields'].get('Value'), f'{ref}: schematic/PCB value mismatch')
        require(sch['fields'].get('Footprint') == fp['footprint'], f'{ref}: schematic/PCB footprint mismatch')
        for fields in (sch['fields'], fp['fields']):
            for key in ('LCSC', 'LCSC Part #', 'JLCPCB Part #'):
                require(not fields.get(key) or fields[key] == part['lcsc'], f'{ref}: {key} conflicts with mapping')
            for key in ('MPN', 'Manufacturer Part Number'):
                require(not fields.get(key) or fields[key] == part['mpn'], f'{ref}: {key} conflicts with mapping')
    require('J1' in refs, 'Hybrid USB connector J1 was accidentally excluded')
    return refs


def parse_positions(text):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    needed = {'Ref', 'PosX', 'PosY', 'Rot', 'Side'}
    require(needed <= set(reader.fieldnames or []), f'Unexpected KiCad position CSV header: {reader.fieldnames}')
    result = {}
    for row in reader:
        ref = row['Ref']
        insert_unique(result, ref, {
            'x': number(row['PosX'], ref+' PosX mm'),
            'y': number(row['PosY'], ref+' PosY mm'),
            'rotation': number(row['Rot'], ref+' Rot deg'),
            'side': row['Side'].strip().lower(),
        }, 'KiCad position CSV')
    return result


def check_positions(refs, positions, pcb, origin):
    require(set(refs) <= set(positions), f'Position CSV missing assembled references {sorted(set(refs)-set(positions))}')
    require(set(positions) <= set(pcb), f'Position CSV has unknown references {sorted(set(positions)-set(pcb))}')
    for ref in refs:
        point, fp = positions[ref], pcb[ref]
        require(point['side'] in ('top', 'front'), f'{ref}: expected top-side raw position, got {point["side"]}')
        # KiCad absolute PCB Y increases downward; its mm position export is Y-up.
        expected_x, expected_y = fp['x']-origin[0], origin[1]-fp['y']
        require(close(point['x'], expected_x) and close(point['y'], expected_y),
                f'{ref}: raw mm coordinates do not match PCB/origin: raw {(point["x"],point["y"])} '
                f'expected {(expected_x,expected_y)}. Check units/origin/export behavior; do not guess corrections')
        require(rotation_equal(point['rotation'], fp['rotation']), f'{ref}: raw/PCB rotation mismatch')


def pin1_positions(fp, origin):
    pads = children(fp['node'], 'pad')
    pin = '1' if any(p[1] == '1' for p in pads) else 'A1' if any(p[1] == 'A1' for p in pads) else ''
    absolute, exported = [], []
    theta = math.radians(fp['rotation'])
    for pad in pads:
        if not pin or pad[1] != pin:
            continue
        at = child(pad, 'at')
        require(at is not None, 'Pin 1 has no location')
        lx, ly = number(at[1], 'pin1 X'), number(at[2], 'pin1 Y')
        x = fp['x'] + math.cos(theta)*lx + math.sin(theta)*ly
        y = fp['y'] - math.sin(theta)*lx + math.cos(theta)*ly
        absolute.append([round(x, 6), round(y, 6)])
        exported.append([round(x-origin[0], 6), round(origin[1]-y, 6)])
    return pin, absolute, exported


def build_rows(refs, schematic, pcb, mapping, positions, origin):
    groups = {}
    cpl, review = [], []
    for ref in refs:
        part, fp, point = mapping[ref], pcb[ref], positions[ref]
        key = (part['mpn'], fp['footprint'], part['lcsc'])
        groups.setdefault(key, []).append(ref)
        cpl.append(dict(zip(CPL_COLUMNS, [ref, fmt(point['x']), fmt(point['y']), 'Top', fmt(point['rotation'])])))
        pin, absolute, exported = pin1_positions(fp, origin)
        require(pin and absolute, f'{ref}: no pin 1/A1 anchor; cannot complete independent assembly review')
        review.append(dict(zip(REVIEW_COLUMNS, [
            ref, part['mpn'], part['lcsc'], schematic[ref]['fields']['Value'], fp['footprint'],
            fmt(fp['x']), fmt(fp['y']), fmt(fp['rotation']),
            fmt(point['x']), fmt(point['y']), fmt(point['rotation']), 'Top', pin,
            json.dumps(absolute), json.dumps(exported), part.get('selection', ''),
            'YES: verify centroid, pad 1/polarity and vendor zero-angle in JLC placement preview',
        ])))
    require(len(groups) == EXPECTED_GROUPS, f'Expected {EXPECTED_GROUPS} BOM groups, got {len(groups)}')
    bom = [dict(zip(BOM_COLUMNS, [mpn, ','.join(designators), footprint.split(':')[-1], code]))
           for (mpn, footprint, code), designators in groups.items()]
    matching_refs(refs, [ref for row in bom for ref in row['Designator'].split(',')], 'BOM coverage')
    matching_refs(refs, [r['Designator'] for r in cpl], 'CPL coverage')
    return bom, cpl, review


def csv_text(columns, rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def validate_output_text(bom_text, cpl_text, expected_refs):
    bom = list(csv.DictReader(io.StringIO(bom_text)))
    cpl = list(csv.DictReader(io.StringIO(cpl_text)))
    brefs = [ref for row in bom for ref in row['Designator'].split(',')]
    crefs = [row['Designator'] for row in cpl]
    require(len(brefs) == len(set(brefs)) == EXPECTED_COMPONENTS, 'Duplicate/missing BOM designator')
    require(len(crefs) == len(set(crefs)) == EXPECTED_COMPONENTS, 'Duplicate/missing CPL designator')
    matching_refs(expected_refs, brefs, 'serialized BOM coverage')
    matching_refs(expected_refs, crefs, 'serialized CPL coverage')
    require(len(bom) == EXPECTED_GROUPS, 'Serialized BOM group mismatch')
    for row in cpl:
        require(row['Layer'] == 'Top', 'Serialized CPL is not top-only')
        for key in ('Mid X', 'Mid Y', 'Rotation'):
            number(row[key], key)
    require(not (MANUAL & set(crefs)), 'Manual part leaked into CPL')


def export(args):
    inputs = {'pcb': args.pcb.resolve(), 'schematic': args.sch.resolve(), 'mapping': args.mapping.resolve()}
    for path in inputs.values():
        require(path.is_file(), f'Input file does not exist: {path}')
    hashes = {key: digest(path) for key, path in inputs.items()}
    schematic = parse_schematic(inputs['schematic'])
    pcb, origin = parse_pcb(inputs['pcb'], args.expected_origin)
    mapping = parse_mapping(inputs['mapping'])
    refs = check_sources(schematic, pcb, mapping)
    out = args.out.resolve()
    require(all(out/name not in inputs.values() for name in OUTPUT_NAMES), 'Output would overwrite an input')
    existing = [name for name in OUTPUT_NAMES if (out/name).exists()]
    require(not existing or args.overwrite, f'Generated files already exist: {existing}; choose a new output or --overwrite')
    cli = shutil.which(args.kicad_cli) or args.kicad_cli
    with tempfile.TemporaryDirectory(prefix='ir-h2-jlc-export-') as task_tmp:
        raw_path = Path(task_tmp)/'kicad-position-raw.csv'
        command = [cli, 'pcb', 'export', 'pos', '--format', 'csv', '--units', 'mm',
                   '--side', 'both', '--use-drill-file-origin', '--output', str(raw_path), str(inputs['pcb'])]
        # No --smd-only / --exclude-fp-th: hybrid USB connector J1 must survive.
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
        require(result.returncode == 0, f'KiCad position export failed ({result.returncode}): {result.stderr.strip()}')
        require(raw_path.is_file(), 'KiCad returned success without the requested raw CSV')
        raw_text = raw_path.read_text(encoding='utf-8-sig')
    require(hashes == {key: digest(path) for key, path in inputs.items()},
            'Inputs changed during export. Save/finalize the board and rerun; no final files written')
    positions = parse_positions(raw_text)
    check_positions(refs, positions, pcb, origin)
    bom, cpl, review = build_rows(refs, schematic, pcb, mapping, positions, origin)
    bom_text, cpl_text = csv_text(BOM_COLUMNS, bom), csv_text(CPL_COLUMNS, cpl)
    validate_output_text(bom_text, cpl_text, refs)
    manifest = {
        'generated_utc': datetime.now(timezone.utc).isoformat(), 'manufacture_ready': False,
        'input_files': {key: {'name': path.name, 'sha256': hashes[key]} for key, path in inputs.items()},
        'units': 'mm', 'drill_place_origin_kicad_mm': list(origin),
        'export_method': 'kicad-cli pcb export pos --format csv --units mm --side both --use-drill-file-origin',
        'coordinate_check': 'Each exported point checked against PCB X-originX, originY-PCB Y',
        'rotation_policy': 'Native KiCad exported degrees unchanged; no vendor correction or production orientation guarantee',
        'components': len(refs), 'bom_groups': len(bom), 'top_only': True,
        'manual_exclusions': sorted(MANUAL), 'hybrid_usb_J1_included': 'J1' in refs,
        'assembly_review_required': True, 'gerber_and_drill_origin_must_match': True,
        'unvalidated': ['JLC centroid/rotation/polarity preview', 'live stock and quote',
                        'component/footprint selection acceptance', 'electrical design', 'ERC/DRC'],
    }
    readme = f'''# JLCPCB assembly export — review required

Generated from saved final PCB and matching schematic; this exporter never writes CAD.
{len(refs)} Top components / {len(bom)} BOM groups. Only BT1 and D1 are manually soldered
and excluded. Hybrid USB connector J1 remains included.

- `jlc-bom.csv`: Comment=exact proposed MPN, grouped by MPN/LCSC/actual footprint.
- `jlc-cpl.csv`: native KiCad placement export; coordinates in mm, rotations in degrees.
- `kicad-position-raw.csv`: unmodified KiCad CSV content before reference filtering.
- `assembly-review.csv`: original KiCad footprint position/rotation, pin 1 (or USB A1)
  absolute and exported coordinates, exact MPN, selection caveats.
- `assembly-export.json`: input hashes, method and validation scope.

Drill/place origin: ({fmt(origin[0])}, {fmt(origin[1])}) mm in KiCad absolute coordinates.
This is aux_axis_origin, NOT grid_origin. Export Gerber/drill files with the SAME
origin; this tool does not export or verify those files. Raw CPL coordinates were
independently checked against (PCB X - origin X, origin Y - PCB Y).

The exported Mid X/Y are KiCad footprint origins. A custom footprint origin is not
automatically proven to be the physical pick-up centroid. No vendor-specific
rotation offsets were guessed. Check every component's centroid, pad 1, polarity,
and rotation in JLCPCB's placement preview before authorizing production.
Repeated pin 1 positions are retained as JSON arrays in the review CSV.

Passing these data-integrity checks does not approve electrical design, routing,
DRC, exact part selection, stock availability, manufacturing, or real operation.
U2 H4S catalog currently requires Standard PCBA and X-ray inspection. Check again
when ordering. Selection notes originate in the separate reviewed mapping file;
they are not proof that those MPN fields were already present in CAD.

Sources:
- https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad
- https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly
- https://jlcpcb.com/blog/files-needed-for-pcb-assembly
- https://docs.kicad.org/10.0/en/cli/cli.html
'''
    payloads = {
        'jlc-bom.csv': bom_text, 'jlc-cpl.csv': cpl_text, 'kicad-position-raw.csv': raw_text,
        'assembly-review.csv': csv_text(REVIEW_COLUMNS, review),
        'assembly-export.json': json.dumps(manifest, indent=2, ensure_ascii=False)+'\n',
        'README-assembly.md': readme,
    }
    if args.artifact_data:
        # Keep native KiCad positional output as evidence; author the three
        # delivery tables through the documented artifact-tool workbook API.
        for name in ('jlc-bom.csv','jlc-cpl.csv','assembly-review.csv'):
            payloads.pop(name)
        payloads['assembly-tables.json']=json.dumps({
            'tables':[
                {'file':'jlc-bom.csv','sheet':'BOM','headers':BOM_COLUMNS,'rows':bom},
                {'file':'jlc-cpl.csv','sheet':'CPL','headers':CPL_COLUMNS,'rows':cpl},
                {'file':'assembly-review.csv','sheet':'Review','headers':REVIEW_COLUMNS,'rows':review},
            ],'expected_refs':refs},ensure_ascii=False,indent=2)+'\n'
    out.mkdir(parents=True, exist_ok=True)
    for name, text in payloads.items():
        # Only fixed generated filenames are written. No input or CAD path is a target.
        with (out/name).open('w', encoding='utf-8', newline='') as stream:
            stream.write(text)
    print(f'ASSEMBLY_COMPONENTS={len(refs)} BOM_GROUPS={len(bom)} TOP_ONLY=True')
    print('MANUAL_EXCLUSIONS=BT1,D1 HYBRID_J1_INCLUDED=True')
    print(f'UNITS=mm AUX_ORIGIN={fmt(origin[0])},{fmt(origin[1])} INPUT_HASHES_UNCHANGED=True')
    print('MANUFACTURE_READY=False JLC_PLACEMENT_PREVIEW_REQUIRED=True')


def self_test():
    """Pure in-memory tests; no CSV artifacts and no CAD/CLI access."""
    raw = 'Ref,Val,Package,PosX,PosY,Rot,Side\nU1,test,pkg,10,20,90,top\n'
    parsed = parse_positions(raw)
    fp = {'x': 74.5, 'y': 74.0, 'rotation': 90, 'node': ['footprint', 'x',
          ['pad', '1', 'smd', 'rect', ['at', 1, 0]]]}
    check_positions(['U1'], parsed, {'U1': fp}, (64.5, 94.0))
    pin, absolute, exported = pin1_positions(fp, (64.5, 94.0))
    require(pin == '1' and absolute == [[74.5, 73.0]] and exported == [[10.0, 21.0]], 'Pin 1 90-degree transform failed')
    require(rotation_equal(-90, 270) and not rotation_equal(90, 270), 'Rotation equivalence failed')
    failures = 0
    for invalid in (raw.replace('10,20', '254,508'), raw.replace('90,top', '90,bottom'),
                    raw.replace('10,20', '10mm,20'), raw + 'U1,test,pkg,10,20,90,top\n'):
        try:
            check_positions(['U1'], parse_positions(invalid), {'U1': fp}, (64.5, 94.0))
        except ValueError:
            failures += 1
    require(failures == 4, 'Unit/side/numeric/duplicate rejection tests failed')
    require(fmt(-0.0000001) == '0', 'Negative zero formatting failed')
    fake_refs = [f'R{i}' for i in range(1, EXPECTED_COMPONENTS+1)]
    fake_groups = [[ref] for ref in fake_refs[:EXPECTED_GROUPS-1]]+[fake_refs[EXPECTED_GROUPS-1:]]
    fake_bom = [dict(zip(BOM_COLUMNS, [f'PART{i}', ','.join(refs), '0402', f'C{i}']))
                for i, refs in enumerate(fake_groups, 1)]
    fake_cpl = [dict(zip(CPL_COLUMNS, [ref, '1.5', '2.5', 'Top', '90'])) for ref in fake_refs]
    btext, ctext = csv_text(BOM_COLUMNS, fake_bom), csv_text(CPL_COLUMNS, fake_cpl)
    validate_output_text(btext, ctext, fake_refs)
    try:
        validate_output_text(btext, ctext.replace('R40,', 'BT1,'), fake_refs)
    except ValueError:
        pass
    else:
        raise ValueError('Serialized BOM/CPL mismatch was not rejected')
    print('SELF_TEST_PASSED: coordinate, pin1 transform, rotation, units, top-only, duplicates, '
          'negative zero, 40-component/27-group CSV round-trip, BOM/CPL mismatch rejection')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pcb', type=Path)
    parser.add_argument('--sch', type=Path)
    parser.add_argument('--mapping', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--expected-origin', type=float, nargs=2, metavar=('X_MM', 'Y_MM'))
    parser.add_argument('--kicad-cli', default='kicad-cli')
    parser.add_argument('--overwrite', action='store_true', help='Replace only this script\'s six fixed generated outputs')
    parser.add_argument('--artifact-data', action='store_true', help='Export validated JSON tables for artifact-tool CSV authoring')
    parser.add_argument('--self-test', action='store_true', help='Pure in-memory tests; no CAD reads or CSV file output')
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    required = ('pcb', 'sch', 'mapping', 'out', 'expected_origin')
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error('Required for export: '+', '.join('--'+name.replace('_', '-') for name in missing))
    require(all(math.isfinite(v) for v in args.expected_origin), 'Expected origin must be finite')
    export(args)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f'EXPORT_FAILED: {exc}', file=sys.stderr)
        raise SystemExit(1)
