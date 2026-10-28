# Atlas BG Remover · أطلس إزالة الخلفية

Free, offline background remover for Windows. Batch processing, no watermark, no limits, and nothing is uploaded.
Arabic and English UI.

برنامج مجاني لإزالة خلفية الصور على ويندوز، بيشتغل من غير إنترنت. بيعالج صور كتير مرة واحدة، من غير علامة مائية ولا حدود، ومفيش أي صورة بتترفع على النت.
الواجهة عربي وإنجليزي.

> remove.bg's standalone site closes on 1 Dec 2026. This app is an offline alternative for sellers, photographers and passport/ID photos.

---

## English

### Features
- Add images or whole folders by **drag & drop** or the file/folder pickers.
  Formats: JPG, PNG, WebP, BMP, TIFF and GIF. Subfolders are included.
- **Batch** processing with a progress bar and **Cancel**. One bad file never stops the batch.
- **Before / after preview** on a checkerboard.
- **Models**, all running locally on the CPU:

  | Choice | Model | Licence | Download | Speed* |
  |---|---|---|---|---|
  | Fast & good (default) | IS-Net general | Apache-2.0 (see notes) | 171 MB once | ~1.7 s/img |
  | Best quality | BiRefNet-lite | MIT | 214 MB once, needs ~7 GB free RAM | ~9.5 s/img |
  | Classic | U²-Net | Apache-2.0 | 168 MB once | ~1.2 s/img |
  | Tiny (built in) | U²-Netp | Apache-2.0 | bundled, works offline | ~1.1 s/img |

  \*Measured on an 8-core Linux VM with 2–4 MP photos, including edge refinement and saving.
- **Output**:
  - PNG or WebP with transparency, or JPG.
  - JPG always gets a solid background (white by default, or any colour).
- **Crop to subject** and **size presets**:
  - max 1080/2000 px;
  - square 1080/2000 (Instagram, Jumia/Amazon);
  - story 1080×1920;
  - passport 4×6 cm and 35×45 mm at 300 dpi.
- **Edges**:
  - Smart refine (guided filter) and colour-halo removal;
  - optional Alpha matting when `pymatting` is installed (slow).
- Handles:
  - EXIF rotation;
  - CMYK/ICC images, converted to sRGB;
  - 16-bit, palette and transparent inputs (existing transparency is kept);
  - Arabic file names.
- Rejects images over 120 MP. Corrupt or non-image files show a clear message.
- Never overwrites: outputs are `name_nobg.png`, `name_nobg (1).png`, and so on.

### Run from source
```bash
python -m venv .venv && .venv\Scripts\activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python atlas_bg_gui.py                                  # GUI
python -m atlas_bg photos/ -o out -f jpg --bg white --preset square2000   # CLI
python -m atlas_bg --list-models
```
CLI exit codes:
- `0`: all OK.
- `1`: some files failed.
- `2`: model or usage error.
- `3`: cancelled.

### Models: download & offline use
- **U²-Netp** ships inside the app.
- The other models download **once**, the first time you use them. Downloads are MD5-verified and go to:
  - Windows: `%LOCALAPPDATA%\AtlasBgRemover\models`
  - Linux: `~/.cache/atlas-bg-remover/models`
  - Any OS: override with the `ATLAS_BG_MODELS` env var.
- **Offline PCs:** copy the `.onnx` files into a `models` folder next to `Atlas_BG_Remover.exe`, or into the folder above.
- **"Full bundle" option:** put all four `.onnx` files (~570 MB) in `models/` before zipping. Nothing else changes.

### Build the Windows app
`.github/workflows/build-windows.yml` runs on `windows-latest` with Python 3.12. It:
1. runs the unit tests;
2. builds a one-folder PyInstaller app (`scripts/build.py`);
3. runs the frozen exe's `--selftest`;
4. uploads `Atlas_BG_Remover_Win.zip`.

On a `v*` tag it also attaches the zip to a GitHub release.

To build locally: `pip install -r requirements-dev.txt && python scripts/build.py`. Add `--matting` to bundle Alpha matting (+~150 MB).

### Tests
```bash
pip install -r requirements-dev.txt
python -m pytest -q tests        # needs models/u2netp.onnx (+ isnet for one real-photo test)
```
`tests/gui_smoke.py` drives the GUI under Xvfb and takes screenshots.

### Licence
**Not chosen yet.** The owner will choose before publishing. Third-party licences are in `THIRD_PARTY_NOTICES.md`.

---

## العربي

### المميزات
- ضيف صور أو فولدرات كاملة بالسحب والإفلات أو بالأزرار. الفولدرات الفرعية بتتضاف كمان.
  الصيغ المدعومة: JPG وPNG وWebP وBMP وTIFF وGIF.
- معالجة صور كتير مرة واحدة، مع شريط تقدم وزرار إلغاء. لو فيه صورة بايظة، الباقي بيكمل عادي.
- معاينة "قبل وبعد" على خلفية مربعات.
- أربع نماذج، كلها شغالة على الجهاز:
  - **سريع وجيد (IS-Net):** الافتراضي.
  - **أعلى جودة (BiRefNet):** بطيء ومحتاج حوالي 7 جيجا رام فاضية.
  - **كلاسيكي (U²-Net).**
  - **صغير (U²-Netp):** مدمج في البرنامج وبيشتغل من غير نت.
- الحفظ:
  - PNG أو WebP بخلفية شفافة، أو JPG.
  - الـ JPG لازم يبقى بخلفية، بيضاء أو أي لون تختاره. ده مناسب لصور المنتجات وصور الباسبور.
- قص حول العنصر، ومقاسات جاهزة:
  - مربع 1080 لإنستجرام، ومربع 2000 لجوميا وأمازون؛
  - ستوري؛
  - باسبور 4×6 سم و35×45 مم بدقة 300 نقطة.
- تنعيم ذكي للحواف، وإزالة الهالة اللونية حوالين الشعر والفرو.
- بيتعامل مع الحالات دي صح:
  - الصور المتلفة في الموبايل (EXIF)؛
  - صور CMYK؛
  - الصور الشفافة؛
  - أسماء الملفات العربي.
- مش بيكتب فوق ملفاتك أبدًا: النتيجة اسمها `الاسم_nobg.png`.

### النماذج والإنترنت
- النموذج الصغير جوه البرنامج.
- الباقيين بيتنزلوا مرة واحدة أول ما تستخدمهم، وبعد كده البرنامج كله بيشتغل من غير نت.
- لو الجهاز مفيهوش نت: انسخ ملفات `.onnx` في فولدر `models` جنب ملف البرنامج.

### الترخيص
لسه ما اتحددش، وصاحب المشروع هيختاره قبل النشر. تراخيص المكتبات والنماذج موجودة في `THIRD_PARTY_NOTICES.md`.
