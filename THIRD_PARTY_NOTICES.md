# Third-party notices

Atlas BG Remover's own code is released under the **MIT License** (see `LICENSE`).
The components and model weights below keep their own licences.

## AI models (ONNX)
The ONNX conversions are downloaded from the rembg release page:
https://github.com/danielgatis/rembg/releases/tag/v0.0.0

| Model | Upstream | Licence | Notes |
|---|---|---|---|
| U²-Netp (bundled) | https://github.com/xuebinqin/U-2-Net | Apache-2.0 | Safe to redistribute with attribution. |
| U²-Net | https://github.com/xuebinqin/U-2-Net | Apache-2.0 | Downloaded on first use. |
| IS-Net general-use | https://github.com/xuebinqin/DIS | Apache-2.0 (repository) | ⚠ See below. Downloaded on first use. |
| BiRefNet (general, swin_v1_tiny, "lite") | https://github.com/ZhengPeng7/BiRefNet | MIT | Downloaded on first use. |

⚠ **IS-Net:**
- The DIS repository is Apache-2.0. Its README says the code and evaluation metric are Apache-2.0.
- The weights are not licensed separately, and the DIS5K training dataset has its own Terms of Use PDF.
- rembg and many commercial tools ship it, but it is less clear-cut than U²-Net or BiRefNet. Review this before commercial use.
- If in doubt, make BiRefNet or U²-Net the default (one line in `atlas_bg/models.py`).

**Deliberately not used:** BRIA RMBG-1.4/2.0. Its licence is non-commercial (Creative Commons BY-NC / BRIA custom).

## Libraries in the Windows build
| Package | Licence |
|---|---|
| ONNX Runtime | MIT |
| NumPy | BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| CustomTkinter | MIT |
| tkinterdnd2 / tkdnd | MIT / BSD-style (tkdnd) |
| darkdetect (via CustomTkinter) | BSD-3-Clause |
| Python, Tcl/Tk | PSF-2.0, Tcl/Tk licence (BSD-style) |
| PyInstaller bootloader | GPL-2.0 with a bootloader exception, which allows distributing built apps under any licence |

## Optional / Linux-only (not in the default Windows build)
| Package | Licence | Use |
|---|---|---|
| pymatting (+numba, llvmlite, scipy) | MIT / BSD | Optional "Alpha matting" edge mode (`scripts/build.py --matting`). |
| arabic-reshaper | MIT | Arabic shaping on Linux/X11 only. |
| python-bidi | **LGPL-3.0** | Linux/X11 only. Excluded from the Windows exe because Windows Tk renders Arabic natively. |

## Method credits
- Fast guided filter: K. He, J. Sun, "Fast Guided Filter", 2015.
- Foreground colour estimation (halo removal): M. Forte, F. Pitié, "Approximate Fast Foreground Colour Estimation", ICIP 2021.
- Preprocessing follows rembg (MIT): https://github.com/danielgatis/rembg
