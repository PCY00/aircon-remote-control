"""Vendor referenced KiCad 3D models into a generated project, without touching source libraries.

Call ``normalize_library_models(output_dir)`` after copying .pretty libraries and
before loading footprints into a board. Only quoted model filenames are changed;
model offsets, rotations, scales, footprint geometry and UUIDs are byte-preserved.
This helper needs ordinary Python, not pcbnew.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

MODEL_REFERENCE = re.compile(r'(\(model\s+)("(?:\\.|[^"\\])*")')
VARIABLE = re.compile(r'\$\{([^}]+)\}')


def _expression_end(text, start):
    """End of one model S-expression, respecting quoted parentheses/escapes."""
    depth, quoted, escaped = 0, False, False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError('Unclosed model S-expression')


def _known_project_models():
    """Existing user CAD sources for corrected footprints, never electrical BOM substitutions."""
    cad = Path.home() / 'OneDrive/Desktop/설계-하드웨어/cad'
    return {
        'DLA0010A_TI': cad/'TPS63802DLAT/DLA0010A.stp',
        # R47 and 4R7 use the same DFE201612E package. The BOM remains R47 (0.47uH).
        'IND_DFE201612E_Murata': cad/'ul_DFE201612E-4R7M-P2/IND_DFE201612E_MUR.step',
    }


def _default_variable_roots() -> dict[str, Path]:
    """Resolve installed KiCad/core and PCM paths; callers may override any key."""
    user = Path.home()
    local = Path(os.environ.get('LOCALAPPDATA', user / 'AppData/Local'))
    installs = [local / 'Programs/KiCad/10.0', Path(r'C:\Program Files\KiCad\10.0')]
    installed = next((p for p in installs if (p / 'share/kicad/3dmodels').is_dir()), None)
    documents = [user / 'OneDrive/문서', user / 'OneDrive/Documents', user / 'Documents']
    third_party = next((d / 'KiCad/10.0/3rdparty' for d in documents
                        if (d / 'KiCad/10.0/3rdparty').is_dir()), None)
    roots = {}
    if installed:
        roots['KICAD10_3DMODEL_DIR'] = installed / 'share/kicad/3dmodels'
    # Some vendor PCM packages still embed an old major-version variable. Their
    # content is installed under the active 10.0 thirdparty directory.
    if third_party:
        for version in ('8', '9', '10'):
            roots[f'KICAD{version}_3RD_PARTY'] = third_party
    # Explicit environment paths take precedence over discovered defaults.
    for key, value in os.environ.items():
        if re.fullmatch(r'KICAD\d+_(3DMODEL_DIR|3RD_PARTY)', key) and value:
            roots[key] = Path(value)
    return roots


def normalize_library_models(output_dir, *, variable_roots=None, strict=True,
                             omit_missing=False, project_model_sources=None):
    """Copy all referenced 3D files into ``output_dir/models`` and localize paths.

    Only ``*.pretty/*.kicad_mod`` inside output_dir are modified. The function
    preflights all input files before any library writes, errors on unresolved
    references by default, is idempotent, and returns/writes a JSON audit report.
    Existing unrelated files and source model/library files are never deleted.
    ``strict=False`` leaves unresolved references unchanged and reports them.
    ``omit_missing=True`` deliberately removes unavailable model nodes instead,
    records them in ``omitted_missing``, and never substitutes guessed geometry.
    Known corrected DLA/inductor footprints receive the matching existing user
    package CAD model when no model is already present; geometry only, not BOM.
    """
    output = Path(output_dir).resolve(strict=True)
    if not output.is_dir():
        raise NotADirectoryError(output)
    roots = _default_variable_roots()
    roots.update({key: Path(value) for key, value in (variable_roots or {}).items()})
    roots['KIPRJMOD'] = output
    model_dir = output / 'models'
    plans, records, missing, no_models, supplemental = [], [], [], [], []
    source_map = _known_project_models()
    source_map.update({key:Path(value) for key,value in (project_model_sources or {}).items()})
    copies: dict[Path, Path] = {}
    for footprint in sorted(output.glob('*.pretty/*.kicad_mod')):
        # Do not follow a library symlink/junction out into a source library.
        if not footprint.resolve().is_relative_to(output):
            raise ValueError(f'Footprint resolves outside output directory: {footprint}')
        original = footprint.read_bytes()
        text = original.decode('utf-8-sig')
        if not MODEL_REFERENCE.search(text) and footprint.stem in source_map:
            source = source_map[footprint.stem]
            model_node = ('\n  (model ' + json.dumps(source.as_posix(), ensure_ascii=False)
                          + ' (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))\n')
            closing = text.rfind(')')
            if closing < 0:
                raise ValueError(f'No footprint closing parenthesis: {footprint}')
            text = text[:closing] + model_node + text[closing:]
            supplemental.append({'footprint': footprint.relative_to(output).as_posix(),
                                 'source_filename': source.name})
        replacements = []
        matches = list(MODEL_REFERENCE.finditer(text))
        if not matches:
            no_models.append(footprint.relative_to(output).as_posix())
        for match in matches:
            reference = json.loads(match.group(2))
            unresolved = []

            def expand(token):
                key = token.group(1)
                if key not in roots:
                    unresolved.append(key)
                    return token.group(0)
                return str(roots[key])

            expanded = VARIABLE.sub(expand, reference)
            source = Path(expanded)
            if not source.is_absolute():
                source = output / source
            if unresolved or not source.is_file():
                missing.append({'footprint': footprint.relative_to(output).as_posix(),
                                'reference': reference, 'unresolved_variables': unresolved})
                if omit_missing:
                    replacements.append((match.start(), _expression_end(text, match.start()), ''))
                continue
            source = source.resolve(strict=True)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            if source.is_relative_to(model_dir.resolve()):
                destination = source
            else:
                # Stable content-addressed suffix prevents same-filename models
                # from different manufacturers silently overwriting one another.
                destination = model_dir / f'{source.stem}-{digest[:12]}{source.suffix}'
            localized = '${KIPRJMOD}/' + destination.relative_to(output).as_posix()
            replacements.append((match.start(2), match.end(2), json.dumps(localized, ensure_ascii=False)))
            copies[destination] = source
            records.append({'footprint': footprint.relative_to(output).as_posix(),
                            'model': destination.relative_to(output).as_posix(),
                            'sha256': digest})
        rewritten = text
        for start, end, replacement in sorted(replacements, reverse=True):
            rewritten = rewritten[:start] + replacement + rewritten[end:]
        data = rewritten.encode('utf-8')
        if original.startswith(b'\xef\xbb\xbf'):
            data = b'\xef\xbb\xbf' + data
        if data != original:
            plans.append((footprint, data))
    if strict and missing and not omit_missing:
        raise FileNotFoundError('Unresolved 3D models; no footprint changes applied: '
                                + json.dumps(missing, ensure_ascii=False))
    model_dir.mkdir(exist_ok=True)
    for destination, source in copies.items():
        if destination != source:
            # Do not overwrite a generated model that was edited unexpectedly.
            if destination.exists() and destination.read_bytes() != source.read_bytes():
                raise FileExistsError(f'Different content already exists at {destination}')
            if not destination.exists():
                shutil.copyfile(source, destination)
    for footprint, data in plans:
        footprint.write_bytes(data)
    report = {
        'model_references': len(records), 'unique_models': len(copies),
        'modified_footprints': len(plans), 'missing': missing,
        'omitted_missing': missing if omit_missing else [],
        'supplemental_package_models': supplemental,
        'footprints_without_models': no_models, 'models': records,
    }
    checks = output / 'checks'
    checks.mkdir(exist_ok=True)
    (checks / 'model-normalization.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--allow-missing', action='store_true')
    parser.add_argument('--omit-missing', action='store_true')
    args = parser.parse_args()
    result = normalize_library_models(args.output_dir, strict=not args.allow_missing,
                                      omit_missing=args.omit_missing)
    print(json.dumps(result, ensure_ascii=False, indent=2))
