"""Release identity and the compatibility identity used by Rev23 journals."""
import json
import os
import re
import sys
from pathlib import Path

BUILD_ID = "AKIRA_16_5_4_STUDIO_REV19"
UI_REVISION = "STUDIO_REV19"
VERSION = "16.5.4"
BASE_COMMIT = "d6049d8b73beaa37e766ac221ecf38ca4a29f7e3"
LEGACY_REVISION = "Rev23"
RELEASES = ("0.1.0","0.2.0","0.3.0")
DATA_SCHEMA = 1610
REPAIR_ID = "Fiabilidad de voz, MT5 y actualización"
_BUILD_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _built_identity():
    try:
        return json.loads((_BUILD_ROOT / "release_build.json").read_text(encoding="utf-8"))
    except (OSError,ValueError):
        return {}


_BUILT = _built_identity()
RELEASE_VERSION = (_BUILT.get("version") if getattr(sys,"frozen",False)
                   else os.environ.get("AKIRA_RELEASE_VERSION")) or RELEASES[0]
if RELEASE_VERSION not in RELEASES:
    raise ValueError("Versión de entrega de AKIRA inválida.")
DISPLAY_VERSION = RELEASE_VERSION.rsplit(".",1)[0]


def release_identity():
    commit=_BUILT.get("commit","")
    if not re.fullmatch("[0-9a-f]{40}",commit):commit="Sin compilar"
    return {"version": RELEASE_VERSION, "display": DISPLAY_VERSION, "revision": REPAIR_ID,
            "commit": commit, "base_commit": BASE_COMMIT, "schema": DATA_SCHEMA}
