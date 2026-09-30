"""Snapshot embedded current-user KiCad symbols/footprints into portable libraries.

Only generated *.pretty/*.kicad_mod, *.kicad_sym, library tables, models, and
checks files in output are written. The input board/schematic/project are never
saved. Run after footprint geometry fixes, and rerun after further pad changes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import pcbnew as p

from kicad_sexpr import a, child, children, read, write
from portable_models import normalize_library_models


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _without_instance_ids(node):
    if not isinstance(node, list):
        return node
    return [_without_instance_ids(n) for n in node
            if not (isinstance(n,list) and n and n[0] in ('uuid','tstamp','net'))]


def _pad_signature(path):
    root=read(path)
    return sorted((json.dumps(_without_instance_ids(n),sort_keys=True)
                   for n in children(root,'pad')))


def snapshot_libraries(board_path, schematic_path, output_dir, *, omit_missing_models=True):
    board_path=Path(board_path).resolve(strict=True)
    schematic_path=Path(schematic_path).resolve(strict=True)
    output=Path(output_dir).resolve(strict=True)
    before={path:_digest(path) for path in (board_path,schematic_path)}
    board=p.LoadBoard(str(board_path))
    plugin=p.PCB_IO_MGR.FindPlugin(p.PCB_IO_MGR.KICAD_SEXP)
    footprint_libs=set()
    records=[]
    conflicts=[]
    signatures={}
    # Work on the board's in-memory instances only. FootprintSave converts them
    # to origin/orientation-zero library coordinates and strips pad net links.
    for fp in sorted(board.GetFootprints(),key=lambda f:f.GetReference()):
        ref=fp.GetReference()
        libid=str(fp.GetFPID().GetUniStringLibId())
        nickname,name=libid.split(':',1)
        if any(c in nickname+name for c in '/\\'):
            raise ValueError(f'Unsafe library name: {libid}')
        lib=output/(nickname+'.pretty')
        lib.mkdir(exist_ok=True)
        fp.SetLocked(False)
        fp.SetReference('REF**')
        fp.SetValue(name)
        # KiCad 10.0.1 FootprintSave normalizes pads/graphics and rotates nested
        # rule areas, but leaves those zone polygons translated by the board
        # footprint position. Explicitly move this in-memory snapshot to the
        # origin first so its zones are also written in local coordinates.
        # Do not SaveBoard: the user's instance placement must remain unchanged.
        fp.SetPosition(p.VECTOR2I(0,0))
        with tempfile.TemporaryDirectory(prefix='kicad-fp-snapshot-') as tmp:
            stage=Path(tmp)/'snapshot.pretty'
            stage.mkdir()
            plugin.FootprintSave(str(stage),fp)
            saved=stage/(name+'.kicad_mod')
            signature=_pad_signature(saved)
            if libid in signatures and signatures[libid] != signature:
                conflicts.append({'reference':ref,'library_id':libid,
                                  'reason':'Instances sharing one library ID have different pad geometry/numbers'})
            elif libid not in signatures:
                signatures[libid]=signature
                (lib/saved.name).write_bytes(saved.read_bytes())
        footprint_libs.add(nickname)
        records.append({'reference':ref,'library_id':libid,
                        'library_file':(lib/(name+'.kicad_mod')).relative_to(output).as_posix()})
    if conflicts:
        raise ValueError(json.dumps(conflicts,ensure_ascii=False))
    write(output/'fp-lib-table',a('fp_lib_table',a('version',7),*[
        a('lib',a('name',name),a('type','KiCad'),
          a('uri','${KIPRJMOD}/'+name+'.pretty'),a('options',''),
          a('descr','Project snapshot of current user board footprint geometry'))
        for name in sorted(footprint_libs)]))

    symbols=defaultdict(list)
    for sym in children(child(read(schematic_path),'lib_symbols'),'symbol'):
        sym=copy.deepcopy(sym)
        nickname,name=str(sym[1]).split(':',1)
        if any(c in nickname+name for c in '/\\'):
            raise ValueError(f'Unsafe symbol library name: {nickname}:{name}')
        sym[1]=name
        symbols[nickname].append(sym)
    for nickname,items in symbols.items():
        write(output/(nickname+'.kicad_sym'),a('kicad_symbol_lib',a('version',20241209),
                                             a('generator','kicad_symbol_editor'),*items))
    write(output/'sym-lib-table',a('sym_lib_table',a('version',7),*[
        a('lib',a('name',name),a('type','KiCad'),
          a('uri','${KIPRJMOD}/'+name+'.kicad_sym'),a('options',''),
          a('descr','Project snapshot of embedded user schematic symbols'))
        for name in sorted(symbols)]))
    model_report=normalize_library_models(output,omit_missing=omit_missing_models)
    assert all(_digest(path)==digest for path,digest in before.items()), 'Source input changed during snapshot'
    result={'input_sha256':{path.name:digest for path,digest in before.items()},
            'footprint_libraries':len(footprint_libs),'unique_footprints':len(signatures),
            'footprint_instances':len(records),'footprints':records,
            'symbol_libraries':len(symbols),'symbols':sum(map(len,symbols.values())),
            'models':{'unique_models':model_report['unique_models'],
                      'missing':model_report['missing'],
                      'omitted_missing':model_report['omitted_missing']},
            'input_files_modified':False}
    (output/'checks').mkdir(exist_ok=True)
    (output/'checks/library-snapshot.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result


def apply_library_models_to_board(board, output_dir):
    """Optional in-memory operation for the caller before its own SaveBoard.

    Copy model definitions only from the portable footprint library. Preserve
    footprint coordinates, orientation, pads, schematic paths and all routing.
    """
    output=Path(output_dir).resolve(strict=True)
    count=0
    for fp in board.GetFootprints():
        nickname,name=str(fp.GetFPID().GetUniStringLibId()).split(':',1)
        local=p.FootprintLoad(str(output/(nickname+'.pretty')),name)
        if local is None:
            raise FileNotFoundError(f'Local footprint not found: {nickname}:{name}')
        models=fp.Models()
        models.clear()
        for model in local.Models():
            models.push_back(model)
            count+=1
    return count


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board',type=Path)
    parser.add_argument('schematic',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(snapshot_libraries(args.board,args.schematic,args.output),ensure_ascii=False,indent=2))
