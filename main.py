import os
import json
import tempfile
import random
import requests
import re  # 🟢 إضافة مكتبة re لمعالجة النصوص
import time
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ==== إعداد Firebase (من الملف الأول - لا تغيير) ====
firebase_json = os.environ['FIREBASE_JSON']
with tempfile.NamedTemporaryFile(mode='w+', delete=False) as f:
    f.write(firebase_json)
    firebase_file = f.name

cred = credentials.Certificate(firebase_file)
firebase_admin.initialize_app(cred)
db = firestore.client()

# ==== إعداد Telegram (من الملف الأول - لا تغيير) ====
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

def notify(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg}
        )
    except Exception as e:
        print("خطأ في إرسال Telegram:", e)

# ==== دوال مساعدة (دمجنا normalize_arabic هنا) ====
def clean_text(text):
    text = text.strip()
    text = text.replace("ة", "ه")
    if text.startswith("ال"):
        text = text[2:]
    return text

def normalize_arabic(text):
    """تنظيف النصوص العربية للمطابقة الذكية (من الملف الثاني)"""
    if not text: return ""
    text = str(text)
    text = re.sub(r'[\u064B-\u065F\u0640]', '', text) # تشكيل
    text = re.sub(r'[أإآ]', 'ا', text) # ألف
    text = re.sub(r'ة', 'ه', text) # تاء مربوطة
    text = re.sub(r'\bال', '', text) # ال التعريف
    return text.strip()

# ==== جلب الطلبات pending فقط ====
docs = db.collection("orders").where("status", "==", "pending").stream()

# لتخزين الرموز العشوائية المستخدمة
used_codes = set()

for doc in docs:
    order = doc.to_dict()
    doc_ref = db.collection("orders").document(doc.id)

    # جمع البيانات
    store_name = order.get("store_name", "")
    receiver_name = order.get("receiver_name", "")
    receiver_phone = order.get("receiver_phone", "")
    
    city = clean_text(order.get("city", ""))
    region = clean_text(order.get("region", ""))
    city_region = f"{city} - {region}"
    
    district = order.get("district", "")
    street = order.get("street", "")
    district_street = f"{district} - {street}" 

    # توليد رمز عشوائي جديد لكل طلب
    while True:
        branch_code = str(random.randint(10000, 99999))
        if branch_code not in used_codes:
            used_codes.add(branch_code)
            break

    # إشعار Telegram قبل التنفيذ
    notify(f"📦 بدء تنفيذ طلب جديد:\n"
           f"المستودع: {store_name}\n"
           f"المسؤول: {receiver_name}\n"
           f"المدينة: {city_region}\n"
           f"رمز الفرع: {branch_code}")

    # ==== بدء Playwright (تم استبدال المنطق هنا بكود mainB) ====
    try:
        with sync_playwright() as p:
            # ⚠️ هام: headless=True عشان GitHub Actions
            browser = p.chromium.launch(headless=True) 
            page = browser.new_page()

            # 1️⃣ تسجيل الدخول (باستخدام محددات mainB الذكية)
            # ملاحظة: أبقيت رابط demo كما هو في الملف الأول
            print(f"🔐 جاري الدخول للطلب: {store_name}")
            page.goto("https://demo.stage.torod.co/ar/login")
            
            # استخدام get_by_role بدلاً من XPath (أكثر دقة)
            page.get_by_role("textbox", name="أدخل البريد الإلكتروني").fill("kook53281@gmail.com")
            page.get_by_role("textbox", name="Password").fill("Abcd_0504989381")
            page.get_by_role("button", name="تسجيل دخول").click()
            
            # انتظار الدخول
            page.wait_for_url("**/dashboard", timeout=60000)

            # ==== 🛑 بداية كود الفحص 🛑 ====
            print(f"📍 الرابط الحالي: {page.url}")
            page.screenshot(path="debug_status.png") 
            
            if "login" in page.url:
                print("❌ البوت ما زال في صفحة الدخول! (لم ينجح الدخول)")
            elif "create" in page.url or "address" in page.url:
                print("✅ البوت وصل لصفحة العنوان بنجاح!")
            else:
                print("⚠️ البوت في صفحة غير متوقعة!")
            # ==== 🛑 نهاية كود الفحص 🛑 ====
            # 2️⃣ الانتقال لصفحة العناوين
            page.goto("https://demo.stage.torod.co/ar/settings/address")
            page.get_by_role("link", name="+ عنوان جديد").click()

            # 3️⃣ تعبئة البيانات (كود mainB)
            # دمجنا متغيرات الملف الأول مع طريقة إدخال الملف الثاني
            page.get_by_role("textbox", name="اسم المستودع *").fill(store_name)
            page.get_by_role("textbox", name="رمز الفرع او المستودع").fill(branch_code)
            page.get_by_role("textbox", name="مسؤول الإتصال *").fill(receiver_name)
            page.get_by_role("textbox", name="أدخل البريد الإلكتروني").fill("noon53281@gmail.com")
            page.get_by_placeholder("أدخل رقم الجوال").fill(receiver_phone)

            # --- التعامل مع المدينة (منطق mainB الذكي) ---
            match_success = False
            try:
                page.locator("#select2-merchant_address_form_city-container").click()
                page.get_by_role("searchbox").fill(city)
                page.wait_for_timeout(1500)

                options = page.locator("li[role='option']").all()
                target_norm = normalize_arabic(city_region)

                # محاولة المطابقة الأولى
                for opt in options:
                    opt_text = opt.inner_text()
                    if target_norm in normalize_arabic(opt_text) or normalize_arabic(opt_text) in target_norm:
                        opt.click()
                        match_success = True
                        break
                
                # محاولة ثانية بالمدينة فقط إذا فشلت الأولى
                if not match_success:
                    city_norm = normalize_arabic(city)
                    for opt in options:
                        if city_norm in normalize_arabic(opt.inner_text()):
                            opt.click()
                            match_success = True
                            break
                            
            except Exception as e:
                print(f"خطأ في تحديد المدينة: {e}")

            if not match_success:
                print(f"⚠️ لم يتم العثور على مدينة مطابقة لـ: {city}")
                # هنا ممكن تختار خيار افتراضي أو تكمل، سأتركه يكمل لكي لا يتوقف البوت

            # إكمال وتأكيد (Google Map والتفاصيل)
            page.locator("#merchant_address_form_google_map_toggle").uncheck()
            page.get_by_role("textbox", name="تفاصيل العنوان").fill(district_street)

            # الضغط على إرسال
            page.get_by_role("button", name="إرسال").click()
            
            # انتظار قليل للتأكد من الحفظ
            page.wait_for_timeout(3000)

            browser.close()

        # ==== تحديث الحالة بعد التنفيذ ====
        doc_ref.update({"status": "done"})
        notify(f"✅ تم تنفيذ الطلب بنجاح: {store_name} ({city_region})")

    except PlaywrightTimeoutError as e:
        notify(f"⚠️ Timeout Error للطلب {store_name}: {e}")
        print("Playwright TimeoutError:", e)
    except Exception as e:
        notify(f"⚠️ خطأ غير متوقع للطلب {store_name}: {e}")
        print("Error:", e)
