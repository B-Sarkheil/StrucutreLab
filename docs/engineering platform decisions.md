# نرم‌افزار تجمیعی مهندسی (پایتون، ویندوز): تصمیم‌های معماری
 
## هدف
نرم‌افزار رسمی بخش مهندسی برای ۳۰ کاربر که به‌تدریج ابزارهای پراکنده‌ی MATLAB و VBA اکسل را تجمیع می‌کند. توسعه و تغییر زیاد خواهد بود.
 
## تصمیم‌ها
- نصب رسمی فقط یک بار، با Setup و توسط IT؛ محل نصب اولیه مهم نیست. آپدیت‌ها بدون IT و فقط در `%LocalAppData%\<AppName>\` (مثل NET).
- پایتون روی سیستم کاربر نصب نمی‌شود. Python embeddable و کتابخانه‌ها به‌صورت بسته‌ی zip/کپی فایل می‌آیند.
- سه لایه‌ی جدا:
  - **Bootstrap**: Python کوچک + `launcher.py` + میانبرها، نصب‌شده با Setup، تقریباً ثابت (قرارداد frozen).
  - **Runtime**: Python + کتابخانه‌ها (PySide6, numpy, ...)، در `runtime\<hash>\`، آپدیت گاهی.
  - **App**: کد برنامه، در `app\<version>\`، آپدیت مرتب.
- آپدیت: در هر اجرا `latest.json` سرور خوانده می‌شود (نسخه‌ی app و runtime، sha256، `min_bootstrap_version`). دانلود در temp، بررسی hash، extract، rename اتمیک، self-check، rollback خودکار، fail-open اگر سرور در دسترس نبود، لاگ best-effort روی سرور. فقط بخشی که تغییر کرده کپی می‌شود.
- نسخه‌ی سه‌بخشی (`packaging.version`)، کانال stable/beta، معماری plugin برای ابزارها.
- `latest.json` در `build.py` آخر از همه نوشته می‌شود تا نسخه‌ی نیمه‌منتشرشده دیده نشود.
## ابزار و کتابخانه‌ها
- GUI: PySide6 (احتمالاً PySide6-Essentials) + Fluent Widgets یا QML.
- ارتباط با ابزارها: pywin32/comtypes/xlwings، openpyxl، SAP2000 OAPI، MATLAB Runtime به‌صورت subprocess و پورت تدریجی.
- داده و محاسبات: numpy, scipy, pandas/polars, matplotlib/pyqtgraph, sqlite/Parquet.
- زیرساخت: pydantic, platformdirs, packaging, logging؛ تست و کیفیت: pytest, pytest-qt, ruff, mypy.
- ساخت: `uv` برای runtime با lockfile، Inno Setup برای Setup.exe (قابل `/VERYSILENT` برای IT؛ در صورت نیاز IT، MSI با WiX).
- توسعه با VSCode: افزونه‌های Python, Pylance, Ruff, Qt for Python, GitLens؛ Git از ابتدا.
## وضعیت پاسخ‌های IT
- exeها در شرکت اجرا می‌شوند. امضای دیجیتال فعلاً مهم نیست (حفاظت از نرم‌افزار در پایان کار با روش دیگری انجام می‌شود).
- دسترسی خواندن سرور وجود دارد. حساسیت آنتی‌ویروس بعید است و در prototype تست می‌شود.
- هنوز پرسیده نشده: نوشتن روی share سرور فقط Write Data است یا نه (برای انتشار)، و AppLocker روی `.pyd`/`.dll` در AppData.