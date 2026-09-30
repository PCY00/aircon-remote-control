"""Read-only checks of original preservation and the actual generated CAD/CAM."""
from pathlib import Path
import csv,hashlib,json,sys
import pcbnew as p
from export_user_jlc import (parse_schematic,parse_pcb,parse_mapping,check_sources,
                           parse_positions,check_positions,build_rows,validate_output_text,self_test)
from kicad_sexpr import read,children,child,walk
OUT=Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2\artwork-current')
ORIGINAL=OUT.parent
BACKUP=ORIGINAL.parent/'IR_ESP32H2-snapshots/user-design-20260920-022829'
MAPPING=OUT/'manufacturing/assembly/part-selection.json'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
pcb=OUT/'IR_ESP32H2.kicad_pcb';sch=OUT/'IR_ESP32H2.kicad_sch'
for name in ('IR_ESP32H2.kicad_pcb','IR_ESP32H2.kicad_sch','IR_ESP32H2.kicad_pro'):
    assert sha(ORIGINAL/name)==sha(BACKUP/name),f'Original changed: {name}'
assert not (ORIGINAL/'codex-revA').exists()
assert (BACKUP/'retired-codex-revA').is_dir()
print('ORIGINAL_CAD_UNCHANGED=True OLD_REVA_REMOVED_FROM_ACTIVE=True BACKUP_RECOVERABLE=True')
b=p.LoadBoard(str(pcb));fps={f.GetReference():f for f in b.GetFootprints()}
baseline=json.loads((OUT/'checks/locked-baseline.json').read_text())
for r,old in baseline.items():
    f=fps[r]
    actual={'xy':[round(p.ToMM(f.GetPosition().x),6),round(p.ToMM(f.GetPosition().y),6)],
            'angle':f.GetOrientationDegrees(),'layer':f.GetLayerName(),'locked':f.IsLocked()}
    assert actual==old,(r,actual,old)
assert len(fps)==42
assert [r for r,f in fps.items() if f.GetLayer()==p.B_Cu]==['BT1']
print('LOCKED_COMPONENTS_PRESERVED=5 FRONT=41 REAR=1 REAR_ONLY=BT1')
for r in ('SW1','SW2'):
    f=fps[r];pads=list(f.Pads())
    assert sorted(q.GetNumber() for q in pads)==['1','1','2','2']
    assert len({q.GetNetname() for q in pads if q.GetNumber()=='1'})==1
    assert {q.GetNetname() for q in pads if q.GetNumber()=='2'}=={'GND'}
print('BUTTON_CONTACT_MAPPING=PASS')
vias=[t for t in b.GetTracks() if isinstance(t,p.PCB_VIA)]
assert all(t.GetFrontTentingMode()==p.TENTING_MODE_TENTED and t.GetBackTentingMode()==p.TENTING_MODE_TENTED for t in vias)
assert b.GetCopperLayerCount()==2
drc=json.loads((OUT/'checks/final-drc.json').read_text(encoding='utf8'))
assert not drc['violations'] and not drc['unconnected_items'] and not drc['schematic_parity']
erc=json.loads((OUT/'checks/final-erc.json').read_text(encoding='utf8'))
assert all(not sheet['violations'] for sheet in erc['sheets'])
print('ERC=0 DRC=0 UNCONNECTED=0 SCHEMATIC_PARITY=0')
doc=read(pcb)
for model in walk(doc,'model'):
    assert model[1].startswith('${KIPRJMOD}/models/'),model[1]
    assert (OUT/model[1].removeprefix('${KIPRJMOD}/')).is_file()
for f in fps.values():
    lib,name=str(f.GetFPID().GetUniStringLibId()).split(':',1)
    assert (OUT/(lib+'.pretty')/(name+'.kicad_mod')).is_file()
cam=json.loads((OUT/'checks/cam-export.json').read_text())
assert cam['source_sha256']=={(OUT/n).name:sha(OUT/n) for n in cam['source_sha256']}
assert all(sha(OUT/'manufacturing/gerber'/n)==h for n,h in cam['manufacturing_files'].items())
print('CAM_SOURCE_HASHES=MATCH LIBRARIES_AND_3D_PATHS=PORTABLE')
cam_readback=json.loads((OUT/'checks/cam-independent.json').read_text())
assert cam_readback['source_sha256']==sha(pcb)
assert cam_readback['source_and_cam_unchanged']
assert cam_readback['outline']['size_mm']==[85.,40.]
assert not cam_readback['outline']['missing'] and not cam_readback['outline']['extra']
for name,count in [('PTH',46),('NPTH',6)]:
    drill=cam_readback['drills'][name]
    assert drill['actual']==drill['expected']==count
    assert not drill['missing'] and not drill['extra']
for layer in cam_readback['layers'].values():assert not layer['missing_pad_flash_centers']
print('INDEPENDENT_CAM_READBACK=PASS OUTLINE_MM=85x40 PTH=46 NPTH=6')
s=parse_schematic(sch);board,origin=parse_pcb(pcb,[64.5,94]);m=parse_mapping(MAPPING)
refs=check_sources(s,board,m);folder=OUT/'manufacturing/assembly'
pos=parse_positions((folder/'kicad-position-raw.csv').read_text(encoding='utf8'))
check_positions(refs,pos,board,origin)
expected=build_rows(refs,s,board,m,pos,origin)
for name,rows in zip(('jlc-bom.csv','jlc-cpl.csv','assembly-review.csv'),expected):
    with (folder/name).open(encoding='utf8',newline='') as stream:actual=list(csv.DictReader(stream))
    assert rows==actual,name
validate_output_text((folder/'jlc-bom.csv').read_text(),(folder/'jlc-cpl.csv').read_text(),refs)
self_test()
print('BOM_GROUPS=27 CPL_COMPONENTS=40 TOP_ONLY=True MANUAL=BT1,D1')
print('BOM_CPL_CAD_EXACT_MATCH=True AUX_ORIGIN_MM=64.5,94')
result={'passed':True,'original_unchanged':True,'locked_preserved':baseline,'footprints':42,
        'front':41,'rear':['BT1'],'track_via_items':len(list(b.GetTracks())),'vias':len(vias),
        'erc':0,'drc':0,'unconnected':0,'schematic_parity':0,'bom_groups':27,'cpl_top_components':40,
        'source_sha256':cam['source_sha256'],'physical_validation':False,'JLC_preview_approval':False}
(OUT/'checks/release-validation.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print('RELEASE_DATA_VALIDATION=PASS PHYSICAL_TEST_AND_JLC_ORDER_APPROVAL=NOT_PERFORMED')
