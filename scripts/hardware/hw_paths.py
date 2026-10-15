"""Shared locations for the IR_ESP32H2 hardware scripts, taken from the environment.

The KiCad project, the KiCad installation and the autorouter live outside this
repository, so these scripts used to embed absolute paths of one PC. They now
call the functions below: each reads an environment variable first, then looks
in the usual place on this PC, and otherwise stops with a message naming the
variable to set.

  IR_H2_KICAD_ROOT         KiCad project folder holding IR_ESP32H2.kicad_pro
                           (default: ~/OneDrive/Desktop/설계-하드웨어/kicad/IR_ESP32H2)
  KICAD_INSTALL_DIR        KiCad 10 installation folder
                           (default: %LOCALAPPDATA%/Programs/KiCad/10.0, then
                           C:/Program Files/KiCad/10.0)
  KICAD_CLI                kicad-cli executable
                           (default: <KICAD_INSTALL_DIR>/bin/kicad-cli.exe)
  IR_H2_VENDOR_FOOTPRINTS  Espressif.pretty installed by the KiCad plugin manager
                           (default: <Documents>/KiCad/10.0/3rdparty/footprints/
                           com_github_espressif_kicad-libraries/Espressif.pretty)
  IR_H2_ROUTE_TOOLS        folder holding freerouting-2.4.1.jar and its JRE; only
                           used with --autoroute, so it does not have to exist
                           (default: <IR_H2_KICAD_ROOT>/../KeyRing/tmp/route_tools)
"""
from __future__ import annotations

import os
from pathlib import Path


class MissingLocation(SystemExit):
    """A folder or tool was not found; the message names the variable to set."""


def _from_environment(name: str) -> Path | None:
    value = os.environ.get(name, '').strip()
    return Path(value).expanduser() if value else None


def _locate(name, what, defaults, *, exists=Path.is_dir, required=True) -> Path:
    """Return the path named by the variable ``name`` or the first existing default.

    ``defaults`` is called only when the variable is unset, so setting one
    variable never requires the others. Without ``required`` the first default
    is returned even when nothing exists yet.
    """
    explicit = _from_environment(name)
    if explicit is not None:
        if exists(explicit):
            return explicit
        raise MissingLocation(f'{name}={explicit} is not {what}')
    candidates = [candidate for candidate in defaults() if candidate is not None]
    for candidate in candidates:
        if exists(candidate):
            return candidate
    if candidates and not required:
        return candidates[0]
    looked = ', '.join(str(candidate) for candidate in candidates) or 'no default location'
    raise MissingLocation(f'Could not find {what}; set {name} (looked in: {looked})')


def kicad_root() -> Path:
    """The IR_ESP32H2 KiCad project folder; scripts only write below it."""
    return _locate('IR_H2_KICAD_ROOT', 'the IR_ESP32H2 KiCad project folder',
                   lambda: [Path.home() / 'OneDrive/Desktop/설계-하드웨어/kicad/IR_ESP32H2'])


def kicad_install() -> Path:
    """The KiCad 10 installation, used for its bundled footprints and 3D models."""
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    return _locate('KICAD_INSTALL_DIR', 'the KiCad 10 installation folder',
                   lambda: [local / 'Programs/KiCad/10.0', Path(r'C:\Program Files\KiCad\10.0')])


def kicad_cli() -> Path:
    return _locate('KICAD_CLI', 'the kicad-cli executable',
                   lambda: [kicad_install() / 'bin/kicad-cli.exe'], exists=Path.is_file)


def vendor_footprints() -> Path:
    """Espressif.pretty from the plugin-manager package com_github_espressif_kicad-libraries."""
    def defaults():
        home = Path.home()
        library = 'KiCad/10.0/3rdparty/footprints/com_github_espressif_kicad-libraries/Espressif.pretty'
        return [folder / library for folder in
                (home / 'OneDrive/문서', home / 'OneDrive/Documents', home / 'Documents')]
    return _locate('IR_H2_VENDOR_FOOTPRINTS', 'the Espressif.pretty vendor footprint library', defaults)


def route_tools() -> Path:
    """Folder with freerouting-2.4.1.jar and its JRE; only --autoroute runs it."""
    return _locate('IR_H2_ROUTE_TOOLS', 'the freerouting tools folder',
                   lambda: [kicad_root().parent / 'KeyRing/tmp/route_tools'], required=False)
