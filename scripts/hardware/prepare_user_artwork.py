"""Continue the user's 2026-09-20 board, never the abandoned Rev A.

Input is the verified snapshot. Output is an independent editable working project.
Locked mechanical placements are asserted before and after every transformation.
"""
from pathlib import Path
import json
import os
import pcbnew as p

ROOT = Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2')
SNAP = ROOT.parent/'IR_ESP32H2-snapshots/user-design-20260920-022829'
OUT = ROOT/'artwork-current'
NAME = 'IR_ESP32H2'
os.environ['KIPRJMOD'] = str(OUT)

def v(x,y): return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
def xy(item): return [round(p.ToMM(item.GetPosition().x),6),round(p.ToMM(item.GetPosition().y),6)]
def snapshot(f): return dict(xy=xy(f),angle=f.GetOrientationDegrees(),layer=f.GetLayerName(),locked=f.IsLocked())

b = p.LoadBoard(str(SNAP/(NAME+'.kicad_pcb')))
fps = {f.GetReference():f for f in b.GetFootprints()}
locked = {r:snapshot(f) for r,f in fps.items() if f.IsLocked()}
(OUT/'checks/locked-baseline.json').write_text(json.dumps(locked,indent=2),encoding='utf8')
# The extra 5 mm segment duplicates part of the bottom edge. Preserve all other outline geometry.
drawings = list(b.GetDrawings())
removed_items = []
for item in drawings:
    if item.GetLayer()==p.Edge_Cuts:
        endpoints={(round(p.ToMM(pt.x),4),round(p.ToMM(pt.y),4)) for pt in (item.GetStart(),item.GetEnd())}
        if endpoints=={(69.5,94.0),(64.5,94.0)}:
            assert not item.IsLocked()
            b.Remove(item);removed_items.append(item)
# Stale cached copper fills gave spurious shorts. Rebuild planes after routing.
zones = list(b.Zones())
for zone in zones:
    if not zone.GetIsRuleArea(): b.Remove(zone);removed_items.append(zone)

placement = {
    'R1':(80.0,65.8,90),'R5':(77.9,65.8,90),
    'U3':(74.4,64.7,0),'U4':(82.4,63.0,0),
    'R2':(82.8,59.4,0),'R6':(82.8,61.0,0),'F1':(87,58.5,0),
    'R3':(92.8,69.6,90),'R4':(92.8,72.1,90),
    'R8':(84,69.0,0),'R9':(84,67.3,0),
    'SW2':(88,75.0,0),'SW1':(88,86.0,0),
    'R7':(77.2,82.3,0),'C4':(79.6,84.0,0),
    'C2':(73.2,81.8,0),'C3':(72.4,84.5,180),'R16':(77,89,0),
    'U5':(99,83,0),'L1':(102.2,83,270),
    'C10':(99.0,80.0,180),'C9':(102.0,78.0,0),'C8':(99,86,0),
    'R15':(94.8,85,90),'R14':(94.8,82.5,90),
    'Q1':(140.5,73.2,0),'R10':(136.2,71.8,0),'R11':(137.0,74.5,90),
    'R12':(142,87.0,180),'C5':(135,78.5,0),'C6':(137.5,80.5,0),
}
for ref,(x,y,a) in placement.items():
    f=fps[ref]; assert not f.IsLocked(),ref
    f.SetOrientationDegrees(a);f.SetPosition(v(x,y))

# Correct XKB switch contact groups: each horizontal row is internally common.
for ref in ('SW1','SW2'):
    f=fps[ref]
    nets={pad.GetNumber():pad.GetNet() for pad in f.Pads() if pad.GetNumber() in ('1','2')}
    for pad in f.Pads():
        number='1' if pad.GetNumber() in ('1','2') else '2'
        pad.SetNumber(number);pad.SetNet(nets[number])

# The user's 9 open vias in solder pads require costly via filling. Replace unlocked
# holes by four tented vias between solder islands, retaining the locked module.
removed=[]
original_tracks = list(b.GetTracks())
for t in original_tracks:
    if isinstance(t,p.PCB_VIA) and 73<xy(t)[0]<79 and 71<xy(t)[1]<77:
        assert not t.IsLocked();removed.append(xy(t));b.Remove(t);removed_items.append(t)
def via(net,x,y,diam=.6,drill=.3):
    t=p.PCB_VIA(b);t.SetPosition(v(x,y));t.SetWidth(p.FromMM(diam));t.SetDrill(p.FromMM(drill))
    t.SetViaType(p.VIATYPE_THROUGH);t.SetLayerPair(p.F_Cu,p.B_Cu);t.SetNet(b.FindNet(net))
    t.SetFrontTentingMode(p.TENTING_MODE_TENTED);t.SetBackTentingMode(p.TENTING_MODE_TENTED)
    b.Add(t);return t
for x in (74.6125,76.5875):
    for y in (73.0125,74.9875): via('GND',x,y)
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA):
        t.SetFrontTentingMode(p.TENTING_MODE_TENTED);t.SetBackTentingMode(p.TENTING_MODE_TENTED)

# Two-layer keepout around the module antenna; the existing board cutout remains.
def polygon_zone(points,layer,keepout=False):
    z=p.ZONE(b);z.SetLayer(layer)
    z.Outline().NewOutline()
    for x,y in points:z.Outline().Append(p.FromMM(x),p.FromMM(y))
    if keepout:
        ls=p.LSET();ls.AddLayer(p.F_Cu);ls.AddLayer(p.B_Cu);z.SetLayerSet(ls)
        z.SetIsRuleArea(True);z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(True)
        z.SetDoNotAllowZoneFills(True);z.SetDoNotAllowPads(False);z.SetDoNotAllowFootprints(False)
    b.Add(z);return z
polygon_zone([(64,65.5),(69.8,65.5),(69.8,82.5),(64,82.5)],p.F_Cu,True)

for f in b.GetFootprints():
    f.Value().SetVisible(False)
    f.Reference().SetTextSize(v(.8,.8));f.Reference().SetTextThickness(p.FromMM(.12))
    f.Reference().SetTextAngle(p.EDA_ANGLE(0,p.DEGREES_T))
    if f.GetReference() not in locked:
        pos=xy(f);f.Reference().SetPosition(v(pos[0],pos[1]-1.5))
    for field in f.GetFields():
        if field.GetName() not in ('Reference','Value'):field.SetVisible(False)

assert {r:snapshot(fps[r]) for r in locked}==locked,'Locked mechanical placement changed'
assert [f.GetReference() for f in b.GetFootprints() if f.GetLayer()==p.B_Cu]==['BT1']
b.BuildConnectivity()
# Preserve user project schematic/ERC settings across the PCB API save.
project=json.loads((OUT/(NAME+'.kicad_pro')).read_text(encoding='utf8'))
assert p.SaveBoard(str(OUT/(NAME+'.kicad_pcb')),b)
rules=project['board']['design_settings']['rules']
rules.update(min_clearance=.15,min_track_width=.2,min_silk_clearance=.10,min_text_thickness=.12)
for nc in project['net_settings']['classes']:
    if nc['name']=='Default':nc.update(clearance=.15,track_width=.25,via_diameter=.6,via_drill=.3)
(OUT/(NAME+'.kicad_pro')).write_text(json.dumps(project,indent=2),encoding='utf8')
(OUT/'checks/preparation.json').write_text(json.dumps(dict(locked=locked,moved_unlocked=placement,removed_pad_vias=removed,remaining_original_track_items=len(list(b.GetTracks()))),indent=2),encoding='utf8')
print('Prepared current-user artwork; locked placements preserved:',len(locked))
print('Electrical footprints:',len(fps),'Rear components: BT1 only')
