#!/usr/bin/env python3
"""Build a one-folder app with PyInstaller (Windows in CI; also works on Linux
for a smoke test). Bundles the small u2netp model (4.6 MB) so the app works
offline out of the box; bigger models download on first use.

    python scripts/build.py            # -> dist/Atlas_BG_Remover_<os>.zip
    python scripts/build.py --matting  # also bundle pymatting/numba (+~150 MB)
"""
import hashlib, os, platform, shutil, subprocess, sys, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from atlas_bg.models import MODELS, BUNDLED  # noqa: E402

NAME = "Atlas_BG_Remover"


def fetch_bundled() -> Path:
    spec = MODELS[BUNDLED]
    dst = ROOT / "build_cache" / spec.filename
    for cand in (ROOT / "models" / spec.filename, dst):
        if cand.exists() and hashlib.md5(cand.read_bytes()).hexdigest() == spec.md5:
            return cand
    dst.parent.mkdir(parents=True, exist_ok=True)
    print("downloading", spec.url)
    urllib.request.urlretrieve(spec.url, dst)
    if hashlib.md5(dst.read_bytes()).hexdigest() != spec.md5:
        raise SystemExit("checksum mismatch for bundled model")
    return dst


def main():
    matting = "--matting" in sys.argv
    model = fetch_bundled()
    win = sys.platform == "win32"
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
            "--name", NAME, "--distpath", str(ROOT / "build_out"), "--workpath", str(ROOT / "build"),
            "--specpath", str(ROOT / "build"),
            "--collect-all", "customtkinter", "--collect-all", "tkinterdnd2",
            "--collect-binaries", "onnxruntime", "--collect-data", "onnxruntime",
            # ImageTk loads this lazily, PyInstaller misses it -> crash on first preview
            "--hidden-import", "PIL._tkinter_finder", "--hidden-import", "PIL.ImageTk",
            "--exclude-module", "rembg", "--exclude-module", "pytest", "--exclude-module", "matplotlib",
            "--exclude-module", "PyInstaller"]
    if not matting:
        for m in ("pymatting", "numba", "llvmlite", "scipy"):
            args += ["--exclude-module", m]
    if win:
        # Windows' Tk shapes Arabic natively; keep LGPL python-bidi out of the exe.
        args += ["--exclude-module", "bidi", "--exclude-module", "arabic_reshaper"]
    icon = ROOT / "assets" / "icon.ico"
    if win and icon.exists():
        args += ["--icon", str(icon)]
    args.append(str(ROOT / "atlas_bg_gui.py"))
    print(" ".join(args))
    subprocess.check_call(args, cwd=ROOT)

    app = ROOT / "build_out" / NAME
    (app / "models").mkdir(exist_ok=True)
    shutil.copy2(model, app / "models" / model.name)
    for f in ("README.md", "MANUAL.md", "THIRD_PARTY_NOTICES.md", "LICENSE"):
        if (ROOT / f).exists():
            shutil.copy2(ROOT / f, app / f)
    dist = ROOT / "dist"; dist.mkdir(exist_ok=True)
    tag = {"win32": "Win", "darwin": "Mac"}.get(sys.platform, "Linux")
    z = dist / f"{NAME}_{tag}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in app.rglob("*"):
            zf.write(p, Path(NAME) / p.relative_to(app))
    size = sum(p.stat().st_size for p in app.rglob("*") if p.is_file())
    print(f"built {app} ({size / 1e6:.0f} MB unpacked) -> {z} ({z.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
