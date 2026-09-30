"""Export final current-user PCB using a shared KiCad drill/place origin."""
from pathlib import Path
import hashlib,json,subprocess
OUT=Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2\artwork-current')
CLI=Path(r'C:\Users\kksp1\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe')
PCB=OUT/'IR_ESP32H2.kicad_pcb';SCH=OUT/'IR_ESP32H2.kicad_sch'
CAM=OUT/'manufacturing/gerber';CHECKS=OUT/'checks'
CAM.mkdir(parents=True,exist_ok=True)
transcript=[]
def run(*args):
    cmd=[str(CLI),*map(str,args)]
    show='kicad-cli '+' '.join(str(x).replace(str(OUT),'<PROJECT>') for x in args)
    print('$ '+show,flush=True)
    result=subprocess.run(cmd,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=180)
    output=(result.stdout+result.stderr).replace(str(OUT),'<PROJECT>')
    transcript.extend(['$ '+show,output.strip(),f'EXIT_CODE={result.returncode}',''])
    print(output.strip(),flush=True)
    assert result.returncode==0,show
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
inputs={p.name:sha(p) for p in (PCB,SCH,OUT/'IR_ESP32H2.kicad_pro')}
run('pcb','drc','--format','json','--schematic-parity','--exit-code-violations','-o',CHECKS/'final-drc.json',PCB)
run('sch','erc','--format','json','--exit-code-violations','-o',CHECKS/'final-erc.json',SCH)
run('pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,Edge.Cuts',
    '--use-drill-file-origin','--subtract-soldermask','--exclude-value','--precision','6','-o',str(CAM)+'/',PCB)
run('pcb','export','drill','--format','excellon','--drill-origin','plot','--excellon-units','mm',
    '--excellon-zeros-format','decimal','--excellon-oval-format','route','--excellon-separate-th',
    '--generate-report','--report-path',CHECKS/'drill-report.txt','-o',str(CAM)+'/',PCB)
run('pcb','export','svg','--layers','F.Cu,F.SilkS,Edge.Cuts','--mode-single',
    '--fit-page-to-board','--exclude-drawing-sheet','-o',CHECKS/'final-top-copper.svg',PCB)
run('pcb','export','svg','--layers','B.Cu,B.SilkS,Edge.Cuts','--mode-single',
    '--fit-page-to-board','--exclude-drawing-sheet','-o',CHECKS/'final-bottom-copper.svg',PCB)
run('sch','export','netlist','--format','kicadxml','-o',CHECKS/'netlist-final.xml',SCH)
run('sch','export','svg','--output',str(CHECKS/'schematic-svg')+'/',SCH)
assert inputs=={p.name:sha(p) for p in (PCB,SCH,OUT/'IR_ESP32H2.kicad_pro')},'CAD input changed during export'
report={'source_sha256':inputs,'cad_unchanged_during_export':True,'origin_kicad_mm':[64.5,94],
        'gerber_drill_units':'mm','layers':2,'manufacturing_files':{p.name:sha(p) for p in CAM.iterdir() if p.is_file()}}
(CHECKS/'cam-export.json').write_text(json.dumps(report,indent=2),encoding='utf8')
transcript.extend(['CAD_UNCHANGED_DURING_EXPORT=True',f'CAM_FILE_COUNT={len(report["manufacturing_files"])}'])
(CHECKS/'manufacturing-terminal.txt').write_text('\n'.join(transcript)+'\n',encoding='utf8')
print('CAD_UNCHANGED_DURING_EXPORT=True')
