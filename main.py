import os
import random
import requests
import re
import time
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ==========================================
# ⚙️ إعدادات المستخدم
# ==========================================
BOT_TOKEN = "8224827964:AAGpO4HKau6MDDOHPxyBC0Lkp9hiGYCfS3M" 
CHAT_ID = "5278948260"
FIREBASE_KEY_FILE = "firebase_credinalt.json"
# ==========================================

# 1️⃣ الاتصال بـ Firebase
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(FIREBASE_KEY_FILE)
        firebase_admin.initialize_app(cred)
        print("✅ تم الاتصال بقاعدة بيانات Firebase بنجاح.")
    except FileNotFoundError:
        print(f"❌ خطأ: لم يتم العثور على ملف {FIREBASE_KEY_FILE}")
        print("تأكد أن الملف موجود في نفس المجلد مع الكود.")
        exit()

db = firestore.client()

# 2️⃣ دالة إرسال تلقرام
def notify(msg):
    if BOT_TOKEN == "ضع_توكن_بوت_تلقرام_هنا":
        print(f"⚠️ تنبيه محلي: {msg}")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg}
        )
    except Exception as e:
        print("خطأ في إرسال Telegram:", e)

# 3️⃣ دالة المساعدة في المقارنة فقط (لا تغير النص الأصلي)
def normalize_arabic(text):
    if not text: return ""
    text = str(text)
    # هذا التنظيف للمقارنة فقط عشان يلقى المدينة في القائمة
    text = re.sub(r'[\u064B-\u065F\u0640]', '', text) 
    text = re.sub(r'[أإآ]', 'ا', text) 
    text = re.sub(r'ة', 'ه', text) 
    text = re.sub(r'\bال', '', text) 
    return text.strip()

# ==========================================
# 🚀 بداية تشغيل البوت
# ==========================================

print("🔄 جاري البحث عن طلبات 'pending'...")
docs = db.collection("orders").where("status", "==", "pending").stream()
docs_list = list(docs)

if not docs_list:
    print("😴 لا توجد طلبات معلقة (Pending) حالياً.")
else:
    print(f"📦 تم العثور على {len(docs_list)} طلب/طلبات.")

used_codes = set()

for doc in docs_list:
    order = doc.to_dict()
    doc_ref = db.collection("orders").document(doc.id)

    # ==== جمع البيانات (بدون تعديل أو تنظيف) ====
    # نستخدم strip() فقط لإزالة المسافات الزائدة أول وآخر الكلام إن وجدت
    store_name = order.get("store_name", "").strip()
    receiver_name = order.get("receiver_name", "").strip()
    receiver_phone = order.get("receiver_phone", "").strip()
    
    # البيانات كما هي من الفايربيس
    city = order.get("city", "").strip()
    region = order.get("region", "").strip()
    city_region = f"{city} - {region}"
    
    district = order.get("district", "").strip()
    street = order.get("street", "").strip()
    district_street = f"{district} - {street}" 

    # توليد رمز فرع
    while True:
        branch_code = str(random.randint(10000, 99999))
        if branch_code not in used_codes:
            used_codes.add(branch_code)
            break

    notify(f"📦 بدء تنفيذ طلب:\nمستودع: {store_name}\nمدينة: {city_region}")

    try:
        with sync_playwright() as p:
            print("🌐 فتح المتصفح...")
            browser = p.chromium.launch(headless=False, slow_mo=500) 
            page = browser.new_page()

            # تسجيل الدخول
            print(f"🔐 تسجيل دخول للمتجر: {store_name}")
            page.goto("https://demo.stage.torod.co/ar/login")
            
            page.get_by_role("textbox", name="أدخل البريد الإلكتروني").fill("kook53281@gmail.com")
            page.get_by_role("textbox", name="Password").fill("Abcd_0504989381")
            page.get_by_role("button", name="تسجيل دخول").click()
            
            page.wait_for_url("**/dashboard", timeout=60000)
            print("✅ تم الدخول.")

            # الانتقال لصفحة العناوين
            page.goto("https://demo.stage.torod.co/ar/settings/address")
            page.get_by_role("link", name="+ عنوان جديد").click()

            # تعبئة البيانات (تعبئة المتغيرات الخام كما هي)
            page.get_by_role("textbox", name="اسم المستودع *").fill(store_name)
            page.get_by_role("textbox", name="رمز الفرع او المستودع").fill(branch_code)
            page.get_by_role("textbox", name="مسؤول الإتصال *").fill(receiver_name)
            page.get_by_role("textbox", name="أدخل البريد الإلكتروني").fill("noon53281@gmail.com")
            page.get_by_placeholder("أدخل رقم الجوال").fill(receiver_phone)

            # معالجة المدينة
            match_success = False
            try:
                page.locator("#select2-merchant_address_form_city-container").click()
                # نكتب اسم المدينة كما هو من الفايربيس
                page.get_by_role("searchbox").fill(city)
                page.wait_for_timeout(2000)

                options = page.locator("li[role='option']").all()
                
                # نستخدم التطبيع فقط للمقارنة لإيجاد الخيار الصحيح
                target_norm = normalize_arabic(city_region)

                for opt in options:
                    opt_text = opt.inner_text()
                    if target_norm in normalize_arabic(opt_text):
                        opt.click()
                        match_success = True
                        break
                
                if not match_success:
                    # محاولة ثانية
                    city_norm = normalize_arabic(city)
                    for opt in options:
                        if city_norm in normalize_arabic(opt.inner_text()):
                            opt.click()
                            match_success = True
                            break
                            
            except Exception as e:
                print(f"⚠️ مشكلة في قائمة المدن: {e}")

            if not match_success:
                print(f"⚠️ لم يتم العثور على المدينة بدقة: {city}")

            # إكمال وتأكيد
            if page.locator("#merchant_address_form_google_map_toggle").is_checked():
                page.locator("#merchant_address_form_google_map_toggle").uncheck()
                
            page.get_by_role("textbox", name="تفاصيل العنوان").fill(district_street)

            # مراجعة سريعة
            try:
                chk_store = page.locator("#merchant_address_form_name").input_value()
                print(f"👀 مراجعة سريعة: المتجر المدخل هو {chk_store}")
            except:
                pass

            # حفظ
            print("💾 جاري الحفظ...")
            page.get_by_role("button", name="إرسال").click()
            page.wait_for_timeout(4000)

            browser.close()

        # تحديث الحالة
        doc_ref.update({"status": "done"})
        print(f"✅ انتهى الطلب: {store_name}")
        notify(f"✅ تم التنفيذ: {store_name}")

    except PlaywrightTimeoutError as e:
        print(f"⏳ انتهى الوقت (Timeout): {e}")
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")

print("🏁 انتهى تشغيل البرنامج.")
