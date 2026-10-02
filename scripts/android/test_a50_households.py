"""Run locally authored tests on A50 using temporary fixtures, outside production data."""
import base64
import json
import sys
from pathlib import Path
from a50_record import PhoneSession


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    names = ['test_central_households.py','test_central_server_foundation.py']
    files = {name:base64.b64encode((Path('tests')/name).read_bytes()).decode() for name in names}
    remote = '''
import base64,json,os,subprocess,tempfile
from pathlib import Path
files = FILES
root = Path.home()/'services/aircon-central'
python = root/'.venv/bin/python'
with tempfile.TemporaryDirectory(prefix='central-tests-') as folder:
    stage = Path(folder)
    (stage/'tests').mkdir()
    for name,content in files.items():
        (stage/'tests'/name).write_bytes(base64.b64decode(content))
    (stage/'services').mkdir()
    (stage/'services/central-server').symlink_to(root/'current',target_is_directory=True)
    libraries = stage/'test-libraries'
    subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check',
                    '--target',str(libraries),'pytest==8.4.2'],check=True)
    environment = dict(os.environ,PYTHONPATH=str(libraries)+os.pathsep+str(root/'current'))
    subprocess.run([str(python),'-m','pytest',str(stage/'tests'),'-q','--basetemp',str(stage/'fixtures')],
                   env=environment,check=True)
    print('A50_SIGNED_FIXTURES_AND_HOUSEHOLD_TESTS=PASS PRODUCTION_DATA_SEEDED=NO')
'''.replace('FILES',repr(files))
    PhoneSession('household-native-tests').run('python -',data=remote.encode(),
        label='python - < locally authored test_a50_households.py [temporary signed fixtures]',timeout=300)


if __name__ == '__main__': main()
