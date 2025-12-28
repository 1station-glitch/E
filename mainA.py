import os
import json
import tempfile
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ==== إعداد Firebase ====
firebase_json = os.environ['FIREBASE_JSON']
with tempfile.NamedTemporaryFile(mode='w+', delete=False) as f:
    f.write(firebase_json)
    firebase_file = f.name

cred = credentials.Certificate(firebase_file)
firebase_admin.initialize_app(cred)
db = firestore.client()

# ==== إعداد Telegram ====
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

# ==== تنظيف النصوص للمدينة والمنطقة ====
def clean_text(text):
    text = text.strip()
    text = text.replace("ة", "ه")
    if text.startswith("ال"):
        text = text[2:]
    return text

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
    district_street = f"{district} - {street}"  # صيغة الحي - الشارع

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
           f"الهاتف: {receiver_phone}\n"
           f"المدينة/المنطقة: {city_region}\n"
           f"الحي/الشارع: {district_street}\n"
           f"رمز الفرع: {branch_code}\n"
           f"الحالة: {order.get('status', '')}")

    # ==== بدء Playwright ====
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)  # False لتشوف المتصفح أثناء التجربة
            page = browser.new_page()

            # 1️⃣ تسجيل الدخول
            page.goto("https://demo.stage.torod.co/ar/login")
            page.fill('/html/body/div[2]/div/div/form/p[1]', "kook53281@gmail.com")
            page.fill('/html/body/div[2]/div/div/form/p[2]', "Abcd_0504989381")
            page.click('/html/body/div[2]/div/div/form/p[4]')
            page.wait_for_timeout(2000)  # انتظار تسجيل الدخول

            # 2️⃣ الانتقال لصفحة العنوان والضغط على زر إضافة عنوان جديد
            page.goto("https://demo.stage.torod.co/ar/settings/address")
            page.click('//*[@id="ga4-addressesDiv"]/div/div/div[2]')
            page.wait_for_timeout(2000)  # انتظار ظهور الخانات

            # 3️⃣ تعبئة البيانات
            page.fill('//*[@id="merchant_address_form_name"]', store_name)
            page.fill('//*[@id="merchant_address_form_contact_name"]', receiver_name)
            page.fill('//*[@id="merchant_address_form_phone_number"]', receiver_phone)

            # المدينة + المنطقة
            page.click('//*[@id="select2-merchant_address_form_city-container"]')
            page.fill('//*[@id="select2-merchant_address_form_city-container"]', city)
            page.wait_for_timeout(1000)
            options = page.query_selector_all('//*[@id="select2-merchant_address_form_city-results"]/li')
            matched = None
            for opt in options:
                text = opt.inner_text().strip()
                if city_region in text:
                    matched = opt
                    break
            if matched:
                matched.click()
            else:
                print("لم يتم العثور على المدينة/المنطقة:", city_region)

            # الضغط على زر Google Map
            page.click('//*[@id="merchant_address_form_google_map_toggle"]')

            # الحي + الشارع
            page.fill('//*[@id="merchant_address_form_address_details"]', district_street)

            # البريد الإلكتروني ثابت
            page.fill('//*[@id="merchant_address_form_email"]', "noon53281@gmail.com")

            # رمز الفرع عشوائي
            page.fill('//*[@id="merchant_address_form_title"]', branch_code)

            # الضغط على زر الحفظ / الإرسال
            page.click('//*[@id="address_form_btn"]')

            browser.close()

        # ==== تحديث الحالة بعد التنفيذ ====
        doc_ref.update({"status": "done"})
        notify(f"✅ تم تنفيذ الطلب بنجاح: {store_name} ({city_region})")

    except PlaywrightTimeoutError as e:
        notify(f"⚠️ خطأ أثناء تنفيذ الطلب {store_name}: {e}")
        print("Playwright TimeoutError:", e)
    except Exception as e:
        notify(f"⚠️ خطأ غير متوقع للطلب {store_name}: {e}")
        print("خطأ:", e)
