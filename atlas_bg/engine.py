"""Core engine: load any image robustly, predict a mask with an ONNX model,
refine it, and build the final cutout. No GUI imports."""
from __future__ import annotations

import io
import threading
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import numpy as np
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from .models import MODELS, ensure_model

# Refuse absurd images (decompression bombs) but allow big camera / scan files.
MAX_PIXELS = 120_000_000          # covers 108 MP phone photos (~12000 x 9000)
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
STRIP = 1024                      # rows per strip for full-resolution filters
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".jfif"}


class ImageLoadError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code   # not_found | not_image | corrupt | too_large


# --------------------------------------------------------------------- loading
_SRGB = None


def _srgb_profile():
    global _SRGB
    if _SRGB is None:
        _SRGB = ImageCms.createProfile("sRGB")
    return _SRGB


def _to_srgb(img: Image.Image) -> Image.Image:
    icc = img.info.get("icc_profile")
    if not icc:
        return img.convert("RGB")
    try:
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        return ImageCms.profileToProfile(img, src, _srgb_profile(), outputMode="RGB")
    except Exception:
        return img.convert("RGB")


def load_image(src: Union[str, Path, Image.Image]):
    opened = []
    try:
        return _load_image(src, opened)
    finally:
        for im in opened:   # release the file handle (matters on Windows)
            try:
                im.close()
            except Exception:
                pass


def _load_image(src, opened):
    """Return (rgb, alpha_or_None, info). ``rgb`` is an sRGB 8-bit RGB image
    in display orientation (EXIF applied); ``alpha`` is the input's own
    transparency (mode L) if it has any."""
    try:
        if isinstance(src, Image.Image):
            img = src
        else:
            p = Path(src)
            if not p.is_file():
                raise ImageLoadError("not_found", f"File not found: {p}")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            if not isinstance(src, Image.Image):
                img = Image.open(p)
                opened.append(img)
            w, h = img.size
            if w * h > MAX_PIXELS:
                raise ImageLoadError("too_large", f"Image is too large: {w}x{h} = {w * h / 1e6:.0f} MP "
                                     f"(limit {MAX_PIXELS // 1_000_000} MP). Resize it first.")
            if w < 1 or h < 1:
                raise ImageLoadError("corrupt", "Image has no pixels")
            try:
                img.seek(0)
            except Exception:
                pass
            img.load()
            dpi = img.info.get("dpi")
            try:   # TIFF/BMP sometimes report nonsense such as 0.99 or 1 dpi
                if dpi and not all(50 <= float(v) <= 2400 for v in dpi[:2]):
                    dpi = None
            except Exception:
                dpi = None
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass  # broken EXIF: keep pixels as stored
    except ImageLoadError:
        raise
    except Image.DecompressionBombError as e:
        raise ImageLoadError("too_large", f"Image is too large (limit {MAX_PIXELS // 1_000_000} MP)") from e
    except UnidentifiedImageError as e:
        raise ImageLoadError("not_image", "Not an image file or unsupported format") from e
    except (OSError, SyntaxError, ValueError) as e:
        raise ImageLoadError("corrupt", f"Damaged or truncated image: {e}") from e

    mode = img.mode
    alpha = None
    if mode in ("I;16", "I;16B", "I;16L", "I;16N", "I", "F"):
        a = np.asarray(img, dtype=np.float64)
        lo, hi = float(a.min()), float(a.max())
        a = (a - lo) / (hi - lo) * 255.0 if hi > lo else np.zeros_like(a)
        img = Image.fromarray(a.astype(np.uint8), "L")
        mode = "L"
    if mode == "1":
        img = img.convert("L")
    elif mode in ("P", "PA"):
        img = img.convert("RGBA")
    elif mode == "LA":
        img = img.convert("RGBA")
    elif mode == "RGBa":
        img = img.convert("RGBA")

    if img.mode == "RGBA":
        alpha = img.getchannel("A")
        if alpha.getextrema()[0] == 255:
            alpha = None
        rgb_src = img.convert("RGB")
        rgb_src.info = img.info
        rgb = _to_srgb(rgb_src) if img.info.get("icc_profile") else rgb_src
    elif img.mode == "CMYK":
        rgb = _to_srgb(img)
    else:
        rgb = _to_srgb(img)
    info = {"size": rgb.size, "dpi": dpi, "mode": mode}
    return rgb, alpha, info


# ------------------------------------------------------------------- filters
def _box_axis0(a: np.ndarray, r: int) -> np.ndarray:
    n = a.shape[0]
    pad = [(r + 1, r)] + [(0, 0)] * (a.ndim - 1)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=0, dtype=np.float32)
    return (c[2 * r + 1:2 * r + 1 + n] - c[:n]) * np.float32(1.0 / (2 * r + 1))


def box_mean(a: np.ndarray, r: int) -> np.ndarray:
    """Mean over a (2r+1)x(2r+1) window (edge-replicated borders). Works on
    HxW or HxWxC arrays; returns float32."""
    a = np.asarray(a, dtype=np.float32)
    if r <= 0:
        return a.copy()
    out = _box_axis0(a, r)
    out = _box_axis0(np.swapaxes(out, 0, 1), r)
    return np.ascontiguousarray(np.swapaxes(out, 0, 1))


def _strips(h: int, overlap: int, step: int = None):
    """Yield (src0, src1, keep0, keep1) row ranges covering 0..h."""
    step = step or STRIP
    y = 0
    while y < h:
        y1 = min(h, y + step)
        s0, s1 = max(0, y - overlap), min(h, y1 + overlap)
        yield s0, s1, y - s0, y1 - s0
        y = y1


def _resize_f(a: np.ndarray, size, box=None) -> np.ndarray:
    """Bilinear resize of a float32 HxW or HxWxC array (optionally of a
    sub-box of the source, PIL box semantics)."""
    if a.ndim == 2:
        return np.asarray(Image.fromarray(np.ascontiguousarray(a, dtype=np.float32), "F")
                          .resize(size, Image.BILINEAR, box=box), dtype=np.float32)
    return np.dstack([_resize_f(a[..., c], size, box) for c in range(a.shape[2])])


def _low_res(shape, target: int):
    h, w = shape[:2]
    k = max(1.0, min(h, w) / float(target))
    return max(1, round(w / k)), max(1, round(h / k))


def estimate_foreground(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Approximate fast foreground colour estimation (Forte & Pitie 2021,
    'blur fusion'). Removes the old background's colour from semi-transparent
    edge pixels so there is no halo on a new background.

    rgb uint8 HxWx3, alpha float 0..1 -> uint8 HxWx3. The wide first pass
    (window ~91 px) runs on a reduced copy; the fine pass (window 7) runs at
    full resolution in strips, only over the rows/cols that have edge pixels."""
    h, w = alpha.shape
    partial = (alpha > 0.002) & (alpha < 0.998)
    rows = np.where(partial.any(axis=1))[0]
    if rows.size == 0:
        return rgb
    cols = np.where(partial.any(axis=0))[0]
    out = rgb.copy()
    # pass 1 on a low-res copy (short side ~512)
    lw, lh = _low_res(alpha.shape, 512)
    k = w / lw
    img_l = np.asarray(Image.fromarray(rgb).resize((lw, lh), Image.BOX), dtype=np.float32) / 255.0
    A_l = _resize_f(alpha.astype(np.float32), (lw, lh))[..., None]
    r1 = max(1, int(round(45 / k)))
    ba = box_mean(A_l, r1)
    bF_l = box_mean(img_l * A_l, r1) / (ba + 1e-5)
    bB_l = box_mean(img_l * (1 - A_l), r1) / ((1 - ba) + 1e-5)
    r2 = 3
    ov = r2 + 1
    sx, sy = lw / w, lh / h
    T = 384
    y_lo, y_hi = int(rows[0]), int(rows[-1]) + 1
    x_lo, x_hi = int(cols[0]), int(cols[-1]) + 1
    for ty in range(y_lo, y_hi, T):
        for tx in range(x_lo, x_hi, T):
            cy1, cx1 = min(ty + T, y_hi), min(tx + T, x_hi)
            sel = partial[ty:cy1, tx:cx1]
            if not sel.any():
                continue          # only tiles that contain edge pixels
            s0, s1 = max(0, ty - ov), min(h, cy1 + ov)
            c0, c1 = max(0, tx - ov), min(w, cx1 + ov)
            box = (c0 * sx, s0 * sy, c1 * sx, s1 * sy)
            size = (c1 - c0, s1 - s0)
            bF = _resize_f(bF_l, size, box)
            bB = _resize_f(bB_l, size, box)
            img = rgb[s0:s1, c0:c1].astype(np.float32) / 255.0
            A = alpha[s0:s1, c0:c1, None].astype(np.float32)
            F = np.clip(bF + A * (img - A * bF - (1 - A) * bB), 0, 1)
            ba2 = box_mean(A, r2)
            bF2 = box_mean(F * A, r2) / (ba2 + 1e-5)
            bB2 = box_mean(bB * (1 - A), r2) / ((1 - ba2) + 1e-5)
            F = np.clip(bF2 + A * (img - A * bF2 - (1 - A) * bB2), 0, 1)
            k0, k1 = ty - s0, cy1 - s0
            j0, j1 = tx - c0, cx1 - c0
            res = (F[k0:k1, j0:j1] * 255 + 0.5).astype(np.uint8)
            dst = out[ty:cy1, tx:cx1]
            out[ty:cy1, tx:cx1] = np.where(sel[..., None], res, dst)
    return out


def guided_refine(rgb: np.ndarray, mask: np.ndarray, radius: int = 8, eps: float = 1e-3) -> np.ndarray:
    """Fast guided filter (He & Sun 2015): snaps the upscaled soft mask to real
    image edges. Coefficients are computed at <=1536 px and applied at full
    resolution in strips, only near the mask boundary."""
    h, w = mask.shape
    sw, sh = w, h
    scale = min(1.0, 1536.0 / max(h, w))
    if scale < 1.0:
        sw, sh = max(1, round(w * scale)), max(1, round(h * scale))
    g = np.asarray(Image.fromarray(rgb).convert("L").resize((sw, sh), Image.BILINEAR)
                   if scale < 1.0 else Image.fromarray(rgb).convert("L"), dtype=np.float32) / 255.0
    p = _resize_f(mask, (sw, sh)) if scale < 1.0 else mask.astype(np.float32)
    r = max(1, int(round(radius * scale)))
    mI, mp = box_mean(g, r), box_mean(p, r)
    cov = box_mean(g * p, r) - mI * mp
    var = box_mean(g * g, r) - mI * mI
    a = cov / (var + eps)
    b = mp - a * mI
    ma, mb = box_mean(a, r), box_mean(b, r)
    band_l = box_mean(((p > 0.02) & (p < 0.98)).astype(np.float32), r + 1) > 0
    out = mask.astype(np.float32, copy=True)
    if not band_l.any():
        return out
    sx, sy = sw / w, sh / h
    for s0, s1, k0, k1 in _strips(h, 0):
        box = (0, s0 * sy, sw, s1 * sy)
        size = (w, s1 - s0)
        band = _resize_f(band_l.astype(np.float32), size, box) > 0.01
        if not band.any():
            continue
        A = _resize_f(ma, size, box) if scale < 1.0 else ma[s0:s1]
        B = _resize_f(mb, size, box) if scale < 1.0 else mb[s0:s1]
        gs = np.asarray(Image.fromarray(rgb[s0:s1]).convert("L"), dtype=np.float32) / 255.0
        q = np.clip(A * gs + B, 0, 1)
        out[s0:s1] = np.where(band, q, out[s0:s1])
    return out


def matting_available() -> bool:
    """Cheap check (no numba import); the real import happens on first use."""
    import importlib.util
    try:
        return importlib.util.find_spec("pymatting") is not None
    except Exception:
        return False


def alpha_matting(rgb: np.ndarray, mask: np.ndarray, fg_th: float = 0.94, bg_th: float = 0.04,
                  erode: int = 10, max_pixels: int = 2_000_000) -> np.ndarray:
    """Closed-form matting via pymatting (optional dependency). Big images are
    matted at reduced size because the solver is slow and memory hungry."""
    from pymatting import estimate_alpha_cf
    from scipy.ndimage import binary_erosion
    h, w = mask.shape
    scale = min(1.0, (max_pixels / (h * w)) ** 0.5)
    if scale < 1.0:
        sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
        img_s = np.asarray(Image.fromarray(rgb).resize((sw, sh), Image.LANCZOS))
        m_s = np.asarray(Image.fromarray(mask.astype(np.float32), "F").resize((sw, sh), Image.BILINEAR))
        er = max(1, int(erode * scale))
    else:
        img_s, m_s, er = rgb, mask, erode
    st = np.ones((er, er), dtype=bool)
    fg = binary_erosion(m_s > fg_th, structure=st)
    bg = binary_erosion(m_s < bg_th, structure=st, border_value=1)
    if not fg.any() or not bg.any():
        return mask
    tri = np.full(m_s.shape, 0.5)
    tri[fg] = 1.0
    tri[bg] = 0.0
    a = estimate_alpha_cf(img_s.astype(np.float64) / 255.0, tri)
    a = np.clip(a, 0, 1).astype(np.float32)
    if scale < 1.0:
        a = np.asarray(Image.fromarray(a, "F").resize((w, h), Image.BILINEAR))
        # keep the sharp model edges where matting had no say
        a = np.where((mask > 0.98) | (mask < 0.02), mask, a)
    return a.astype(np.float32)


# ------------------------------------------------------------------- model
class Remover:
    """Holds one ONNX session. Thread-safe for sequential use from a worker."""

    def __init__(self, model: str = "isnet-general-use", threads: Optional[int] = None,
                 model_path: Optional[Path] = None, progress=None, cancel=None,
                 allow_download: bool = True):
        if model not in MODELS:
            raise ValueError(f"unknown model {model}")
        self.spec = MODELS[model]
        self.model_path = Path(model_path) if model_path else ensure_model(
            model, progress=progress, cancel=cancel, allow_download=allow_download)
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.log_severity_level = 3
        # The arena keeps peak buffers forever (BiRefNet grew 7.4 -> 12 GB on
        # the 2nd image); without it memory stays flat for a small speed cost.
        so.enable_cpu_mem_arena = False
        so.enable_mem_pattern = False
        if threads:
            so.intra_op_num_threads = threads
        try:
            self.session = ort.InferenceSession(str(self.model_path), so, providers=["CPUExecutionProvider"])
        except Exception as e:  # truncated / wrong file in the models folder
            from .models import ModelError
            raise ModelError("bad_model", f"Model file {self.model_path} could not be loaded: {e}. "
                             "Delete it so it is downloaded again.") from e
        self.input_name = self.session.get_inputs()[0].name
        self._lock = threading.Lock()

    def predict_mask(self, rgb: Image.Image) -> np.ndarray:
        """Return float32 HxW mask in 0..1 at the image's own size."""
        s = self.spec.input_size
        im = rgb.convert("RGB").resize((s, s), Image.LANCZOS)
        arr = np.asarray(im, dtype=np.float32)
        arr = arr / max(float(arr.max()), 1e-6)
        mean = np.array(self.spec.mean, dtype=np.float32)
        std = np.array(self.spec.std, dtype=np.float32)
        arr = ((arr - mean) / std).transpose(2, 0, 1)[None].astype(np.float32)
        with self._lock:
            out = self.session.run(None, {self.input_name: arr})[0]
        pred = out[0, 0].astype(np.float32)
        if self.spec.sigmoid:
            pred = 1.0 / (1.0 + np.exp(-pred))
        lo, hi = float(pred.min()), float(pred.max())
        pred = (pred - lo) / (hi - lo) if hi - lo > 1e-6 else np.zeros_like(pred)
        # per-model calibration: U2Net/IS-Net leave large areas half
        # transparent (shirts, fur); a gentle levels curve makes them solid
        # while keeping hair strands soft.
        l0, l1 = self.spec.levels
        if (l0, l1) != (0.0, 1.0):
            pred = np.clip((pred - l0) / (l1 - l0), 0.0, 1.0)
        m = Image.fromarray(pred, "F").resize(rgb.size, Image.BICUBIC)
        return np.clip(np.asarray(m, dtype=np.float32), 0.0, 1.0)


# ------------------------------------------------------------------- options
# kind, width, height, margin(frac), dpi
PRESETS = {
    "none": None,
    "max1080": ("fit", 1080, 1080, 0.0, None),
    "max2000": ("fit", 2000, 2000, 0.0, None),
    "square1080": ("canvas", 1080, 1080, 0.06, None),
    "square2000": ("canvas", 2000, 2000, 0.06, None),
    "story1080x1920": ("canvas", 1080, 1920, 0.06, None),
    "passport4x6": ("canvas", 472, 709, 0.08, 300),      # 4 x 6 cm (Egypt)
    "passport35x45": ("canvas", 413, 531, 0.08, 300),    # 35 x 45 mm (Schengen, UK...)
}


def parse_color(c) -> Optional[tuple]:
    if c is None or c == "" or c == "none" or c == "transparent":
        return None
    if isinstance(c, (tuple, list)):
        return tuple(int(v) for v in c[:3])
    s = str(c).strip().lower()
    named = {"white": (255, 255, 255), "black": (0, 0, 0), "red": (220, 38, 38),
             "blue": (37, 99, 235), "green": (22, 163, 74), "gray": (128, 128, 128),
             "grey": (128, 128, 128), "lightblue": (173, 216, 230)}
    if s in named:
        return named[s]
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError(f"Bad colour '{c}' (use #RRGGBB or a name)")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


@dataclass
class Options:
    model: str = "isnet-general-use"
    out_format: str = "png"          # png | jpg | webp
    bg_color: Optional[tuple] = None  # None = transparent (jpg -> white)
    crop: bool = False
    crop_margin: float = 0.04
    preset: str = "none"
    refine: bool = True               # guided-filter edge refinement
    decontaminate: bool = True        # remove colour halo on edges
    matting: bool = False             # pymatting closed-form (slow)
    jpg_quality: int = 95

    def effective_bg(self) -> Optional[tuple]:
        if self.bg_color is None and self.out_format == "jpg":
            return (255, 255, 255)
        return self.bg_color


@dataclass
class Result:
    image: Image.Image
    mask: np.ndarray
    warnings: list = field(default_factory=list)
    dpi: Optional[tuple] = None


def subject_bbox(alpha: np.ndarray, th: float = 0.04):
    ys = np.where((alpha > th).any(axis=1))[0]
    xs = np.where((alpha > th).any(axis=0))[0]
    if ys.size == 0:
        return None
    return int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1


def make_cutout(rgb: Image.Image, src_alpha: Optional[Image.Image], remover: Remover,
                opts: Options) -> Result:
    warn = []
    mask = remover.predict_mask(rgb)
    arr = np.asarray(rgb, dtype=np.uint8)
    if opts.matting:
        if matting_available():
            if mask.size > 2_000_000:
                warn.append("matting_downscaled")
            mask = alpha_matting(arr, mask)
        else:
            warn.append("matting_unavailable")
    elif opts.refine:
        mask = guided_refine(arr, mask)
    if src_alpha is not None:
        mask = mask * (np.asarray(src_alpha, dtype=np.float32) / 255.0)
    if float(mask.max()) < 0.5 or float((mask > 0.5).mean()) < 0.0005:
        warn.append("no_subject")
    if opts.decontaminate:
        arr = estimate_foreground(arr, mask)
    a8 = (np.clip(mask, 0, 1) * 255 + 0.5).astype(np.uint8)
    rgba = Image.fromarray(np.dstack([arr, a8]), "RGBA")
    return Result(rgba, mask, warn)


def finish(res: Result, opts: Options) -> Result:
    """Crop / resize / place on canvas / flatten background."""
    img = res.image
    alpha = np.asarray(img.getchannel("A"), dtype=np.float32) / 255.0
    bbox = subject_bbox(alpha)
    preset = PRESETS.get(opts.preset)
    dpi = None
    if opts.preset not in PRESETS:
        raise ValueError(f"Unknown size preset '{opts.preset}'")
    W0, H0 = img.size
    touches_bottom = bbox is not None and bbox[3] >= H0 - 2

    if (opts.crop or (preset and preset[0] == "canvas")) and bbox is not None:
        x0, y0, x1, y1 = bbox
        if opts.crop and not (preset and preset[0] == "canvas"):
            m = int(round(max(x1 - x0, y1 - y0) * opts.crop_margin))
            x0, y0 = max(0, x0 - m), max(0, y0 - m)
            x1, y1 = min(W0, x1 + m), min(H0, y1 + m)
        img = img.crop((x0, y0, x1, y1))

    if preset:
        kind, W, H, margin, dpi = preset
        if kind == "fit":
            w, h = img.size
            s = min(W / w, H / h)
            if s < 1.0:
                img = img.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
        else:
            w, h = img.size
            mw, mh = W * (1 - 2 * margin), H * (1 - 2 * margin)
            if touches_bottom:
                mh = H * (1 - margin)          # head-and-shoulders: no bottom margin
            s = min(mw / w, mh / h)
            nw, nh = max(1, round(w * s)), max(1, round(h * s))
            img = img.resize((nw, nh), Image.LANCZOS)
            canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            x = (W - nw) // 2
            y = H - nh if touches_bottom else (H - nh) // 2
            canvas.paste(img, (x, y))
            img = canvas
            if bbox is None:
                res.warnings.append("no_subject")

    bg = opts.effective_bg()
    if bg is not None:
        base = Image.new("RGBA", img.size, tuple(bg) + (255,))
        img = Image.alpha_composite(base, img).convert("RGB")
    return Result(img, res.mask, res.warnings, (dpi, dpi) if dpi else None)


def process(src, remover: Remover, opts: Options) -> Result:
    rgb, alpha, info = load_image(src)
    res = finish(make_cutout(rgb, alpha, remover, opts), opts)
    if res.dpi is None and info.get("dpi"):
        try:
            res.dpi = tuple(float(v) for v in info["dpi"][:2])
        except Exception:
            pass
    return res


def save(res: Result, path: Union[str, Path], opts: Options) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img = res.image
    kw = {}
    if res.dpi:
        kw["dpi"] = res.dpi
    fmt = opts.out_format
    tmp = path.with_name(path.name + ".tmp")
    if fmt == "jpg":
        if img.mode != "RGB":
            img = Image.alpha_composite(Image.new("RGBA", img.size, (255, 255, 255, 255)), img.convert("RGBA")).convert("RGB")
        img.save(tmp, "JPEG", quality=opts.jpg_quality, subsampling=0, optimize=True, **kw)
    elif fmt == "webp":
        img.save(tmp, "WEBP", quality=95, method=4, exact=True, **{k: v for k, v in kw.items() if k != "dpi"})
    else:
        img.save(tmp, "PNG", optimize=False, compress_level=3, **kw)
    tmp.replace(path)
    return path
