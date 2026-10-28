# Atlas BG Remover: User manual · دليل الاستخدام

## English

1. **Install:** unzip `Atlas_BG_Remover_Win.zip` anywhere and run `Atlas_BG_Remover.exe`.
   - The app is not code-signed yet. If Windows SmartScreen says "Windows protected your PC", click **More info → Run anyway**.
2. **Language:** the top button switches between English and عربي. Your choice is remembered.
3. **Add images:**
   - Drag files or folders onto the **Images** list, or use **Add images** / **Add folder**.
   - Remove entries with **Remove** (or the Delete key) or **Clear**.
4. **Preview:** select an image and press **Preview selected**. You can also double-click it. You'll see before and after with the current settings. Nothing is saved.
5. **Settings** (saved automatically):
   - **Model:**
     - *Fast & good* suits most photos.
     - *Best quality* is better on hair, fur and fine detail, but slow. It needs ~7 GB of free RAM; the app warns you if you have less.
     - *Tiny* works with no download.
     - The line under the menu shows whether the model is ready or how big the one-time download is.
   - **Output format:** PNG (transparent), JPG (always a solid background), WebP (transparent, smaller).
   - **Background:** Transparent, White, or a Custom colour (click **Colour**).
   - **Size:** keep the original size, or pick a preset.
     - Square/story/passport presets centre the subject with a small margin. They keep a person's shoulders at the bottom edge.
     - Passport presets set 300 dpi so they print at the right size.
   - **Crop to subject:** trims empty space around the subject.
   - **Edges:**
     - *Smart refine* is recommended.
     - *Alpha matting* is only shown if installed. It's very slow and sometimes better on hair.
     - *Off* gives the raw model mask.
   - **Remove colour halo:** removes the old background's colour from soft edges such as hair and fur.
   - **Save to:** the output folder. Default: `%USERPROFILE%\AtlasRecordings\BgRemover`.
6. **Remove backgrounds:**
   - Processes the whole list. ✓ / ✗ marks show each file's result; click a ✗ to see why it failed.
   - **Cancel** stops after the current image.
   - **Open folder** opens the output folder.

### Errors
| Message | What to do |
|---|---|
| Not an image / unsupported | The file isn't a picture (e.g. PDF, text) or the format isn't supported. |
| Damaged or truncated | Re-download or re-export the photo. |
| Too large (>120 MP) | Resize the image first. |
| Could not download the model | Check the internet connection. You can also use the built-in *Tiny* model, or copy the `.onnx` file into the `models` folder shown in the message. |
| Model file is damaged | Delete the file shown and try again. It will download again. |

### Tips
- Product photos for stores: **JPG + White + Square 2000 + Crop to subject**.
- Passport photo: **JPG + White + Passport 4×6**. Use a straight-on photo with good light.
- Hair and fur look best with *Best quality*, or with *Fast & good* plus *Remove colour halo*.
- Busy scenes such as groups or rooms can pick up background objects. Check the preview first.

## العربي

1. **التشغيل:** فك ضغط الملف وشغّل `Atlas_BG_Remover.exe`.
   - البرنامج لسه مش موقّع رقميًا. لو ويندوز قال "Windows protected your PC"، اضغط **More info** وبعدين **Run anyway**.
2. **اللغة:** الزرار اللي فوق بيبدّل بين عربي وEN، والبرنامج بيفتكر اختيارك.
3. **إضافة الصور:** اسحب الصور أو الفولدرات على قايمة **الصور**، أو استخدم **إضافة صور** و**إضافة مجلد**.
4. **المعاينة:** اختار صورة واضغط **معاينة الصورة المحددة**، أو دبل كليك عليها. هتشوف قبل وبعد بالإعدادات الحالية، ومش هيتحفظ حاجة.
5. **الإعدادات** (بتتحفظ لوحدها):
   - **النموذج:**
     - *سريع وجيد* مناسب لمعظم الصور.
     - *أعلى جودة* أحسن في الشعر والفرو، لكنه بطيء ومحتاج حوالي 7 جيجا رام.
     - *صغير* بيشتغل من غير تنزيل.
   - **صيغة الحفظ:** PNG شفاف، أو JPG بخلفية، أو WebP شفاف وحجمه أصغر.
   - **الخلفية:** شفافة، أو بيضاء، أو لون تختاره من زرار **اللون**.
   - **المقاس:** الأصلي، أو مقاس جاهز. مقاسات الباسبور بتتحفظ بدقة 300 نقطة عشان تتطبع بالمقاس الصح.
   - **قص حول العنصر:** بيشيل المساحة الفاضية حوالين العنصر.
   - **الحواف:** *تنعيم ذكي* هو المستحسن.
   - **إزالة الهالة اللونية:** بتشيل لون الخلفية القديمة من أطراف الشعر والفرو.
   - **الحفظ في:** الفولدر اللي النتايج بتتحفظ فيه.
6. **إزالة الخلفيات:**
   - بيعالج كل الصور اللي في القايمة. علامة ✓ معناها الصورة نجحت، و✗ معناها فشلت؛ دوس على أي ✗ عشان تعرف السبب.
   - زرار **إلغاء** بيوقف بعد الصورة الحالية.
   - زرار **فتح المجلد** بيفتح فولدر النتايج.

### نصايح
- صور المنتجات للمتاجر: **JPG + بيضاء + مربع 2000 + قص حول العنصر**.
- صورة الباسبور: **JPG + بيضاء + باسبور 4×6**، وتكون الصورة من الأمام والإضاءة كويسة.
- الصور الزحمة، زي المجموعات أو الأوض، ممكن يفضل فيها حاجات من الخلفية. اعمل معاينة الأول.
