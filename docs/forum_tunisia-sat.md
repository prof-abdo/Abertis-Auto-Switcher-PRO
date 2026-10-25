# Abertis Auto Switcher PRO v1.9.13 – التشغيل التلقائي لجميع تغذيات أبيرتيس (Enigma2: DreamOS وOpenATV معاً)

أهلاً بكم إخواني أعضاء منتدى تونس-سات الكرام،

يسعدني أن أضع بين أيديكم إضافتي **Abertis Auto Switcher PRO**، حزمة أوتوماتيك
كاملة لتشغيل **جميع تغذيات أبيرتيس على القمر 30 غرباً (Hispasat)**، طوّرتها
ومجرّبتها عملياً على جهاز **Dreambox Two**، تحت **DreamOS 2.6 (بايثون 2.7)**
وتحت **openATV 8.0.1 (بايثون 3.14)**.

**GitHub:** https://github.com/prof-abdo/Abertis-Auto-Switcher-PRO

---

## ماذا تفعل الإضافة؟

على القمر 30 غرباً تبثُّ تغذيات أبيرتيس عشرات القنوات (المفتوحة والمشفَّرة
BISS) مجمَّعة داخل **مولتيبلكس T2-MI واحد**. تظهر كل تغذية على الإنجيما2
كمجموعة PIDs مستقلة (`Abertis PID 301 / 303 / 420 / 2025 / 2026 / 2050 / 8001
/ 8008 …`). في العادة تضطر إلى إعادة ضبط astra-sm و oscam.dvbapi و SoftCam.Key
و lamedb **لكل تغذية يدوياً، ومع كل تغيّر في التغذية**.

هذه الإضافة تنجز ذلك كله **بضغطة واحدة** (أو تلقائياً بعد كل إقلاع).

### التسلسل التلقائي (من F1 إلى F5)
عندما تنتقل (Zap) إلى أي رابط streamrelay من إعدادات الأخ Ciefp بالصيغة
`http://127.0.0.1:8001/abertis/pid<الرقم>` تقوم الإضافة بما يلي:

1. تقرأ **/etc/enigma2/lamedb** وتجد المرجع (Service Reference) الخاص بـ
   `Abertis PID <الرقم>`، مع **PMT PID الخارجي** و**data PID بصيغة c:00xxxx**.
2. **مرحلة التعلُّم (F1)** – تنقل القناة إلى الوضع F1 وتحفظ data PID + PMT PID،
   ثم تطلب من الإنجيما2 **إعادة تحميل lamedb** حتى يتعرَّف على برنامج CA
   الخاص بالقناة المشفَّرة.
3. **التشغيل (F5)** – تعود إلى F5 مع data PID المحفوظ وتعيد التحميل مرة
   أخرى – فتعمل الصورة.
4. كل شيء **يُسجَّل لحظياً**، وتؤخذ نسخة احتياطية قبل أي تعديل، والعملية
   **قابلة للتكرار (idempotent)**: نفّذها ألف مرة دون أن يحدث أي تكرار أو تلف.

### قواعد A ومفاتيح BISS وبلوكات البث تلقائياً
* قاعدة **`A:` واحدة لكل تغذية** لمحاكاة oscam-emu في
  `/etc/tuxbox/config/oscam.dvbapi`، مع الاحتفاظ بنسخة احتياطية.
* مزامنة مفاتيح BISS الناقصة من `softcam.key` إلى `SoftCam.Key`
  (oscam-emu يقرأ الملف المكتوب بأحرف كبيرة).
* توليد كل **بلوكات البث الناقصة لـ astra-sm** داخل `/etc/astra/astra.conf`
  لكي يعمل أي PID جديد مباشرة.

### منظومة astra-sm / T2-MI التلقائية
* تُرفق ثنائيات **astra-sm 0.2.88 (المعدَّلة لـ t2mi payload PID 0x90)
  + `t2mi_decap` + `spammer`** **لأجهزة aarch64**، وثنائي **`abertis`**
  الأصلي الثابت لتفريغ T2-MI (static) **لأجهزة aarch64 و arm (32 بت)
  و mips**.
* كتابة `/etc/init.d/astra` + خدمة **astra-sm.service** لكي يبدأ astra
  تلقائياً في كل إقلاع بارد (فقط إذا كانت الصورة لا تدير astra بنفسها).
* إضافة `streamrelay.socket` حتى يبقى مخرج المنفذ 8001 مشغولاً دائماً.

### إصلاح lamedb قبل بدء تشغيل الإنجيما2
سكربت صغير `prestart_fix.py` يعمل **قبل** أن يكتب الإنجيما2 لقطةً خاصة به من
lamedb (عبر ملف drop-in لخدمة systemd من نوع `ExecStartPre`)، فلا تفقد بيانات
`c:00xxxx` المحفوظة في الذاكرة بعد أي ريسكان.

### حل التقطيع (ta9ti3)
ملف ضبط شبكة `/etc/sysctl.d/99-abertis.conf` (من المشروع المرجعي Ciefp) يحتوي
على **مخازن شبكة (socket buffers) بمقدار 16 ميغابايت** لبروتوكلي UDP/TCP، وضبط
`vm.dirty*` الخاصة بكتابة الصفحات (page-write tuning)، و`net.ipv4.tcp_tw_recycle = 0` – هذه تمنع **فقد
الحزم الذي يقص الصورة** عندما تمر تغذيات أبيرتيس عالية المعدّل داخل المسار
`streamproxy → astra → HTTP`.

### الجديد في v1.9.13: صيغتا حزم، عائلتا صور… مع دعم حقيقي للمعماريات
* **صور DreamOS / Debian (dpkg)** ← تثبِّت الحزمة **`.deb`**
* **صور OpenATV / OpenPLi / opkg** ← تثبِّت الحزمة **`.ipk`**
* **المثبِّت ذو السطر الواحد يكتشف تلقائياً** نظام الحزم ويختار الصيغة
  المناسبة؛ لا حاجة لأي تعليمات إضافية.
* **دعم المعماريات في حزمة واحدة**: يكتشف معمارية الجهاز (`uname -m`) وينشر
  الثنائيات المطابقة:
  * **aarch64 / arm64** – الأدوات الكاملة (`astra`، `t2mi_decap`، `spammer`، `abertis`)
  * **arm (32 بت) / mips** – أداة `abertis` الأصلية الثابتة لتفريغ T2-MI
* **لا تُنشر أبداً ثنائيات بمعمارية خاطئة**: على أجهزة arm/mips تبقى ثنائيات
  الإصدار المثبتة عندك دون مساس، وتُنشر فقط أداة `abertis` المطابقة لمعمارية
  جهازك (ويُسجَّل القرار في السجل، مثلاً `astra: no mips binary shipped,
  leaving the installed one untouched`).
* **الصور التي لا تملك OpenSSL 3 لن تحصل أبداً على astra معطوب**: نسخة astra
  المعدَّلة مربوطة بمكتبة `libcrypto.so.3`. إذا كانت الصورة تفتقدها
  (مثلاً openATV 8.0.1 التي تأتي بـ libcrypto.so.4 / 1.0.2 فقط) تُنشر المكتبة
  المرافقة للحزمة في `/usr/lib` **فقط إذا كانت غائبة** ثم يُحدَّث `ldconfig`؛
  وإذا تعذَّر توفير مكتبة ضرورية، لا تُثبَّت نسختنا إطلاقاً و**يبقى ما كان
  شغَّالاً عندك كما هو**. كل ملف يتم استبداله يُحفظ مرة واحدة باسم `*.orig`.
* رسالة ما بعد التثبيت (postinst) لم تعد تطلب إعادة إقلاع: **الإضافة تُحمَّل عند إعادة
  تشغيل الإنجيما2 التي تجريها بنفسك متى شئت**.

### لا شيء يُستبدَل أبداً
`/etc/astra/astra.conf` و `/etc/astra/scripts/abertis` وملفات OSCam ومفاتيح
softcam العاملة تُحفظ **دون استبدال إطلاقاً**: تُضاف **المدخلات الناقصة فقط**،
ويؤخذ من كل شيء نسخة احتياطية أولاً (`.orig` / `.abetrisauto.bak` /
`/root/abetris-backup`). ملفات مفاتيح أبيرتيس تُنشر بصيغة **`*.dist`** فتبقى
مفاتيح الأجهزة القديمة كما هي دون مساس؛ وتُثبَّت تلقائياً في الصور الجديدة.

---

## التثبيت (سطر واحد، يعمل على عائلتا الصور)

في طرفية **root** للمستقبل:

```
wget https://raw.githubusercontent.com/prof-abdo/Abertis-Auto-Switcher-PRO/main/installer.sh -O - | /bin/sh
```

**أو تثبيت يدوي:**

```
# صور DreamOS / Debian (dpkg):
cd /tmp
wget -O abertis-pro.deb https://github.com/prof-abdo/Abertis-Auto-Switcher-PRO/releases/download/v1.9.13/enigma2-plugin-extensions-abertisautoswitcher_1.9.13_all.deb
dpkg -i abertis-pro.deb

# صور OpenATV / OpenPLi / opkg:
cd /tmp
wget -O abertis-pro.ipk https://github.com/prof-abdo/Abertis-Auto-Switcher-PRO/releases/download/v1.9.13/enigma2-plugin-extensions-abertisautoswitcher_1.9.13_all.ipk
opkg install --force-reinstall --force-overwrite abertis-pro.ipk
```

(نسخ `.ipk` القديمة v1.0 → v1.9.12 ما زالت على GitHub للصور الأقدم،
والمثبِّت يرقّيها دون الإخلال بالإعدادات القائمة).

## قائمة إضافة

`Menu → Extensions → AbertisAutoSwitcher`

يمكن تشغيل التسلسل كله يدوياً بـ «Run setup» واحدة – ويعمل التسلسل التلقائي
بعد كل إقلاع وعند كل زاب على رابط Ciefp.

## ما تحتاجه

* جهاز Enigma2 بصورة فيها **dpkg (DreamOS 2.6) أو opkg (OpenATV 8 / OpenPLi)**.
* صحن موجه نحو **30 غرباً** و **تونر حر** واحد لمولتيبلكسات أبيرتيس
  (Hispasat 12583 V، مولتيبلكس T2-MI).
* **OSCam مع oscam-emu** مثبت (يدعم BISS).
* **إعدادات وقوائم Ciefp** التي توفر روابط `/abertis/pid<n>`
  (إعدادات T2-MI أبيرتيس هي المرجع).

## لقطات الشاشة

*(تُدرج هنا: abetris_osd_1.png – بانر OSD أثناء مرحلة التعلُّم F1،
abetris_osd_2.png – شاشة الإعدادات، abetris_osd_3.png – عرض السجل)*

## الشكر والتقدير

* **الأخ Ciefp** – على مشروع المرجع CiefpSettingsT2miAbertis: ثنائيات astra-sm
  الأصلية، أدوات `abertis` لكل المعماريات، ضبط T2-MI sysctl، والإعداد المرجعي.
* **الأخوان MOHAMED_OS / Levi45** – على تحديث مفاتيح أبيرتيس BISS باستمرار.
* **منتدى تونس-سات** – على مرجعية المعرفة والدعم.

## المصدر والدعم

* GitHub: https://github.com/prof-abdo/Abertis-Auto-Switcher-PRO
* الإصدارات: v1.9.13 (`.deb` لأجهزة DreamOS، `.ipk` لأجهزة OpenATV/OpenPLi)

---

**مُجرَّب وشغّال**: Dreambox Two 4K تحت DreamOS 2.6 (dpkg) وتحت openATV 8.0.1 /
opkg ببايثون 3.14 (وتعمل نسخة astra المعدَّلة مع المكتبة المرافقة
libcrypto.so.3): كل تغذيات أبيرتيس تُضبط تلقائياً – FTA + BISS + مرحلة التعلُّم
F1 – وتغذية PID 8008 متحقَّق منها بتزامن TS بنسبة 100%.

استمتعوا! 🙂

— أخوكم في الله Prof-Abdo (Kingcs)، حصرياً في منتدى تونس-سات
