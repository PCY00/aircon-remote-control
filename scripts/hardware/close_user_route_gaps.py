"""Explicitly close the two remaining connections from native DRC, once."""
from pathlib import Path
import pcbnew as p
OUT=Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2\artwork-current')
b=p.LoadBoard(str(OUT/'IR_ESP32H2.kicad_pcb'))
def v(x,y):return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
def trace(net,points,layer=p.F_Cu):
    for a,c in zip(points,points[1:]):
        if any(t.GetNetname()==net and t.GetLayer()==layer and t.GetStart()==v(*a) and t.GetEnd()==v(*c) for t in b.GetTracks()):continue
        t=p.PCB_TRACK(b);t.SetStart(v(*a));t.SetEnd(v(*c));t.SetWidth(p.FromMM(.25));t.SetLayer(layer);t.SetNet(b.FindNet(net));b.Add(t)
trace('/+3V3',[(76.69,82.3),(75.5,82.3),(74.3,83.5),(73.35,83.5)])
if not any(isinstance(t,p.PCB_VIA) and t.GetPosition()==v(94.15,70.11) for t in b.GetTracks()):
    t=p.PCB_VIA(b);t.SetPosition(v(94.15,70.11));t.SetWidth(p.FromMM(.6));t.SetDrill(p.FromMM(.3));t.SetViaType(p.VIATYPE_THROUGH)
    t.SetLayerPair(p.F_Cu,p.B_Cu);t.SetNet(b.FindNet('/USB_5V'));b.Add(t)
trace('/USB_5V',[(92.8,70.11),(94.15,70.11)])
trace('/USB_5V',[(94.15,70.11),(93.56,69.52),(93.56,67.4437)],p.B_Cu)
b.BuildConnectivity();assert p.SaveBoard(str(OUT/'IR_ESP32H2.kicad_pcb'),b)
print('Two DRC-identified circuit gaps connected')
