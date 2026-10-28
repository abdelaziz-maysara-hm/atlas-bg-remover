"""Batch processing with progress callbacks and cancellation (no GUI)."""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from .engine import SUPPORTED_EXT, ImageLoadError, Options, Remover, process, save
from .models import ModelError

SUFFIX = "_nobg"


def collect_files(items: Iterable, recursive: bool = True, skip_dir: Optional[Path] = None) -> list[Path]:
    """Expand files and folders into a de-duplicated, sorted list of images.
    Files the user picked explicitly are kept even with an odd extension (so
    they get a clear error later); folder scans only take image extensions."""
    out, seen = [], set()
    skip = skip_dir.resolve() if skip_dir else None
    for it in items:
        p = Path(it)
        if p.is_dir():
            it2 = p.rglob("*") if recursive else p.glob("*")
            found = []
            for f in it2:
                try:
                    if not f.is_file() or f.suffix.lower() not in SUPPORTED_EXT:
                        continue
                    if skip and skip in f.resolve().parents:
                        continue
                    if f.stem.endswith(SUFFIX):
                        continue
                except OSError:
                    continue
                found.append(f)
            cands = sorted(found, key=lambda x: str(x).lower())
        else:
            cands = [p]
        for f in cands:
            key = os.path.normcase(str(f.resolve()))
            if key not in seen:
                seen.add(key)
                out.append(f)
    return out


def output_path(src: Path, out_dir: Path, fmt: str, taken: set) -> Path:
    ext = {"png": ".png", "jpg": ".jpg", "webp": ".webp"}[fmt]
    base = out_dir / f"{src.stem}{SUFFIX}{ext}"
    cand, n = base, 1
    while cand.exists() or str(cand).lower() in taken:
        cand = out_dir / f"{src.stem}{SUFFIX} ({n}){ext}"
        n += 1
    taken.add(str(cand).lower())
    return cand


@dataclass
class ItemResult:
    src: Path
    ok: bool
    out: Optional[Path] = None
    error_code: str = ""
    error: str = ""
    warnings: list = field(default_factory=list)
    seconds: float = 0.0


ProgressCb = Callable[[int, int, ItemResult], None]


def run_batch(files: list, out_dir, opts: Options, remover: Optional[Remover] = None,
              progress: Optional[ProgressCb] = None, cancel: Optional[threading.Event] = None,
              model_progress=None) -> list[ItemResult]:
    """Process ``files`` into ``out_dir``. One bad file never stops the batch.
    Returns per-file results (files not reached due to cancel are omitted)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if remover is None:
        remover = Remover(opts.model, progress=model_progress, cancel=cancel)
    results: list[ItemResult] = []
    taken: set = set()
    total = len(files)
    for i, f in enumerate(files):
        if cancel is not None and cancel.is_set():
            break
        f = Path(f)
        t0 = time.perf_counter()
        try:
            res = process(f, remover, opts)
            dst = output_path(f, out_dir, opts.out_format, taken)
            save(res, dst, opts)
            r = ItemResult(f, True, dst, warnings=list(res.warnings))
        except ImageLoadError as e:
            r = ItemResult(f, False, error_code=e.code, error=str(e))
        except MemoryError:
            r = ItemResult(f, False, error_code="memory", error="Not enough memory for this image")
        except ModelError:
            raise
        except OSError as e:
            r = ItemResult(f, False, error_code="write", error=f"Could not save: {e}")
        except Exception as e:  # keep the batch alive
            r = ItemResult(f, False, error_code="internal", error=f"{type(e).__name__}: {e}")
        r.seconds = time.perf_counter() - t0
        results.append(r)
        if progress:
            progress(i + 1, total, r)
    return results
