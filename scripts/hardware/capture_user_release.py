"""Preserve actual verification stdout and native CAM transcript for the blog."""
from pathlib import Path
import subprocess,shutil,sys
OUT=Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2\artwork-current')
DOCS=Path('docs/assets')
command=[sys.executable,'scripts/hardware/validate_user_release.py']
result=subprocess.run(command,capture_output=True,text=True,encoding='utf8',errors='replace')
assert result.returncode==0,result.stdout+result.stderr
text='$ KiCad-Python scripts/hardware/validate_user_release.py\n'+result.stdout+result.stderr+f'EXIT_CODE={result.returncode}\n'
(DOCS/'terminal/75-user-pcb-final-verification.txt').write_text(text,encoding='utf8')
shutil.copyfile(OUT/'checks/manufacturing-terminal.txt',DOCS/'terminal/76-user-pcb-cam-export.txt')
images=DOCS/'hardware/user-pcb-20260920';images.mkdir(parents=True,exist_ok=True)
for side,name in [('top','front'),('bottom','back')]:
    shutil.copyfile(OUT/f'checks/3d-{side}.png',images/f'{name}.png')
print('Saved actual validation TXT, native CAM transcript and two native CAD renders.')
