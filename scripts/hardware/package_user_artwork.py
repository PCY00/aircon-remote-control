"""Package only the verified user-derived CAD and order files, never old revA."""
from pathlib import Path
import hashlib,json,zipfile
from kicad_sexpr import read,children,walk
OUT=Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2\artwork-current')
validation=json.loads((OUT/'checks/release-validation.json').read_text())
assert validation['passed']
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for n,h in validation['source_sha256'].items():assert sha(OUT/n)==h
manufacturing=OUT/'manufacturing'
def make_zip(target,files,base,prefix=''):
    assert target.parent.resolve().is_relative_to(OUT.resolve())
    files=sorted(set(files))
    assert all(p.resolve().is_relative_to(OUT.resolve()) for p in files)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for source in files:z.write(source,prefix+source.relative_to(base).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert len(z.infolist())==len(files)
        for source in files:
            name=prefix+source.relative_to(base).as_posix()
            assert hashlib.sha256(z.read(name)).hexdigest()==sha(source),name
    print(target.name,f'FILES={len(files)} ZIP_READBACK=PASS')
    return target
gerberfiles=[p for p in (manufacturing/'gerber').iterdir() if p.is_file()]
assert len(gerberfiles)==12
gerber=make_zip(manufacturing/'JLCPCB-Gerber-IR_ESP32H2.zip',gerberfiles,manufacturing/'gerber')
orderfiles=[gerber,OUT/'README-START-HERE.md',*[
 manufacturing/'assembly'/name for name in ('jlc-bom.csv','jlc-cpl.csv','assembly-review.csv',
 'README-assembly.md','part-selection.json','assembly-export.json')]]
order=make_zip(manufacturing/'IR_ESP32H2-PCBA-review-package.zip',orderfiles,OUT)

# A clean portable editing project: include only libraries actually referenced,
# not stale intermediate footprints/router sessions or old design variants.
doc=read(OUT/'IR_ESP32H2.kicad_pcb')
editing=[OUT/name for name in ('IR_ESP32H2.kicad_pcb','IR_ESP32H2.kicad_sch',
 'IR_ESP32H2.kicad_pro','fp-lib-table','sym-lib-table','README-START-HERE.md')]
for fp in children(doc,'footprint'):
    lib,name=fp[1].split(':',1);editing.append(OUT/(lib+'.pretty')/(name+'.kicad_mod'))
for table_name in ('sym-lib-table',):
    for lib in children(read(OUT/table_name),'lib'):
        uri=next(x[1] for x in lib if isinstance(x,list) and x[0]=='uri')
        assert uri.startswith('${KIPRJMOD}/');editing.append(OUT/uri.removeprefix('${KIPRJMOD}/'))
for model in walk(doc,'model'):
    editing.append(OUT/model[1].removeprefix('${KIPRJMOD}/'))
editing.extend(gerberfiles)
editing.extend(orderfiles)
for name in ('final-drc.json','final-erc.json','release-validation.json','cam-export.json',
 'cam-independent.json','drill-report.txt','3d-top.png','3d-bottom.png'):
    path=OUT/'checks'/name
    if path.exists():editing.append(path)
project=make_zip(OUT/'IR_ESP32H2-editable-project.zip',editing,OUT,'IR_ESP32H2/')
manifest={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in (gerber,order,project)}
(manufacturing/'package-sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print('PACKAGES_VERIFIED=True ORIGINAL_FILES_NOT_TOUCHED=True')
