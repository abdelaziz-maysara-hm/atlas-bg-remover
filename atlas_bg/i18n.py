"""UI strings (Arabic + English) and Arabic display helper. No GUI imports."""
from __future__ import annotations

import os
import re
import sys

T = {
    "en": {
        "title": "ATLAS  BG Remover",
        "tagline": "Offline  ·  no watermark  ·  no limits  ·  nothing is uploaded",
        "lang": "عربي",
        "files": "Images",
        "add": "Add images",
        "add_dir": "Add folder",
        "remove": "Remove",
        "clear": "Clear",
        "drop": "Drag & drop images or folders here",
        "drop_off": "Use the buttons to add images",
        "count": "{n} images",
        "count1": "1 image",
        "before": "Before",
        "after": "After",
        "preview": "Preview selected",
        "preview_hint": "Select an image, then press Preview",
        "settings": "Settings",
        "model": "Model",
        "m_isnet-general-use": "Fast & good – IS-Net (recommended)",
        "m_birefnet-lite": "Best quality – BiRefNet (slow, 8 GB RAM)",
        "m_u2net": "Classic – U²-Net",
        "m_u2netp": "Tiny – U²-Netp (old PCs, built in)",
        "installed": "Model ready on this PC",
        "will_dl": "Downloads once: {mb} MB",
        "format": "Output format",
        "bg": "Background",
        "bg_none": "Transparent",
        "bg_white": "White",
        "bg_custom": "Custom colour…",
        "pick": "Colour",
        "crop": "Crop to subject",
        "size": "Size",
        "p_none": "Original size",
        "p_max1080": "Max 1080 px",
        "p_max2000": "Max 2000 px",
        "p_square1080": "Square 1080 (Instagram)",
        "p_square2000": "Square 2000 (shops: Jumia/Amazon)",
        "p_story1080x1920": "Story 1080×1920",
        "p_passport4x6": "Passport 4×6 cm (300 dpi)",
        "p_passport35x45": "Passport 35×45 mm (300 dpi)",
        "edges": "Edges",
        "e_refine": "Smart refine (fast)",
        "e_matting": "Alpha matting (very slow)",
        "e_off": "Off",
        "halo": "Remove colour halo",
        "out": "Save to",
        "browse": "Change…",
        "start": "Remove backgrounds",
        "cancel": "Cancel",
        "open": "Open folder",
        "ready": "Ready",
        "need": "Add some images first.",
        "loading_model": "Loading model…",
        "downloading": "Downloading model {p}% ({mb} MB)",
        "processing": "Processing {i}/{n}: {name}",
        "cancelling": "Cancelling after the current image…",
        "cancelled": "Cancelled: {ok} saved",
        "done": "Done: {ok} saved, {bad} failed  ·  {sec:.1f} s",
        "previewing": "Making preview…",
        "jpg_note": "JPG has no transparency, so a white background is used.",
        "ram_warn": "This model needs about {need} MB of free memory but only {free} MB is free. "
                    "It may be very slow or crash. Continue?",
        "dnd_missing": "Drag & drop is not available here; use the buttons.",
        "err_title": "Problem",
        "e_not_found": "File not found",
        "e_not_image": "Not an image (or unsupported format)",
        "e_corrupt": "Damaged or incomplete image",
        "e_too_large": "Image too large (over 120 MP) – resize it first",
        "e_memory": "Not enough memory for this image",
        "e_write": "Could not save the result (folder read-only or disk full?)",
        "e_internal": "Unexpected error",
        "e_offline": "Could not download the model. Check your internet connection and try again, or pick the built-in \"Tiny – U²-Netp\" model, which works offline. "
                     "You can also copy the model file into:\n{dir}",
        "e_interrupted": "The download was interrupted. Try again.",
        "e_checksum": "The downloaded model was damaged and has been deleted. Try again.",
        "e_no_write": "Cannot create the models folder:\n{dir}",
        "e_bad_model": "The model file is damaged. Delete it and try again:\n{path}",
        "e_cancelled": "Cancelled",
        "e_unknown": "Unknown model",
        "w_no_subject": "no clear subject found",
        "w_matting_downscaled": "matting done at reduced size",
        "w_matting_unavailable": "alpha matting not installed – used normal edges",
    },
    "ar": {
        "title": "أطلس  إزالة الخلفية",
        "tagline": "بدون إنترنت  ·  بدون علامة مائية  ·  بدون حدود  ·  من غير رفع على النت",
        "lang": "EN",
        "files": "الصور",
        "add": "إضافة صور",
        "add_dir": "إضافة مجلد",
        "remove": "حذف",
        "clear": "مسح الكل",
        "drop": "اسحب الصور أو المجلدات وأفلتها هنا",
        "drop_off": "استخدم الأزرار لإضافة الصور",
        "count": "{n} صورة",
        "count1": "صورة واحدة",
        "before": "قبل",
        "after": "بعد",
        "preview": "معاينة الصورة المحددة",
        "preview_hint": "اختار صورة واضغط معاينة",
        "settings": "الإعدادات",
        "model": "النموذج",
        "m_isnet-general-use": "سريع وجيد – IS-Net (موصى به)",
        "m_birefnet-lite": "أعلى جودة – BiRefNet (بطيء، 8 جيجا رام)",
        "m_u2net": "كلاسيكي – U²-Net",
        "m_u2netp": "صغير – U²-Netp (للأجهزة القديمة، مدمج)",
        "installed": "النموذج جاهز على الجهاز",
        "will_dl": "هيتحمّل مرة واحدة: {mb} ميجا",
        "format": "صيغة الحفظ",
        "bg": "الخلفية",
        "bg_none": "شفافة",
        "bg_white": "بيضاء",
        "bg_custom": "لون مخصص…",
        "pick": "اللون",
        "crop": "قص حول العنصر",
        "size": "المقاس",
        "p_none": "المقاس الأصلي",
        "p_max1080": "أقصى حد 1080 بكسل",
        "p_max2000": "أقصى حد 2000 بكسل",
        "p_square1080": "مربع 1080 (إنستجرام)",
        "p_square2000": "مربع 2000 (متاجر: جوميا وأمازون)",
        "p_story1080x1920": "ستوري 1080×1920",
        "p_passport4x6": "صورة باسبور 4×6 سم (300 نقطة)",
        "p_passport35x45": "صورة باسبور 35×45 مم (300 نقطة)",
        "edges": "الحواف",
        "e_refine": "تنعيم ذكي (سريع)",
        "e_matting": "Alpha matting (بطيء جدًا)",
        "e_off": "إيقاف",
        "halo": "إزالة الهالة اللونية",
        "out": "الحفظ في",
        "browse": "تغيير…",
        "start": "إزالة الخلفيات",
        "cancel": "إلغاء",
        "open": "فتح المجلد",
        "ready": "جاهز",
        "need": "ضيف صور الأول.",
        "loading_model": "جاري تحميل النموذج…",
        "downloading": "جاري تنزيل النموذج {p}% ({mb} ميجا)",
        "processing": "جاري المعالجة {i}/{n}: {name}",
        "cancelling": "هيتم الإلغاء بعد الصورة الحالية…",
        "cancelled": "تم الإلغاء: اتحفظ {ok}",
        "done": "خلصنا: اتحفظ {ok}، وفشل {bad}  ·  {sec:.1f} ثانية",
        "previewing": "جاري تجهيز المعاينة…",
        "jpg_note": "صيغة JPG مفيهاش شفافية، فهتتحط خلفية بيضاء.",
        "ram_warn": "النموذج ده محتاج حوالي {need} ميجا رام فاضية، والمتاح {free} ميجا بس. "
                    "ممكن يبقى بطيء جدًا أو يقفل. تكمل؟",
        "dnd_missing": "السحب والإفلات مش متاح هنا، استخدم الأزرار.",
        "err_title": "مشكلة",
        "e_not_found": "الملف مش موجود",
        "e_not_image": "الملف مش صورة (أو صيغة غير مدعومة)",
        "e_corrupt": "الصورة تالفة أو ناقصة",
        "e_too_large": "الصورة كبيرة جدًا (أكتر من 120 ميجابكسل)، صغّرها الأول",
        "e_memory": "الذاكرة مش كفاية للصورة دي",
        "e_write": "مقدرناش نحفظ النتيجة (المجلد للقراءة بس أو المساحة خلصت؟)",
        "e_internal": "خطأ غير متوقع",
        "e_offline": "مقدرناش ننزّل النموذج. اتأكد من الإنترنت وجرّب تاني، أو اختار النموذج المدمج \"صغير – U²-Netp\" اللي بيشتغل من غير نت. "
                     "وممكن تنسخ ملف النموذج بنفسك في:\n{dir}",
        "e_interrupted": "التنزيل اتقطع. جرّب تاني.",
        "e_checksum": "ملف النموذج اللي اتنزل كان بايظ واتمسح. جرّب تاني.",
        "e_no_write": "مقدرناش نعمل مجلد النماذج:\n{dir}",
        "e_bad_model": "ملف النموذج بايظ. امسحه وجرّب تاني:\n{path}",
        "e_cancelled": "تم الإلغاء",
        "e_unknown": "نموذج غير معروف",
        "w_no_subject": "مفيش عنصر واضح",
        "w_matting_downscaled": "الـ matting اتعمل بمقاس أصغر",
        "w_matting_unavailable": "الـ alpha matting مش متثبت، واستخدمنا الحواف العادية",
    },
}

_ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")


def needs_shaping(windowing_system: str) -> bool:
    """Tk on Windows (Uniscribe) and macOS (CoreText) shape and reorder Arabic
    itself. Tk on X11 draws characters one by one, left to right, so we must
    reshape + apply the bidi algorithm ourselves there.
    ATLAS_ARABIC_SHAPING=1/0 overrides."""
    env = os.environ.get("ATLAS_ARABIC_SHAPING")
    if env in ("0", "1"):
        return env == "1"
    return windowing_system == "x11"


def shape(text: str, enabled: bool, base: str = "R") -> str:
    if not enabled or not text or not _ARABIC.search(text):
        return text
    try:
        import arabic_reshaper
        # pure-Python implementation: unlike bidi.get_display (Rust) in
        # python-bidi 0.6 it mirrors brackets, so "(...)" stays correct.
        from bidi.algorithm import get_display
    except Exception:
        return text
    out = []
    for line in text.split("\n"):
        out.append(get_display(arabic_reshaper.reshape(line), base_dir=base))
    return "\n".join(out)
