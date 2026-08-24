# تشغيل محفظتي محلياً عبر Docker Compose

يشغّل الملف [`docker-compose.finance.local.yml`](../docker-compose.finance.local.yml) أربع خدمات متصلة: واجهة React على المنفذ `3000`، واجهة Django REST على المنفذ `8000`، وقاعدة PostgreSQL على المنفذ `5432`، وRedis لدعم إعدادات Django المحلية. لا يتطلب تشغيل واجهة محفظتي محلياً أي خدمة خارجية.

> يجب أن يكون المستودعان متجاورين داخل المجلد نفسه؛ أي أن يكون المسار `workspace/cms-backend` بجوار `workspace/p2`. هذا ضروري لأن Compose يبني حاوية الواجهة من `../p2`.

## التهيئة الأولى

ثبّت Docker Desktop على macOS أو Windows، أو Docker Engine مع إضافة Compose على Linux. بعد استنساخ فرعي `dev` من المستودعين، انسخ ملف البيئة المحلي داخل مستودع الخلفية:

```bash
cd cms-backend
cp .env.finance.local.example .env.finance.local
docker compose -f docker-compose.finance.local.yml up --build
```

تنتظر خدمة `api` جاهزية PostgreSQL وRedis، ثم تنفذ `python manage.py migrate --noinput` تلقائياً قبل تشغيل Django. افتح بعد ذلك [http://localhost:3000](http://localhost:3000). تتصل الواجهة من المتصفح بخدمة Django على `http://localhost:8000/api/v1`، ولذلك يبقى هذا العنوان بقيمة `VITE_FINANCE_API_URL` داخل حاوية الواجهة حتى لا يشير المتصفح إلى اسم خدمة Docker داخلي غير قابل للحل.

| عنوان محلي | الاستخدام |
|---|---|
| `http://localhost:3000` | واجهة محفظتي React/Vite. |
| `http://localhost:8000/health/` | فحص صحة Django. |
| `http://localhost:8000/accounts/signup/` | إنشاء حساب محلي. |
| `http://localhost:8000/accounts/login/` | تسجيل الدخول إلى Django. |
| `http://localhost:8000/api/v1/workspaces/current/` | نقطة مساحة العمل المحمية. |

لأن `DJANGO_ACCOUNT_EMAIL_VERIFICATION=none` مضبوط في ملف البيئة المحلي، يستطيع حساب محلي جديد تسجيل الدخول فوراً. في الإنتاج يجب إزالة هذا التجاوز واستخدام قيمة سرية لـ`SECRET_KEY` وكلمة مرور PostgreSQL مختلفة.

## الأوامر اليومية

استخدم `Ctrl+C` لإيقاف العرض الحي واترك البيانات محفوظة في volumes. لإعادة تشغيله في الخلفية، نفّذ:

```bash
docker compose -f docker-compose.finance.local.yml up -d
docker compose -f docker-compose.finance.local.yml logs -f api frontend
```

لتشغيل اختبارات الخلفية من الحاوية:

```bash
docker compose -f docker-compose.finance.local.yml exec api pytest apps/finance/tests/test_finance_api.py -q
```

ولإعادة إنشاء قاعدة التطوير من الصفر فقط عندما لا تحتاج البيانات المحلية:

```bash
docker compose -f docker-compose.finance.local.yml down -v
docker compose -f docker-compose.finance.local.yml up --build
```

## حدود ملف التشغيل المحلي

هذا الملف مخصص للتطوير، لا للنشر. فهو يربط مجلدات المصدر لتفعيل التحديث الحي ويكشف PostgreSQL على الجهاز المضيف لسهولة التشخيص. عند النشر، استخدم صورة Django الإنتاجية، لا تكشف منفذ قاعدة البيانات للعامة، واضبط `FRONTEND_BASE_URL` على نطاق الواجهة الفعلي كي تبقى قواعد CORS وCSRF مقيدة.
