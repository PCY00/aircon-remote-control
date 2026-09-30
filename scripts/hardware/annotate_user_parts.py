"""Add reviewed procurement fields to the copied user CAD; no net/geometry edits."""
from pathlib import Path
import copy, json
from kicad_sexpr import read,write,child,children,a,Atom

OUT=Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2\artwork-current')
MAPPING=Path('tmp/user-bom-audit-20260920/part-mapping.json')
parts={r:row for row in json.loads(MAPPING.read_text(encoding='utf8')) for r in row['refs']}

def setprop(node,key,value):
    existing=next((p for p in children(node,'property') if p[1]==key),None)
    if existing is not None:existing[2]=value;return
    template=next(p for p in children(node,'property') if p[1]=='Value')
    prop=copy.deepcopy(template);prop[1]=key;prop[2]=value
    # New purchasing fields must not clutter the drawing/board.
    effects=child(prop,'effects')
    if effects is not None and child(effects,'hide') is None:effects.append(a('hide',Atom('yes')))
    uid=child(prop,'uuid')
    if uid is not None:prop.remove(uid)
    node.append(prop)

for suffix,tag in (('kicad_sch','symbol'),('kicad_pcb','footprint')):
    path=OUT/f'IR_ESP32H2.{suffix}';doc=read(path);changed=[]
    for node in children(doc,tag):
        properties={p[1]:p[2] for p in children(node,'property')};ref=properties.get('Reference')
        if ref not in parts:continue
        part=parts[ref]
        setprop(node,'MPN',part['mpn']);setprop(node,'LCSC',part['lcsc'] or '')
        setprop(node,'Assembly','Hand solder' if ref in ('BT1','D1') else 'JLCPCB Top')
        if ref=='R16':setprop(node,'Value','0R (0805)')
        if ref in ('U3','U4'):setprop(node,'Datasheet','https://www.ti.com/lit/ds/symlink/tpd2eusb30.pdf')
        changed.append(ref)
    assert len(changed)==42
    write(path,doc)
    print(f'{suffix}: 42 purchasing records; R16 label corrected to actual 0805; U3/U4 non-A datasheet')
