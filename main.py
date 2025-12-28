import os
import random
import requests
import time
import json
import firebase_admin
from difflib import SequenceMatcher
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ==========================================
# 🌍 كشف البيئة (هل أنا في GitHub أم جهازي؟)
# ==========================================
# GitHub يضيف تلقائياً متغير اسمه GITHUB_ACTIONS
IS_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"

if IS_GITHUB:
    print("🤖 البيئة المكتشفة: GitHub Actions (سحابي)")
    HEADLESS_MODE = True
    SLOW_MO = 0 # سرعة قصوى في السيرفر
else:
    print("💻 البيئة المكتشفة: Local Machine (جهازك)")
    HEADLESS_MODE = False
    SLOW_MO = 500 # بطيء عشان تشوف بعينك

# ==========================================
# 🔐 إعدادات المصادقة (Auth)
# ==========================================
BOT_TOKEN = "8224827964:AAGpO4HKau6MDDOHPxyBC0Lkp9hiGYCfS3M" 
CHAT_ID = "5278948260"
FIREBASE_FILENAME = "firebase_credinalt.json"

if not firebase_admin._apps:
    try:
        cred = None
        
        if IS_GITHUB:
            # في قيت هوب: نقرأ المفتاح من النصوص السرية (Secrets)
            # يجب أن تضيف سيكرت باسم FIREBASE_KEY_JSON يحتوي على محتوى الملف
            json_str = os.getenv("FIREBASE_KEY_JSON")
            if not json_str:
                raise ValueError("⚠️ لم يتم العثور على Secret باسم FIREBASE_KEY_JSON في إعدادات GitHub")
            
            cred_dict = json.loads(json_str)
            cred = credentials.Certificate(cred_dict)
            print("✅ تم تحميل مفتاح Firebase من Secrets بنجاح.")
            
        else:
            # في الجهاز: نقرأ الملف مباشرة
            if os.path.exists(FIREBASE_FILENAME):
                cred = credentials.Certificate(FIREBASE_FILENAME)
                print(f"✅ تم تحميل مفتاح Firebase من الملف المحلي: {FIREBASE_FILENAME}")
            else:
                raise FileNotFoundError(f"❌ لم يتم العثور على الملف: {FIREBASE_FILENAME}")

        firebase_admin.initialize_app(cred)
        
    except Exception as e:
        print(f"❌ خطأ فادح في الاتصال بـ Firebase: {e}")
        exit()

db = firestore.client()

# ==========================================
# 🛠️ الدوال المساعدة
# ==========================================
def notify(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg}
        )
    except: pass

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

# ==========================================
# 🚀 تشغيل البوت
# ==========================================

print("🔄 جاري البحث عن طلبات 'pending'...")
docs = db.collection("orders").where("status", "==", "pending").stream()
docs_list = list(docs)

if not docs_list:
    print("😴 لا توجد طلبات.")
else:
    print(f"📦 جاري معالجة {len(docs_list)} طلب...")

used_codes = set()

for doc in docs_list:
    order = doc.to_dict()
    doc_ref = db.collection("orders").document(doc.id)

    # بيانات خام
    store_name = order.get("store_name", "").strip()
    receiver_name = order.get("receiver_name", "").strip()
    receiver_phone = order.get("receiver_phone", "").strip()
    city = order.get("city", "").strip()
    region = order.get("region", "").strip()
    district = order.get("district", "").strip()
    street = order.get("street", "").strip()
    district_street = f"{district} - {street}" 

    while True:
        branch_code = str(random.randint(10000, 99999))
        if branch_code not in used_codes:
            used_codes.add(branch_code)
            break

    notify(f"📦 [Bot] طلب جديد: {store_name}\n📍 {city} - {region}")

    try:
        with sync_playwright() as p:
            print("🌐 تشغيل المتصفح...")
            # هنا التبديل الذكي حسب البيئة
            browser = p.chromium.launch(headless=HEADLESS_MODE, slow_mo=SLOW_MO)
            page = browser.new_page()

            # تسجيل الدخول
            page.goto("https://demo.stage.torod.co/ar/login")
            page.get_by_role("textbox", name="أدخل البريد الإلكتروني").fill("kook53281@gmail.com")
            page.get_by_role("textbox", name="Password").fill("Abcd_0504989381")
            page.get_by_role("button", name="تسجيل دخول").click()
            page.wait_for_url("**/dashboard", timeout=60000)

            # الانتقال وإدخال البيانات
            page.goto("https://demo.stage.torod.co/ar/settings/address")
            page.get_by_role("link", name="+ عنوان جديد").click()

            page.get_by_role("textbox", name="اسم المستودع *").fill(store_name)
            page.get_by_role("textbox", name="رمز الفرع او المستودع").fill(branch_code)
            page.get_by_role("textbox", name="مسؤول الإتصال *").fill(receiver_name)
            page.get_by_role("textbox", name="أدخل البريد الإلكتروني").fill("noon53281@gmail.com")
            page.get_by_placeholder("أدخل رقم الجوال").fill(receiver_phone)

            # --- منطق البحث الذكي ---
            match_success = False
            try:
                page.locator("#select2-merchant_address_form_city-container").click()
                page.get_by_role("searchbox").fill(city) # كتابة المدينة 100%
                page.wait_for_timeout(2000)

                options = page.locator("li[role='option']").all()
                
                # 1. بحث دقيق
                for opt in options:
                    if region in opt.inner_text():
                        print(f"✅ تطابق دقيق: {opt.inner_text()}")
                        opt.click()
                        match_success = True
                        break
                
                # 2. بحث تقريبي (اذا فشل الدقيق)
                if not match_success:
                    best_match_ratio = 0
                    best_option = None
                    for opt in options:
                        ratio = similar(region, opt.inner_text())
                        if ratio > best_match_ratio:
                            best_match_ratio = ratio
                            best_option = opt
                    
                    if best_match_ratio >= 0.7:
                        print(f"✅ تطابق تقريبي ({int(best_match_ratio*100)}%): {best_option.inner_text()}")
                        best_option.click()
                        match_success = True

                # 3. مدينة فقط (اذا فشل الكل)
                if not match_success:
                    for opt in options:
                        if city in opt.inner_text():
                            opt.click()
                            match_success = True
                            break
                            
            except Exception as e:
                print(f"⚠️ خطأ: {e}")

            # إكمال
            if page.locator("#merchant_address_form_google_map_toggle").is_checked():
                page.locator("#merchant_address_form_google_map_toggle").uncheck()
            page.get_by_role("textbox", name="تفاصيل العنوان").fill(district_street)

            # حفظ
            page.get_by_role("button", name="إرسال").click()
            page.wait_for_timeout(4000)
            browser.close()

        # إنهاء
        doc_ref.update({"status": "done"})
        print(f"✅ تم: {store_name}")
        notify(f"✅ تم التنفيذ: {store_name}")

    except Exception as e:
        print(f"❌ خطأ: {e}")
        notify(f"⚠️ خطأ في {store_name}: {e}")

print("🏁 انتهى.")
