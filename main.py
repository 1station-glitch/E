import os
import json
import random
import requests
import time
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ======================================================
# 🌍 1. إعدادات البيئة (GitHub vs Local)
# ======================================================
IS_GITHUB = "GITHUB_ACTIONS" in os.environ

# إعدادات Telegram
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') # تأكد أن هذا المتغير موجود في Secrets أو Environment
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# دالة الإشعار
def notify(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ إعدادات تليقرام غير موجودة!")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
        )
    except Exception as e:
        print(f"⚠️ فشل إرسال تليقرام: {e}")

# ======================================================
# 🔐 2. إعداد Firebase (ذكي وهجين)
# ======================================================
if not firebase_admin._apps:
    try:
        if IS_GITHUB:
            print("🤖 البيئة: GitHub Actions")
            # في GitHub: نقرأ محتوى ملف JSON من Secret اسمه FIREBASE_JSON
            firebase_config = os.environ.get("FIREBASE_JSON")
            if not firebase_config:
                raise ValueError("لم يتم العثور على FIREBASE_JSON في Secrets!")
            cred_info = json.loads(firebase_config)
            cred = credentials.Certificate(cred_info)
        else:
            print("💻 البيئة: جهاز محلي")
            # في جهازك: نقرأ الملف مباشرة (تأكد أن اسمه serviceAccountKey.json)
            # أو ضع مسار ملفك هنا
            local_file = "firebase_credinalt.json" 
            if os.path.exists(local_file):
                cred = credentials.Certificate(local_file)
            else:
                # خيار بديل لو الملف له اسم ثاني
                cred = credentials.Certificate("firebase_credentials.json") 
        
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ تم الاتصال بقاعدة البيانات بنجاح.")
    except Exception as e:
        print(f"❌ خطأ في إعداد Firebase: {e}")
        exit(1)
else:
    db = firestore.client()

# ======================================================
# 🛠️ 3. دوال مساعدة
# ======================================================
def clean_text(text):
    if not text: return ""
    return str(text).replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ة","ه").replace("ي","ى").strip()

# ======================================================
# 🚀 4. المحرك الرئيسي
# ======================================================
def process_orders():
    print("🔄 جلب الطلبات (pending)...")
    docs = db.collection("orders").where("status", "==", "pending").stream()
    docs_list = list(docs)

    if not docs_list:
        print("😴 لا توجد طلبات جديدة.")
        return

    print(f"📦 وجدنا {len(docs_list)} طلبات.")
    
    # لتجنب تكرار كود الفرع
    used_codes = set()

    for doc in docs_list:
        try:
            order = doc.to_dict()
            doc_ref = db.collection("orders").document(doc.id)

            # استخراج البيانات
            store_name = order.get("store_name", "").strip()
            receiver_name = order.get("receiver_name", "").strip()
            receiver_phone = order.get("receiver_phone", "").strip()
            city = order.get("city", "").strip()
            region = order.get("region", "").strip()
            district = order.get("district", "").strip()
            street = order.get("street", "").strip()
            district_street = f"{district} - {street}"

            # توليد كود فرع فريد
            while True:
                branch_code = str(random.randint(10000, 99999))
                if branch_code not in used_codes:
                    used_codes.add(branch_code)
                    break

            # 📩 إرسال إشعار البدء
            start_msg = (
                f"🚨 <b>متجر جديد:</b> {store_name}\n"
                f"📱 <b>الرقم:</b> {receiver_phone}\n"
                f"📍 <b>المدينة - المنطقة:</b> {city} - {region}\n"
                f"🏘️ <b>الحي - الشارع:</b> {district_street}"
            )
            notify(start_msg)

            # تشغيل Playwright
            with sync_playwright() as p:
                # في GitHub نستخدم headless=True اجباري، في المحلي اختياري
                browser = p.chromium.launch(headless=True) 
                # إعداد حجم الشاشة لتجنب مشاكل العناصر المخفية
                context = browser.new_context(viewport={'width': 1280, 'height': 800})
                page = context.new_page()

                # 1️⃣ تسجيل الدخول
                print(f"🔐 تسجيل الدخول للمتجر: {store_name}")
                page.goto("https://torod.co/ar/login", timeout=60000)
                page.wait_for_selector("input[type='email']")
                page.locator("input[type='email']").fill("kook53281@gmail.com")
                page.locator("input[type='password']").fill("Abcd_0504989381")
                page.locator("button[type='submit']").click()
                page.wait_for_url("**/dashboard", timeout=60000)

                # 2️⃣ صفحة العنوان
                page.goto("https://torod.co/ar/settings/address")
                page.wait_for_selector("a[href*='address/create']", state="visible")
                page.locator("a[href*='address/create']").click()

                # 3️⃣ تعبئة البيانات الأساسية
                print("📝 تعبئة البيانات...")
                page.locator("#merchant_address_form_name").fill(store_name)
                page.locator("#merchant_address_form_title").fill(branch_code)
                page.locator("#merchant_address_form_contact_name").fill(receiver_name)
                page.locator("#merchant_address_form_email").fill("noon53281@gmail.com")
                page.locator("#merchant_address_form_phone_number").fill(receiver_phone)

                # ---------------------------------------------------------
                # 🏙️ 4️⃣ معالجة المدينة (Select2 Logic)
                # ---------------------------------------------------------
                print(f"🔍 البحث عن المدينة: {city}")
                try:
                    BTN_CLICK   = "#select2-merchant_address_form_city-container"
                    INPUT_FIELD = ".select2-search__field"
                    RESULTS_BOX = "#select2-merchant_address_form_city-results"

                    page.locator(BTN_CLICK).click(force=True)
                    page.locator(INPUT_FIELD).fill("") 
                    page.locator(INPUT_FIELD).type(city, delay=100) # كتابة بطيئة
                    
                    print("   ⏳ انتظار 5 ثواني للنتائج...")
                    page.wait_for_timeout(5000)

                    results_container = page.locator(RESULTS_BOX)
                    options = results_container.locator("li").all()

                    found = False
                    target_city = clean_text(city)
                    target_region = clean_text(region)

                    if options:
                        for opt in options:
                            txt = opt.inner_text()
                            clean_txt = clean_text(txt)
                            
                            # تطابق: المدينة + المنطقة
                            if target_city in clean_txt and target_region in clean_txt:
                                print(f"      ✅ تطابق كامل: {txt}")
                                opt.click()
                                found = True
                                break
                        
                        # خطة ب: المدينة فقط
                        if not found:
                            for opt in options:
                                if target_city in clean_text(opt.inner_text()):
                                    print(f"      ⚠️ تطابق مدينة فقط: {opt.inner_text()}")
                                    opt.click()
                                    found = True
                                    break
                        
                        # خطة ج: أول خيار عشوائي
                        if not found:
                             print("      🎲 اختيار أول نتيجة متاحة.")
                             options[0].click()
                    else:
                        print("❌ القائمة فارغة!")

                except Exception as e:
                    print(f"❌ خطأ في القائمة: {e}")
                    try: page.mouse.click(0,0)
                    except: pass
                
                # إغلاق الخريطة وتكملة العنوان
                if page.locator("#merchant_address_form_google_map_toggle").is_visible():
                     if page.locator("#merchant_address_form_google_map_toggle").is_checked():
                        page.locator("#merchant_address_form_google_map_toggle").click(force=True)
                
                page.locator("#merchant_address_form_address_details").fill(district_street)

                # ---------------------------------------------------------
                # 🏁 5️⃣ الحفظ والتحقق (Check Modal Hidden)
                # ---------------------------------------------------------
                print("💾 حفظ...")
                page.locator("#address_form_btn").click()

                try:
                    # الانتظار حتى تختفي النافذة المنبثقة (بحد أقصى دقيقة)
                    page.wait_for_selector("#exampleModal", state="hidden", timeout=60000)
                    
                    # ✅ نجاح
                    doc_ref.update({"status": "done"})
                    notify(f"✅ <b>تمت الإضافة بنجاح</b>\nالمتجر: {store_name}")
                    print("✅ النتيجة: نجاح.")

                except:
                    # ❌ فشل (النافذة ما زالت موجودة)
                    notify(f"❌ <b>لم تتم الإضافة (رفض الموقع)</b>\nالمتجر: {store_name}")
                    print("❌ النتيجة: فشل.")

                browser.close()

        except Exception as e:
            print(f"❌ خطأ عام في الطلب: {e}")
            notify(f"❌ خطأ فني: {e}")

if __name__ == "__main__":
    process_orders()
