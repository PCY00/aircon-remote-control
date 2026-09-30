"""Keep the research mapping intact and publish final selection notes separately."""
from pathlib import Path
import json
OUT=Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2\artwork-current/manufacturing/assembly')
rows=json.loads(Path('tmp/user-bom-audit-20260920/part-mapping.json').read_text(encoding='utf8'))
notes={
 'F1':'BNstar exact MPN; 1.25x2.0mm pads at +/-1.4mm are an engineering adaptation to maximum terminal width, not a manufacturer-recommended land; request JLC DFM review.',
 'F2':'Yenji exact MPN; manufacturer-recommended 1.0x1.9mm pads at +/-1.5mm implemented in a dedicated footprint.',
 'J1':'HRO exact MPN matches footprint; hybrid SMT/plated shell connector remains included in top assembly. Native 3D model unavailable.',
 'L1':'Murata 0.47uH R47, NOT 4R7. Recommended 0.8x1.8mm pads at +/-0.8mm implemented; central core copper keepout on both layers, whole-body via keepout.',
 'R16':'0 ohm 0805 matches physical land; schematic and PCB value labels corrected from 0402 to 0805.',
 'SW1':'XKB exact MPN; physical common-contact numbering corrected to top pair1/bottom pair2 for a two-pin symbol, preserving pad positions.',
 'SW3':'G-Switch exact MPN; locked placement preserved; non-electrical anchors are not additional electrical connections. Check orientation in JLC preview.',
 'U2':'ESP32-H2-MINI-1-H4S 4MB selected as requested; JLC catalog marked Standard Only and X-ray Required; recheck at order.',
 'U3':'TI TPD2EUSB30DRTR non-A selected; both schematic/PCB datasheet fields corrected to non-A datasheet; verify DRT-3 pin1 orientation.',
 'U5':'TPS63802DLAT exact current-user T suffix (not retired revA DLAR); DLA0010A pad8 split paste retained and dimensions reviewed against TI drawing.',
}
for row in rows:
    key=row['refs'][0]
    if key in notes:row['selection']=notes[key]
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'part-selection.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
print('Published final part-selection notes, retaining original research evidence.')
