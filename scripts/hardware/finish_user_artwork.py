"""Post-route copper, legibility and mechanical invariants for user artwork."""
from pathlib import Path
import json,os
import pcbnew as p
from snapshot_user_libraries import apply_library_models_to_board

OUT=Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2\artwork-current')
PCB=OUT/'IR_ESP32H2.kicad_pcb';os.environ['KIPRJMOD']=str(OUT)
def v(x,y):return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
def xy(i):return [round(p.ToMM(i.GetPosition().x),6),round(p.ToMM(i.GetPosition().y),6)]
b=p.LoadBoard(str(PCB));fps={f.GetReference():f for f in b.GetFootprints()}
baseline=json.loads((OUT/'checks/locked-baseline.json').read_text())
# Specctra session stores 0.1 um resolution. Restore the exact original mechanical
# origins (SW3 had a 0.02 um roundoff), never accept movement of a locked anchor.
for r,old in baseline.items():
    f=fps[r]
    assert abs(xy(f)[0]-old['xy'][0])<.0001 and abs(xy(f)[1]-old['xy'][1])<.0001,r
    f.SetPosition(v(*old['xy']));f.SetOrientationDegrees(old['angle'])
def check_locks():
    for r,old in baseline.items():
        f=fps[r]
        assert dict(xy=xy(f),angle=f.GetOrientationDegrees(),layer=f.GetLayerName(),locked=f.IsLocked())==old,r
    assert [r for r,f in fps.items() if f.GetLayer()==p.B_Cu]==['BT1']
check_locks()
kept_objects=[]
tracks=list(b.GetTracks())
for t in tracks:
    if t.GetNetname().startswith('unconnected-'):
        b.Remove(t);kept_objects.append(t)
    elif isinstance(t,p.PCB_VIA):
        t.SetFrontTentingMode(p.TENTING_MODE_TENTED);t.SetBackTentingMode(p.TENTING_MODE_TENTED)
zones=list(b.Zones())
for z in zones:
    if not z.GetIsRuleArea():b.Remove(z);kept_objects.append(z)
outline=[(64.5,54),(149.5,54),(149.5,94),(64.5,94),(64.5,82),(69.5,82),(69.5,66),(64.5,66)]
for layer in (p.F_Cu,p.B_Cu):
    z=p.ZONE(b);z.SetLayer(layer);z.SetNet(b.FindNet('GND'));z.SetLocalClearance(p.FromMM(.2))
    z.SetPadConnection(p.ZONE_CONNECTION_THT_THERMAL)
    z.SetThermalReliefGap(p.FromMM(.25));z.SetThermalReliefSpokeWidth(p.FromMM(.35))
    z.SetMinThickness(p.FromMM(.2));z.Outline().NewOutline()
    for x,y in outline:z.Outline().Append(p.FromMM(x),p.FromMM(y))
    b.Add(z)
# Murata prohibits copper under the core except electrode connections, and
# through holes under the coil. The central gap derives from its land drawing;
# the whole-body via keepout includes the maximum package tolerance.
for name,points,block_copper in (
 ('L1 core - both layers',[(101.3,82.6),(103.1,82.6),(103.1,83.4),(101.3,83.4)],True),
 ('L1 body - no vias',[(101.3,81.9),(103.1,81.9),(103.1,84.1),(101.3,84.1)],False)):
    if not any(z.GetZoneName()==name for z in b.Zones()):
        z=p.ZONE(b);z.SetZoneName(name);layers=p.LSET();layers.AddLayer(p.F_Cu);layers.AddLayer(p.B_Cu)
        z.SetLayerSet(layers);z.SetIsRuleArea(True);z.SetDoNotAllowTracks(block_copper)
        z.SetDoNotAllowZoneFills(block_copper);z.SetDoNotAllowVias(True)
        z.SetDoNotAllowPads(False);z.SetDoNotAllowFootprints(False);z.Outline().NewOutline()
        for x,y in points:z.Outline().Append(p.FromMM(x),p.FromMM(y))
        b.Add(z)
for r in ('U2','U5'):
    for pad in fps[r].Pads():
        if pad.GetNetname()=='GND':pad.SetLocalZoneConnection(p.ZONE_CONNECTION_FULL)

references={
 'J1':(82,56.8),'U2':(67,87),'D1':(146,69.3),'SW3':(132.3,59.7),'BT1':(115,88),
 'U1':(95.7,63.0),'C1':(92.6,64.3),'C7':(100,67),
 'F1':(87,60.6),'U3':(72.3,64.7),'U4':(84.2,63.5),
 'R1':(80,64),'R5':(78,64),'R2':(84.1,57.8),'R6':(85,61),
 'R3':(91,69.6),'R4':(94.8,72.1),'R8':(84.2,70.5),'R9':(84.2,65.8),
 'SW1':(88,89.5),'SW2':(88,78.5),'R7':(77.2,83.8),'C4':(79.8,85.7),
 'C2':(71,82),'C3':(72.4,86.4),'R16':(77,91),
 'U5':(99,88.9),'L1':(104.5,83),'C10':(99,78.4),'C9':(102.4,76.5),'C8':(99,87.7),
 'R14':(93.1,82.5),'R15':(93.1,85),
 'Q1':(141,70.9),'R10':(136.2,70.2),'R11':(135.4,74.5),
 'R12':(142,89.3),'C5':(133.7,76.8),'C6':(136.6,82.1),
 'F2':(135.81,69.0),'Q2':(129.8,63.6),'R13':(126.3,58.3),
}
for r,(x,y) in references.items():
    text=fps[r].Reference();text.SetPosition(v(x,y));text.SetTextAngle(p.EDA_ANGLE(0,p.DEGREES_T))
    text.SetTextSize(v(.8,.8));text.SetTextThickness(p.FromMM(.12));text.SetVisible(True)
# Antenna body outline extends over a routed notch: fabrication geometry remains,
# only the two off-board silkscreen boundary lines move to the assembly layer.
for item in fps['U2'].GraphicalItems():
    if item.GetLayer()==p.F_SilkS and isinstance(item,p.PCB_SHAPE):
        if min(p.ToMM(item.GetStart().x),p.ToMM(item.GetEnd().x))<70.05:item.SetLayer(p.F_Fab)
    elif item.GetLayer()==p.F_SilkS and isinstance(item,p.PCB_TEXT):
        if p.ToMM(item.GetPosition().x)<69.5:item.SetLayer(p.F_Fab)

# Stitch the lower USB/ESD ground area to both planes. The connector's plated
# shell anchors already stitch the upper side of this short Full-Speed route.
# These vias are outside signal/solder pads and must pass native DRC after fill.
for x,y in ((71.7,64.8),(73.2,66.4),(81.5,65.7)):
    if not any(isinstance(t,p.PCB_VIA) and t.GetPosition()==v(x,y) for t in b.GetTracks()):
        via=p.PCB_VIA(b);via.SetPosition(v(x,y));via.SetWidth(p.FromMM(.6))
        via.SetDrill(p.FromMM(.3));via.SetViaType(p.VIATYPE_THROUGH)
        via.SetLayerPair(p.F_Cu,p.B_Cu);via.SetNet(b.FindNet('GND'))
        via.SetFrontTentingMode(p.TENTING_MODE_TENTED);via.SetBackTentingMode(p.TENTING_MODE_TENTED)
        b.Add(via)

labels={'IR H2':(117.8,90.8,1.4),'USB 5V':(87,55.6,.8),
        'BOOT':(87.9,71.3,.8),'RESET':(88,82.2,.8),'AA x2 / NO CHARGE':(115,86,.8)}
for label,(x,y,size) in labels.items():
    found=next((item for item in b.GetDrawings() if isinstance(item,p.PCB_TEXT) and item.GetText()==label),None)
    text=found or p.PCB_TEXT(b);text.SetText(label);text.SetPosition(v(x,y))
    text.SetLayer(p.F_SilkS);text.SetTextSize(v(size,size));text.SetTextThickness(p.FromMM(.14))
    if found is None:b.Add(text)

apply_library_models_to_board(b,OUT)
b.GetDesignSettings().SetAuxOrigin(v(64.5,94))
b.BuildConnectivity();p.ZONE_FILLER(b).Fill(b.Zones());check_locks()
assert p.SaveBoard(str(PCB),b)
project=json.loads((OUT/'IR_ESP32H2.kicad_pro').read_text(encoding='utf8'))
# Routed-edge requirement: JLCPCB >=.2 mm; use .3 mm, including locked switch pads.
project['board']['design_settings']['rules']['min_copper_edge_clearance']=.3
# 0.15 mm connector escape traces are above JLCPCB's 1 oz two-layer minimum.
project['board']['design_settings']['rules']['min_track_width']=.15
(OUT/'IR_ESP32H2.kicad_pro').write_text(json.dumps(project,indent=2),encoding='utf8')
print('Locked placements unchanged:',len(baseline))
print('Rear-mounted electrical footprints: BT1 only')
print('Tracks and vias:',len(list(b.GetTracks())))
print('Ground planes refilled; native DRC still required')
