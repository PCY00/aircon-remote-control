"""Refine three UNLOCKED lands for the exact production part selections.

Manufacturer dimensions: Yenji SMD1206 p5, Murata DFE201612E land drawing.
BNstar has no recommended land; retain generic toe length, widen to 2 mm.
No component centres/orientations, tracks, or net assignments are changed.
"""
from pathlib import Path
from kicad_sexpr import read,write,child,children

OUT=Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2\artwork-current')
lands={
 'F1':('Fuse_BNstar_1206_050C',1.4,1.25,2.0),
 'F2':('Fuse_Yenji_SMD1206P100TF',1.5,1.0,1.9),
 'L1':('IND_DFE201612E_R47_Recommended',.8,.8,1.8),
}
pcb=OUT/'IR_ESP32H2.kicad_pcb';doc=read(pcb)
for fp in children(doc,'footprint'):
    ref=next(p[2] for p in children(fp,'property') if p[1]=='Reference')
    if ref not in lands:continue
    name,centre,width,height=lands[ref];fp[1]='cypark:'+name
    assert child(fp,'locked') is None
    for pad in children(fp,'pad'):
        at=child(pad,'at');at[1]= -centre if pad[1]=='1' else centre
        child(pad,'size')[1:]=[width,height]
    print(ref,fp[1],f'pad {width}x{height} mm centres +/-{centre} mm')
write(pcb,doc)
sch=OUT/'IR_ESP32H2.kicad_sch';doc=read(sch)
for sym in children(doc,'symbol'):
    props={p[1]:p for p in children(sym,'property')};ref=props['Reference'][2]
    if ref in lands:props['Footprint'][2]='cypark:'+lands[ref][0]
write(sch,doc)
