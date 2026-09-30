from pathlib import Path
from kicad_sexpr import read, child, children, walk

source = Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2\IR_ESP32H2.kicad_sch')
root = read(source)
for symbol in children(child(root, 'lib_symbols'), 'symbol'):
    print('\nSYMBOL', symbol[1])
    for pin in walk(symbol, 'pin'):
        print(child(pin, 'number')[1], child(pin, 'name')[1], child(pin, 'at')[1:], pin[1])
