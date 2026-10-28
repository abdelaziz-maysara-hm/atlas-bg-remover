"""Model registry, cache location and first-use download (stdlib only)."""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

RELEASE = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"


@dataclass(frozen=True)
class ModelSpec:
    key: str            # id used in settings / CLI
    filename: str       # .onnx file name
    url: str
    md5: str
    size_mb: int
    input_size: int     # square model input
    mean: tuple
    std: tuple
    sigmoid: bool       # BiRefNet outputs logits
    license: str
    origin: str
    note: str = ""
    levels: tuple = (0.0, 1.0)  # alpha calibration: lo -> 0, hi -> 1
    ram_mb: int = 500           # measured peak RAM of one inference


MODELS: dict[str, ModelSpec] = {
    "u2netp": ModelSpec(
        "u2netp", "u2netp.onnx", RELEASE + "u2netp.onnx",
        "8e83ca70e441ab06c318d82300c84806", 5, 320,
        (0.485, 0.456, 0.406), (0.229, 0.224, 0.225), False,
        "Apache-2.0", "https://github.com/xuebinqin/U-2-Net",
        "Tiny and very fast, rough edges.", (0.08, 0.65), 250),
    "u2net": ModelSpec(
        "u2net", "u2net.onnx", RELEASE + "u2net.onnx",
        "60024c5c889badc19c04ad937298a77b", 168, 320,
        (0.485, 0.456, 0.406), (0.229, 0.224, 0.225), False,
        "Apache-2.0", "https://github.com/xuebinqin/U-2-Net",
        "Classic general model.", (0.08, 0.65), 700),
    "isnet-general-use": ModelSpec(
        "isnet-general-use", "isnet-general-use.onnx", RELEASE + "isnet-general-use.onnx",
        "fc16ebd8b0c10d971d3513d564d01e29", 171, 1024,
        (0.5, 0.5, 0.5), (1.0, 1.0, 1.0), False,
        "Apache-2.0 (code licence; weights not separately licensed)",
        "https://github.com/xuebinqin/DIS",
        "Trained on DIS5K, which has its own dataset terms of use.", (0.08, 0.65), 900),
    "birefnet-lite": ModelSpec(
        "birefnet-lite", "BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx",
        RELEASE + "BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx",
        "4fab47adc4ff364be1713e97b7e66334", 214, 1024,
        (0.485, 0.456, 0.406), (0.229, 0.224, 0.225), True,
        "MIT", "https://github.com/ZhengPeng7/BiRefNet",
        "Best quality, slow, needs ~7 GB free RAM.", (0.0, 1.0), 7000),
}

# What the GUI calls "fast" / "quality".
DEFAULT_MODEL = "isnet-general-use"
DEFAULT_QUALITY = "birefnet-lite"
BUNDLED = "u2netp"     # small enough (4.6 MB) to ship inside the exe


def available_ram_mb():
    """Free physical memory in MB, or None if unknown. No dependencies."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return int(m.ullAvailPhys // (1024 * 1024))
            return None
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        return None
    return None


def ram_warning(key: str):
    """Return (needed_mb, free_mb) when the model probably won't fit, else None."""
    need = MODELS[key].ram_mb
    free = available_ram_mb()
    if free is not None and free < need:
        return need, free
    return None


class ModelError(Exception):
    """Base error. ``code`` is a stable id the GUI translates."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ModelDownloadError(ModelError):
    pass


class DownloadCancelled(ModelError):
    def __init__(self):
        super().__init__("cancelled", "Download cancelled")


def app_dir() -> Path:
    """Folder of the running exe (PyInstaller) or of the source tree."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def cache_dir() -> Path:
    env = os.environ.get("ATLAS_BG_MODELS")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "AtlasBgRemover" / "models"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "atlas-bg-remover" / "models"


def search_dirs() -> list[Path]:
    """Places a model file may already be: user cache, then a portable
    ``models`` folder next to the exe (bundle / USB-stick plan)."""
    dirs = [cache_dir(), app_dir() / "models"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(Path(meipass) / "models")
    return dirs


def find_model(key: str) -> Optional[Path]:
    spec = MODELS[key]
    for d in search_dirs():
        p = d / spec.filename
        if p.is_file() and p.stat().st_size > 1024:
            return p
    return None


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


ProgressFn = Callable[[int, int], None]  # (bytes_done, bytes_total or 0)


def download_model(key: str, progress: Optional[ProgressFn] = None,
                   cancel: Optional[threading.Event] = None,
                   timeout: float = 30.0, url: Optional[str] = None) -> Path:
    """Download into the cache with an atomic rename and MD5 check."""
    spec = MODELS[key]
    dest_dir = cache_dir()
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ModelDownloadError("no_write", f"Cannot create model folder {dest_dir}: {e}") from e
    dest = dest_dir / spec.filename
    src = url or spec.url
    fd, tmp_name = tempfile.mkstemp(prefix=spec.filename + ".", suffix=".part", dir=dest_dir)
    tmp = Path(tmp_name)
    try:
        req = urllib.request.Request(src, headers={"User-Agent": "AtlasBgRemover/0.1"})
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ModelDownloadError(
                "offline",
                f"Could not download model '{key}' ({e}). Check the internet "
                f"connection, or copy {spec.filename} into {dest_dir} manually "
                f"from {spec.url}") from e
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        h = hashlib.md5()
        with os.fdopen(fd, "wb") as out, resp:
            fd = -1
            while True:
                if cancel is not None and cancel.is_set():
                    raise DownloadCancelled()
                try:
                    chunk = resp.read(1 << 18)
                except (OSError, urllib.error.URLError) as e:
                    raise ModelDownloadError("interrupted", f"Download interrupted: {e}") from e
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if total and done != total:
            raise ModelDownloadError("interrupted", f"Download incomplete ({done}/{total} bytes)")
        if h.hexdigest() != spec.md5:
            raise ModelDownloadError("checksum", f"Checksum mismatch for {spec.filename}; file discarded")
        os.replace(tmp, dest)
        return dest
    finally:
        if fd != -1:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def ensure_model(key: str, progress: Optional[ProgressFn] = None,
                 cancel: Optional[threading.Event] = None, allow_download: bool = True) -> Path:
    if key not in MODELS:
        raise ModelError("unknown", f"Unknown model '{key}'. Choices: {', '.join(MODELS)}")
    p = find_model(key)
    if p:
        return p
    if not allow_download:
        raise ModelDownloadError("missing", f"Model '{key}' is not installed and downloads are disabled")
    return download_model(key, progress, cancel)
