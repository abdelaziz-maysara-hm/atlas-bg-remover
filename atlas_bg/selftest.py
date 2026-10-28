"""Headless self-test, used by CI on the frozen Windows build:
    Atlas_BG_Remover.exe --selftest report.json
Generates a test image, runs the bundled model, checks the PNG and writes a
JSON report. Exit code 0 = pass."""
from __future__ import annotations

import json
import sys
import tempfile
import time
import traceback
from pathlib import Path


def run(argv) -> int:
    report = Path(argv[0]) if argv else Path(tempfile.gettempdir()) / "atlas_bg_selftest.json"
    info = {"ok": False}
    t0 = time.perf_counter()
    try:
        import numpy as np
        from PIL import Image, ImageDraw
        from . import __version__
        from .batch import run_batch
        from .engine import Options, Remover
        from .models import BUNDLED, find_model
        info.update(version=__version__, python=sys.version.split()[0], frozen=bool(getattr(sys, "frozen", False)))
        info["model_path"] = str(find_model(BUNDLED))
        tmp = Path(tempfile.mkdtemp(prefix="atlas_bg_selftest_"))
        im = Image.new("RGB", (800, 600), (236, 236, 230))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((240, 150, 560, 480), radius=40, fill=(40, 60, 120))
        src = tmp / "عربي test.jpg"
        im.save(src)
        r = Remover(BUNDLED, allow_download=False)
        res = run_batch([src, tmp / "missing.png"], tmp / "out", Options(model=BUNDLED), r)
        out = Image.open(res[0].out)
        a = np.asarray(out)[..., 3]
        info.update(out=str(res[0].out), mode=out.mode, size=list(out.size),
                    corner_alpha=int(a[5, 5]), centre_alpha=int(a[300, 400]),
                    missing_error=res[1].error_code)
        info["ok"] = (res[0].ok and out.mode == "RGBA" and out.size == (800, 600)
                      and a[5, 5] < 20 and a[300, 400] > 235 and res[1].error_code == "not_found")
    except Exception:
        info["error"] = traceback.format_exc()
    info["seconds"] = round(time.perf_counter() - t0, 2)
    report.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if info["ok"] else 1
