"""Build/place a PCB from the *exported* schematic netlist using KiCad 10.

Critical power and USB routing is explicitly constructed here; remaining control
signals may be routed with a separate, offline DSN/SES pass. Never overwrites user CAD.
"""
from pathlib import Path
import json
import os
import sys
import xml.etree.ElementTree as ET
import pcbnew as p

OUT = Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2\codex-revA')
NAME = 'IR_ESP32H2_RevA'
KICAD = Path(r'C:\Users\kksp1\AppData\Local\Programs\KiCad\10.0')
os.environ['KICAD10_3DMODEL_DIR'] = str(KICAD/'share/kicad/3dmodels')
os.environ['KIPRJMOD'] = str(OUT)

def v(x, y):
    return p.VECTOR2I(p.FromMM(x), p.FromMM(y))

def mm(pos):
    return (p.ToMM(pos.x), p.ToMM(pos.y))

board = p.BOARD()
board.SetFileName(str(OUT/(NAME+'.kicad_pcb')))
board.SetCopperLayerCount(2)
board.GetDesignSettings().SetBoardThickness(p.FromMM(1.6))
intent = json.loads((OUT/'design-intent.json').read_text(encoding='utf-8'))
project_path = OUT/(NAME+'.kicad_pro')
preserved_project = json.loads(project_path.read_text(encoding='utf-8'))
xml = ET.parse(OUT/'checks/netlist.xml')
net_by_pad = {}
nets = {}
for elem in xml.findall('./nets/net'):
    name = elem.get('name')
    # KiCad XML renders pin-name slashes literally; PCB netlist uses escaped atoms.
    if name.startswith('unconnected-'):
        name = name.replace('/', '{slash}')
    net = p.NETINFO_ITEM(board, name, int(elem.get('code')))
    board.Add(net)
    nets[name] = net
    for node in elem.findall('node'):
        net_by_pad[(node.get('ref'), node.get('pin'))] = net

placements = {
    'U1':(140,103.1,0), 'J1':(154.5,118,90),
    'R3':(148.5,109.3,180), 'R4':(148.5,107.9,180),
    'R1':(145.5,118.2,90), 'R2':(145.5,122.0,90),
    'U4':(147.8,116.8,90), 'U5':(147.8,120.2,90),
    'F1':(155,127,90), 'C1':(104.7,121.25,180),
    'U2':(108.5,121,0), 'C2':(111.9,121.25,0),
    'R8':(110.3,117.2,90), 'R9':(113,117.2,90),
    'U3':(119,124,0), 'L1':(122.2,124,270),
    'C3':(119,121,180), 'C9':(121.8,118.5,0),
    'C4':(119,127,180), 'R10':(114.5,126,90), 'R11':(114.5,123,90),
    'R16':(122,132,0),
    'BT1':(105,136,0), 'F2':(104.6,131,90),
    'SW1':(114,142,0), 'Q2':(109,130,180), 'R14':(112,133,90),
    'C5':(130,104.8,180), 'C7':(132.6,103.0,90),
    'R5':(130,109,90), 'C10':(130,112,0),
    'R6':(144,114,90), 'R7':(141.8,114,90),
    'SW2':(150,139.5,0), 'SW3':(140,139.5,0),
    'R15':(124,136.5,90), 'D1':(125.5,142,0),
    'Q1':(131,133.5,0), 'R12':(133.5,127.5,90), 'R13':(134,131,90),
    'C6':(126.5,128.5,90), 'C8':(129.5,130,90),
    'TP1':(135,119,0), 'TP2':(138,119,0),
    'TP3':(135,123,0), 'TP4':(142,123,0),
    'TP5':(149,103.5,0), 'TP6':(153,103.5,0),
    'TP7':(135,135.5,0), 'TP8':(105,117,0),
}
fps = {}
report = {}
for comp in xml.findall('./components/comp'):
    ref = comp.get('ref')
    fp_id = comp.findtext('footprint')
    if not fp_id:
        continue
    lib, name = fp_id.split(':',1)
    fp = p.FootprintLoad(str(OUT/'IRH2.pretty'), name)
    assert fp is not None, fp_id
    fp.SetReference(ref)
    fp.SetValue(comp.findtext('value'))
    fp.SetFPID(p.LIB_ID(lib,name))
    fp.SetExcludedFromBOM(False)
    fp.SetExcludedFromPosFiles(False)
    for field in comp.findall('./fields/field'):
        if field.get('name') not in ('Footprint','Reference','Value'):
            fp.SetField(field.get('name'), field.text or '')
            fp.GetField(field.get('name')).SetVisible(False)
    fp.SetPath(p.KIID_PATH('/'+intent['root_uuid']+'/'+comp.findtext('tstamps')))
    x,y,deg = placements[ref]
    fp.SetPosition(v(x,y))
    fp.SetOrientationDegrees(deg)
    fp.Reference().SetTextSize(v(.8,.8))
    fp.Reference().SetTextThickness(p.FromMM(.12))
    fp.Value().SetVisible(False)
    board.Add(fp)
    fps[ref] = fp
    for pad in fp.Pads():
        net = net_by_pad.get((ref,pad.GetNumber()))
        if net is not None:
            pad.SetNet(net)
    report[ref] = {
        'at':placements[ref],
        'pads': [{'n':pad.GetNumber(),'xy':mm(pad.GetPosition()),'net':pad.GetNetname()} for pad in fp.Pads()],
    }

def line(a,b,layer=p.Edge_Cuts,width=.05):
    item = p.PCB_SHAPE(board)
    item.SetShape(p.SHAPE_T_SEGMENT)
    item.SetLayer(layer)
    item.SetStart(v(*a))
    item.SetEnd(v(*b))
    item.SetWidth(p.FromMM(width))
    board.Add(item)
    return item

for start,end in [((100,100),(160,100)),((160,100),(160,145)),((160,145),(100,145)),((100,145),(100,100))]:
    line(start,end)

def label(text,x,y,size=.85,layer=p.F_SilkS):
    item=p.PCB_TEXT(board)
    item.SetText(text)
    item.SetPosition(v(x,y))
    item.SetTextSize(v(max(.8,size),max(.8,size)))
    item.SetTextThickness(p.FromMM(.13))
    item.SetLayer(layer)
    board.Add(item)

label('IRH2  REV A',111,107,1.1)
label('2xAA / USB - NO CHARGE',115,110,.8)
label('ANTENNA - KEEP CLEAR',140,97,.7,p.Dwgs_User)
label('BOOT',150,143.1,.75)
label('RESET',140,143.1,.75)
label('BAT+',104.9,138.5,.8)
label('GND',109.6,138.5,.8)
label('IR / 940nm',126,138.8,.7)

# Mechanical mounting holes are board-only; no electrical pin is invented.
for index,(x,y) in enumerate([(103,142),(157,142)],start=1):
    fp=p.FootprintLoad(str(KICAD/'share/kicad/footprints/MountingHole.pretty'),'MountingHole_2.7mm_M2.5')
    fp.SetReference('H'+str(index))
    fp.SetValue('M2.5 NPTH')
    fp.SetAttributes(p.FP_BOARD_ONLY | p.FP_EXCLUDE_FROM_POS_FILES | p.FP_EXCLUDE_FROM_BOM)
    fp.SetPosition(v(x,y))
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    board.Add(fp)

board.BuildConnectivity()
settings=board.GetDesignSettings()
settings.m_MinSilkTextHeight=p.FromMM(.8)
settings.m_MinSilkTextThickness=p.FromMM(.12)
assert p.SaveBoard(str(OUT/(NAME+'.kicad_pcb')),board)
# pcbnew's fresh BOARD writes PCB-only project settings. Preserve the schematic/ERC
# configuration and merge only the settings actually produced by this PCB instance.
generated_project=json.loads(project_path.read_text(encoding='utf-8'))
for key in ('board','net_settings'):
    if key in generated_project:
        preserved_project[key]=generated_project[key]
project_path.write_text(json.dumps(preserved_project,indent=2),encoding='utf-8')
(OUT/'checks/placement.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Placed',len(fps),'electrical footprints; board 60x45mm; antenna overhang with 0.2mm copper-free strip inside edge.')
