"""Generate the reviewable, self-contained Rev A schematic. Never edits originals.

Run with Python 3; PCB generation is separate and uses KiCad's bundled Python.
"""
from __future__ import annotations
import copy
import json
import math
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from kicad_sexpr import Atom, a, child, children, read, walk, write
from portable_models import normalize_library_models

WORK = Path(__file__).resolve().parents[2]
SOURCE = Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2')
OUT = SOURCE / 'codex-revA'
NAME = 'IR_ESP32H2_RevA'
KICAD = Path(r'C:\Users\kksp1\AppData\Local\Programs\KiCad\10.0')
LIB = KICAD / 'share/kicad'
CUSTOM = SOURCE.parents[1] / 'lib/cypark.pretty'
VENDOR = Path(r'C:\Users\kksp1\OneDrive\문서\KiCad\10.0\3rdparty\footprints\com_github_espressif_kicad-libraries\Espressif.pretty')
AUDIT = WORK / 'tmp/schematic-audit-20260919'
OUT.mkdir(exist_ok=True)
(OUT / 'IRH2.pretty').mkdir(exist_ok=True)
(OUT / 'checks').mkdir(exist_ok=True)

def uid(key):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'ir-h2-rev-a/' + key))

def effect(size=1.0, justify=None, hidden=False):
    e = a('effects', a('font', a('size', size, size)))
    if justify:
        e.append(a('justify', *[Atom(x) for x in justify.split()]))
    if hidden:
        e.append(Atom('hide'))
    return e

def prop(key, value, x=0, y=0, hidden=False, justify=None):
    return a('property', key, value, a('at', x, y, 0), effect(1.0, justify, hidden))

original = read(SOURCE / 'IR_ESP32H2.kicad_sch')
symbols = {s[1]: copy.deepcopy(s) for s in children(child(original, 'lib_symbols'), 'symbol')}
for lib_name, sym_name in [('Switch', 'SW_Push'), ('Connector', 'TestPoint'), ('power', 'PWR_FLAG')]:
    lib = read(LIB / 'symbols' / (lib_name + '.kicad_sym'))
    selected = next(s for s in children(lib, 'symbol') if s[1] == sym_name)
    symbols[lib_name + ':' + sym_name] = copy.deepcopy(selected)

# Correct imported electrical types; retain the original pin numbers/geometry.
for pin in walk(symbols['cypark:TPS63802DLAT'], 'pin'):
    n = child(pin, 'number')[1]
    if n == '6':
        pin[1] = Atom('power_out')
    elif n in ('7', '9'):
        pin[1] = Atom('passive')
for pin in walk(symbols['cypark:MK-12C02-G020'], 'pin'):
    pin[1] = Atom('passive')

root_id = uid('root')
root = a('kicad_sch', a('version', 20260306), a('generator', 'eeschema'),
         a('generator_version', '10.0'), a('uuid', root_id), a('paper', 'A2'),
         a('title_block', a('title', 'ESP32-H2 Zigbee IR node / AA + USB'),
           a('date', '2026-09-19'), a('rev', 'A prototype'),
           a('comment', 1, 'AA alkaline only. No charger. EN tied to VSYS for prototype.')))
embedded = a('lib_symbols')
root.append(embedded)
parts = []
used = {}

def copy_fp(identifier):
    lib, name = identifier.split(':', 1)
    if lib == 'PCM_Espressif':
        path = VENDOR / (name + '.kicad_mod')
    elif lib == 'cypark':
        path = CUSTOM / (name + '.kicad_mod')
    elif lib == 'Audit':
        path = AUDIT / (name + '.kicad_mod')
    else:
        path = LIB / 'footprints' / (lib + '.pretty') / (name + '.kicad_mod')
    if not path.exists():
        raise FileNotFoundError(path)
    if lib == 'Fuse':
        name = 'Fuse_BNstar_1206_3.6x1.9'
        footprint = read(path)
        footprint[1] = name
        for pad in children(footprint, 'pad'):
            child(pad, 'size')[2] = 2.0
        for line in children(footprint, 'fp_line'):
            if child(line, 'layer')[1] == 'F.CrtYd':
                for pt in ('start','end'):
                    point = child(line, pt)
                    point[2] = 1.3 if float(point[2]) > 0 else -1.3
        target = OUT / 'IRH2.pretty' / (name + '.kicad_mod')
        write(target, footprint)
    else:
        target = OUT / 'IRH2.pretty' / (name + '.kicad_mod')
        shutil.copyfile(path, target)
    return 'IRH2:' + name

def local_symbol(identifier):
    if identifier in used:
        return used[identifier]
    s = copy.deepcopy(symbols[identifier])
    bare = identifier.split(':')[-1]
    s[1] = 'IRH2:' + bare
    used[identifier] = s
    embedded.append(s)
    return s

def label(net, x, y, angle=0):
    root.append(a('label', net, a('at', x, y, 0),
                  effect(0.95, 'right bottom' if angle == 180 else 'left bottom'),
                  a('uuid', uid(f'label-{net}-{x}-{y}'))))

def wire(x1, y1, x2, y2):
    root.append(a('wire', a('pts', a('xy', x1, y1), a('xy', x2, y2)),
                  a('stroke', a('width', 0), a('type', Atom('default'))),
                  a('uuid', uid(f'wire-{x1}-{y1}-{x2}-{y2}'))))

def add(ref, value, sym_id, fp, x, y, nets, mpn='', lcsc='', assembly='JLC', angle=0, ds=''):
    s = local_symbol(sym_id)
    actual_fp = copy_fp(fp) if fp else ''
    comp_id = uid(ref)
    inst = a('symbol', a('lib_id', s[1]), a('at', x, y, angle), a('unit', 1),
             a('in_bom', Atom('yes' if fp else 'no')), a('on_board', Atom('yes' if fp else 'no')),
             a('dnp', Atom('no')), a('uuid', comp_id))
    simple = sym_id in ('Device:R', 'Device:C', 'Device:L', 'Device:Polyfuse', 'Device:Battery')
    if simple:
        rx, ry = x + 2.54, y - 1.0
        vx, vy = x + 2.54, y + 1.0
    else:
        lib_props = {p[1]: p for p in children(s, 'property')}
        p = child(lib_props['Reference'], 'at')
        rx, ry = x + float(p[1]), y - float(p[2])
        p = child(lib_props['Value'], 'at')
        vx, vy = x + float(p[1]), y - float(p[2])
        # Imported CAD puts both fields too close to the body.
        if sym_id.startswith('cypark:'):
            rx, ry, vx, vy = x, y - 20.32, x, y - 17.78
    inst.extend([prop('Reference', ref, rx, ry, justify='left' if simple else None),
                 prop('Value', value, vx, vy, justify='left' if simple else None),
                 prop('Footprint', actual_fp, x, y, True), prop('Datasheet', ds, x, y, True),
                 prop('MPN', mpn or value, x, y, True), prop('LCSC', lcsc, x, y, True),
                 prop('Assembly', assembly, x, y, True)])
    pins = list(walk(s, 'pin'))
    connected_locations = {}
    positions = {}
    theta = math.radians(angle)
    for pin in pins:
        number = child(pin, 'number')[1]
        at = child(pin, 'at')
        lx, ly, pa = map(float, at[1:])
        px = round(x + lx * math.cos(theta) - ly * math.sin(theta), 6)
        py = round(y - lx * math.sin(theta) - ly * math.cos(theta), 6)
        positions[number] = [px, py]
        net = nets.get(number)
        location = (px, py)
        if location in connected_locations:
            assert connected_locations[location] == net, (ref, number, net)
            continue
        connected_locations[location] = net
        if net is None:
            root.append(a('no_connect', a('at', px, py), a('uuid', uid(f'nc-{ref}-{number}'))))
        else:
            # Extend outward from the pin. Local label direction points away from the body.
            outward = math.radians(pa + angle + 180)
            ex = round(px + 2.54 * math.cos(outward), 6)
            ey = round(py - 2.54 * math.sin(outward), 6)
            wire(px, py, ex, ey)
            label(net, ex, ey, 180 if ex < px - .1 else 0)
        inst.append(a('pin', number, a('uuid', uid(f'pin-{ref}-{number}'))))
    inst.append(a('instances', a('project', NAME, a('path', '/' + root_id,
                a('reference', ref), a('unit', 1)))))
    root.append(inst)
    parts.append(dict(ref=ref, value=value, symbol=s[1], footprint=actual_fp, uuid=comp_id,
                      nets=nets, mpn=mpn or value, lcsc=lcsc, assembly=assembly,
                      x=x, y=y, pin_positions=positions))

def text(value, x, y, size=1.3):
    root.append(a('text', value, a('at', x, y, 0), effect(size, 'left top'),
                  a('uuid', uid('text-' + value))))

def section(title, x1, y1, x2, y2):
    root.append(a('polyline', a('pts', a('xy', x1, y1), a('xy', x2, y1),
                               a('xy', x2, y2), a('xy', x1, y2), a('xy', x1, y1)),
                  a('stroke', a('width', .25), a('type', Atom('default'))),
                  a('fill', a('type', Atom('none'))), a('uuid', uid(title))))
    text(title, x1 + 4, y1 + 4, 1.7)

resdata = {
    '5.1k': ('0402WGF5101TCE', 'C25905', '0402_1005Metric'),
    '22': ('0402WGF220JTCE', 'C25092', '0402_1005Metric'),
    '10k': ('0402WGF1002TCE', 'C25744', '0402_1005Metric'),
    '100': ('0402WGF1000TCE', 'C25076', '0402_1005Metric'),
    '100k': ('0402WGF1003TCE', 'C25741', '0402_1005Metric'),
    '300k': ('0603WAF3003T5E', 'C23024', '0603_1608Metric'),
    '511k': ('0603WAF5113T5E', 'C23194', '0603_1608Metric'),
    '91k': ('0603WAF9102T5E', 'C23265', '0603_1608Metric'),
    '33': ('1210W2F330JT5E', 'C407192', '1210_3225Metric'),
    '0': ('0805W8F0000T5E', 'C17477', '0805_2012Metric'),
}
capdata = {
    '4.7u': ('CL21A475KAQNNNE', 'C1779', '0805_2012Metric', '25V'),
    '10u': ('CL21A106KAYNNNE', 'C15850', '0805_2012Metric', '25V'),
    '22u': ('CL31A226KAHNNNE', 'C12891', '1206_3216Metric', '25V'),
    '100n': ('CL05B104KO5NNNC', 'C1525', '0402_1005Metric', '16V'),
    '1u': ('CL05A105KA5NQNC', 'C52923', '0402_1005Metric', '25V'),
}
def R(ref, val, x, y, n1, n2):
    mpn, lcsc, size = resdata[val]
    add(ref, val + (' / 0.5W' if val == '33' else ''), 'Device:R', 'Resistor_SMD:R_' + size,
        x, y, {'1': n1, '2': n2}, mpn, lcsc)

def C(ref, val, x, y, net):
    mpn, lcsc, size, voltage = capdata[val]
    add(ref, val + ' / ' + voltage, 'Device:C', 'Capacitor_SMD:C_' + size,
        x, y, {'1': net, '2': 'GND'}, mpn, lcsc)

text('IRH2 / REV A  |  USB-C + 2xAA  |  3.3V  |  Zigbee IR transmitter', 12.7, 13, 2.0)
section('1. USB-C / USB2 data / ESD', 10.16, 20.32, 193.04, 180.34)
section('2. AA input / reverse-polarity protection', 10.16, 190.5, 193.04, 327.66)
section('3. USB-priority power mux', 203.2, 20.32, 383.54, 157.48)
section('4. Buck-boost / 3.308V nominal', 203.2, 167.64, 383.54, 327.66)
section('5. ESP32-H2 / programming / boot straps', 393.7, 20.32, 581.66, 228.6)
section('6. IR driver / test access', 393.7, 238.76, 581.66, 373.38)

usb = {p: 'GND' for p in ('A1','A12','B1','B12','SH')}
usb.update({p: 'VBUS_RAW' for p in ('A4','A9','B4','B9')})
usb.update(A5='CC1', B5='CC2', A6='USB_DP_CONN', B6='USB_DP_CONN', A7='USB_DM_CONN', B7='USB_DM_CONN')
add('J1', 'TYPE-C-31-M-12', 'Connector:USB_C_Receptacle_USB2.0_16P',
    'Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12', 38.1, 68.58, usb,
    'TYPE-C-31-M-12', 'C165948')
R('R1','5.1k',99.06,53.34,'CC1','GND')
R('R2','5.1k',137.16,53.34,'CC2','GND')
R('R3','22',99.06,86.36,'USB_DM_CONN','USB_DM')
R('R4','22',137.16,86.36,'USB_DP_CONN','USB_DP')
add('U4','TPD2EUSB30DRTR','Power_Protection:TPD2EUSB30','Package_TO_SOT_SMD:Texas_DRT-3',
    50.8,127,{'1':'USB_DP_CONN','2':'USB_DM_CONN','3':'GND'},'TPD2EUSB30DRTR','C97502',
    ds='https://www.ti.com/lit/ds/symlink/tpd2eusb30.pdf')
add('U5','TPD2EUSB30DRTR','Power_Protection:TPD2EUSB30','Package_TO_SOT_SMD:Texas_DRT-3',
    132.08,127,{'1':'CC1','2':'CC2','3':'GND'},'TPD2EUSB30DRTR','C97502')
add('F1','PPTC 0.5A hold','Device:Polyfuse','Fuse:Fuse_1206_3216Metric',
    35.56,160.02,{'1':'VBUS_RAW','2':'USB_5V'},'SMD1206-050C-16V','C2760267')
C('C1','4.7u',109.22,160.02,'USB_5V')
text('R3/R4 at module. U4/U5 at connector.\nSBU unused. USB never charges AA cells.', 210.82, 347.98)

# Wire-terminated external AA holder, not a dimensionally unverified holder footprint.
add('BT1','2xAA external holder','Device:Battery','Connector_Wire:SolderWire-0.5sqmm_1x02_P4.6mm_D0.9mm_OD2.1mm',
    35.56,223.52,{'1':'BAT_RAW','2':'GND'},'2xAA alkaline wire holder','',assembly='Manual')
add('F2','PPTC 1A hold','Device:Polyfuse','Fuse:Fuse_1206_3216Metric',
    86.36,223.52,{'1':'BAT_RAW','2':'BAT_FUSED'},'SMD1206-100C-16V','C2760271')
add('SW1','MK-12C02-G020','cypark:MK-12C02-G020','Audit:MK-12C02-G020_GSwitch',
    124.46,226.06,{'1':'BAT_FUSED','2':'BAT_SW'},'MK-12C02-G020','C963206')
add('Q2','DMP2035U-7','Transistor_FET:Q_PMOS_GSD','Package_TO_SOT_SMD:SOT-23',
    55.88,276.86,{'1':'BAT_GATE','2':'BAT_PROTECTED','3':'BAT_SW'},'DMP2035U-7','C110499')
R('R14','100k',93.98,276.86,'BAT_GATE','GND')
C('C2','4.7u',144.78,276.86,'BAT_PROTECTED')
text('Q2: D toward cell+, S toward mux.\nSW1 disconnects battery only; USB may keep board on.\nNo charging. Do not mix cell type or state of charge.', 20.32,302.26)

add('U2','TPS2116DRLR','Power_Management:TPS2116DRL','Package_TO_SOT_SMD:SOT-583-8',
    281.94,63.5,{'1':'GND','2':'VSYS','7':'VSYS','3':'USB_5V','4':'USB_PR1','5':'USB_5V','6':'BAT_PROTECTED'},
    'TPS2116DRLR','C3235557',ds='https://www.ti.com/lit/ds/symlink/tps2116.pdf')
R('R8','300k',236.22,111.76,'USB_5V','USB_PR1')
R('R9','100k',292.1,111.76,'USB_PR1','GND')
text('USB priority around 4V.\nMODE follows VIN1. ST unused.', 213.36,134.62)

add('U3','TPS63802DLAR','cypark:TPS63802DLAT','Audit:DLA0010A_TI',
    281.94,213.36,{'1':'VSYS','2':'GND','3':'GND','4':'FB','6':'3V3_REG','7':'SW_L2','8':'GND','9':'SW_L1','10':'VSYS'},
    'TPS63802DLAR','C2845237',ds='https://www.ti.com/lit/ds/symlink/tps63802.pdf')
add('L1','0.47uH','Device:L','Audit:IND_DFE201612E_Murata',
    350.52,198.12,{'1':'SW_L1','2':'SW_L2'},'DFE201612E-R47M=P2','C668312')
C('C3','22u',226.06,256.54,'VSYS')
C('C9','100n',271.78,256.54,'VSYS')
C('C4','22u',340.36,256.54,'3V3_REG')
R('R10','511k',226.06,292.1,'3V3_REG','FB')
R('R11','91k',276.86,292.1,'FB','GND')
R('R16','0',340.36,292.1,'3V3_REG','3V3')
text('EN = VSYS (prototype). MODE = GND for power save.\n22uF/25V X5R 1206 at VIN and VOUT: account for DC bias.\nR16: removable current-measurement link. UV cutoff deferred.',213.36,309.88,1.15)

h2 = {str(n): 'GND' for n in (1,2,11,14,*range(36,54))}
h2.update({'3':'3V3','8':'H2_EN','18':'IR_TX','22':'STRAP8','23':'BOOT9','26':'USB_DM','27':'USB_DP','30':'UART_RX','31':'UART_TX'})
add('U1','ESP32-H2-MINI-1-H4S','PCM_Espressif:ESP32-H2-MINI-1','PCM_Espressif:ESP32-H2-MINI-1',
    487.68,73.66,h2,'ESP32-H2-MINI-1-H4S','C47967030',
    ds='https://documentation.espressif.com/esp32-h2-mini-1_mini-1u_datasheet_en.html')
C('C5','10u',419.1,124.46,'3V3')
C('C7','100n',474.98,124.46,'3V3')
R('R5','10k',419.1,160.02,'3V3','H2_EN')
C('C10','1u',474.98,160.02,'H2_EN')
R('R6','10k',530.86,124.46,'3V3','BOOT9')
R('R7','10k',530.86,160.02,'3V3','STRAP8')
add('SW2','BOOT','Switch:SW_Push','Button_Switch_SMD:SW_SPST_TS-1088-xR020',
    429.26,198.12,{'1':'BOOT9','2':'GND'},'TS-1088-AR02016','C720477')
add('SW3','RESET','Switch:SW_Push','Button_Switch_SMD:SW_SPST_TS-1088-xR020',
    513.08,198.12,{'1':'H2_EN','2':'GND'},'TS-1088-AR02016','C720477')
text('BOOT: hold SW2, pulse RESET, release BOOT.\nVBAT is internally tied to 3V3 by module default; leave pad15 NC.\nIR output = GPIO4 / module pad18 (not SuperMini GPIO8 firmware).',403.86,213.36,1.05)

R('R15','33',419.1,271.78,'3V3','IR_A')
add('D1','TSAL6200 940nm','Device:LED','LED_THT:LED_D5.0mm',
    482.6,266.7,{'1':'IR_K','2':'IR_A'},'TSAL6200','',assembly='Manual',
    ds='https://www.vishay.com/docs/81010/tsal6200.pdf')
add('Q1','AO3400A','Transistor_FET:AO3400A','Package_TO_SOT_SMD:SOT-23',
    535.94,276.86,{'1':'IR_GATE','2':'GND','3':'IR_K'},'AO3400A','C20917')
R('R12','100',419.1,307.34,'IR_TX','IR_GATE')
R('R13','100k',474.98,307.34,'IR_GATE','GND')
C('C6','22u',535.94,307.34,'3V3')
C('C8','100n',535.94,342.9,'3V3')
text('Approx. 55-60mA LED peak at 3.3V; 33R is 0.5W.\nTSAL6200: pad1 cathode, pad2 anode. Manual solder.\nPoint LED away from module antenna. No always-on power LED.',403.86,363.22,1.05)

text('TEST PADS / SMD contact pads; do not connect external 5V to 3V3 or GPIO.', 20.32,342.9,1.35)
for i, net in enumerate(('3V3','GND','H2_EN','BOOT9','UART_TX','UART_RX','IR_TX','VSYS')):
    add('TP' + str(i+1),net,'Connector:TestPoint','TestPoint:TestPoint_Pad_D1.5mm',
        25.4 + (i % 4) * 48.26, 363.22 + (i // 4)*22.86, {'1':net},assembly='PCB only')

# Power flags identify actual external sources and the rail after the removable link.
for i, net in enumerate(('VBUS_RAW','USB_5V','BAT_RAW','BAT_PROTECTED','3V3','GND')):
    add('#FLG' + str(i+1).zfill(2), 'PWR_FLAG', 'power:PWR_FLAG', '',
        220.98 + (i%3)*50.8, 375.92 + (i//3)*17.78, {'1':net}, assembly='Schematic only')

root.append(a('embedded_fonts', Atom('no')))
write(OUT / (NAME + '.kicad_sch'), root)
lib_output = a('kicad_symbol_lib', a('version', 20241209), a('generator', 'kicad_symbol_editor'))
for sym in embedded[1:]:
    standalone = copy.deepcopy(sym)
    standalone[1] = standalone[1].split(':')[1]
    lib_output.append(standalone)
write(OUT / 'IRH2.kicad_sym', lib_output)
write(OUT/'sym-lib-table', a('sym_lib_table', a('version',7),
    a('lib',a('name','IRH2'),a('type','KiCad'),a('uri','${KIPRJMOD}/IRH2.kicad_sym'),a('options',''),a('descr','Project-local reviewed symbols'))))
write(OUT/'fp-lib-table', a('fp_lib_table', a('version',7),
    a('lib',a('name','IRH2'),a('type','KiCad'),a('uri','${KIPRJMOD}/IRH2.pretty'),a('options',''),a('descr','Project-local footprints'))))
(OUT / 'design-intent.json').write_text(json.dumps(dict(root_uuid=root_id,parts=parts),indent=2,ensure_ascii=False),encoding='utf-8')
# Start from real project settings, without copying personal PCB view/cache state.
project = json.loads((SOURCE / 'IR_ESP32H2.kicad_pro').read_text(encoding='utf-8-sig'))
project['meta']['filename'] = NAME + '.kicad_pro'
(OUT / (NAME + '.kicad_pro')).write_text(json.dumps(project,indent=2),encoding='utf-8')
normalize_library_models(OUT, omit_missing=True)
for command in [
    ['sch','export','netlist','--format','kicadxml','-o',OUT/'checks/netlist.xml',OUT/(NAME+'.kicad_sch')],
    ['sch','erc','--format','json','-o',OUT/'checks/erc.json',OUT/(NAME+'.kicad_sch')],
    ['sch','export','svg','-o',OUT/'checks',OUT/(NAME+'.kicad_sch')],
]:
    cp = subprocess.run([str(KICAD/'bin/kicad-cli.exe'),*map(str,command)],capture_output=True,text=True,encoding='utf-8',errors='replace')
    print(' '.join(map(str,command[:3])),cp.returncode,cp.stdout,cp.stderr)
    if cp.returncode:
        raise RuntimeError(command)
print('GENERATED',OUT, 'physical components:',len([p for p in parts if p['footprint']]))
