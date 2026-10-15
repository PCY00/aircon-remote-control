from kicad_sexpr import read, child, children, walk
from hw_paths import kicad_root

source = kicad_root() / 'IR_ESP32H2.kicad_sch'
root = read(source)
for symbol in children(child(root, 'lib_symbols'), 'symbol'):
    print('\nSYMBOL', symbol[1])
    for pin in walk(symbol, 'pin'):
        print(child(pin, 'number')[1], child(pin, 'name')[1], child(pin, 'at')[1:], pin[1])
