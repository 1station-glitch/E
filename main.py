import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright
import time
import random
import re
import requests # مكتبة لإرسال رسائل تليقرام

# ======================================================
# ⚙️ إعدادات التليقرام (عدلها هنا)
# ======================================================
TELEGRAM_TOKEN = "8224827964:AAGpO4HKau6MDDOHPxyBC0Lkp9hiGYCfS3M" 
TELEGRAM_CHAT_ID = "5278948260"

def send_telegram_msg(message):
    """دالة لإرسال إشعار إلى تليقرام"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML" # عشان تقدر ترسل نصوص عريضة أو مائلة
        }
        requests.post(url, data=payload)
    except Exception as e:
        print(f"⚠️ فشل إرسال رسالة تليقرام: {e}")

# ======================================================
# 🔥 أدوات ذكية (Firebase + معالجة النصوص)
# ======================================================

def init_firebase():
    if not firebase_admin._apps:
        # 1. التحقق أولاً: هل الملف موجود بجانب الكود؟ (للعمل المحلي على جهازك)
        if os.path.exists("serviceAccountKey.json"):
            print("📂 جاري استخدام ملف serviceAccountKey.json المحلي...")
            cred = credentials.Certificate("serviceAccountKey.json")
            
        # 2. التحقق ثانياً: هل نحن في GitHub ونستخدم المتغيرات؟
        elif os.environ.get("FIREBASE_CREDENTIALS"):
            print("🔐 جاري استخدام مفاتيح GitHub Secret...")
            cred_dict = json.loads(os.environ.get("FIREBASE_CREDENTIALS"))
            cred = credentials.Certificate(cred_dict)
            
        # 3. إذا لم نجد أياً منهما
        else:
            raise ValueError("❌ خطأ: لم يتم العثور على ملف serviceAccountKey.json ولا مفاتيح GitHub!")

        firebase_admin.initialize_app(cred)
    return firestore.client()

def normalize_arabic(text):
    """تنظيف النصوص العربية للمطابقة الذكية"""
    if not text: return ""
    text = str(text)
    text = re.sub(r'[\u064B-\u065F\u0640]', '', text) # تشكيل
    text = re.sub(r'[أإآ]', 'ا', text) # ألف
    text = re.sub(r'ة', 'ه', text) # تاء مربوطة
    text = re.sub(r'\bال', '', text) # ال التعريف
    return text.strip()

# ======================================================
# 🔐 تسجيل الدخول
# ======================================================
def login_to_torod(page):
    print("🔐 جاري تسجيل الدخول...")
    page.goto("https://torod.co/ar/login")
    
    page.get_by_role("textbox", name="أدخل البريد الإلكتروني").fill("kook53281@gmail.com")
    page.get_by_role("textbox", name="Password").fill("Abcd_0504989381")
    page.get_by_role("button", name="تسجيل دخول").click()
    
    try:
        page.wait_for_url("**/dashboard", timeout=60000)
        print("✅ تم الدخول بنجاح.")
        send_telegram_msg("🚀 <b>بدأ البوت العمل!</b>\nتم تسجيل الدخول بنجاح.")
        return True
    except:
        print("❌ فشل الدخول.")
        send_telegram_msg("❌ <b>تنبيه:</b> فشل البوت في تسجيل الدخول!")
        return False

# ======================================================
# 📦 معالجة الطلب الواحد
# ======================================================
def process_single_order(page, order_data, order_id):
    # استقبال البيانات
    r_name = order_data.get('receiver_name', 'عميل')
    r_phone = order_data.get('receiver_phone', '')
    city = order_data.get('city', '')
    region = order_data.get('region', '')
    full_address = f"{order_data.get('district', '')} - {order_data.get('street', '')}"

    print(f"   >>> معالجة: {r_name} | {city}")

    # الانتقال لصفحة العناوين
    page.goto("https://torod.co/ar/settings/address")
    page.get_by_role("link", name="+ عنوان جديد").click()

    # تعبئة البيانات
    unique_code = f"{int(time.time())}_{random.randint(1, 99)}"
    page.get_by_role("textbox", name="اسم المستودع *").fill(r_name)
    page.get_by_role("textbox", name="رمز الفرع او المستودع").fill(unique_code)
    page.get_by_role("textbox", name="مسؤول الإتصال *").fill(r_name)
    page.get_by_role("textbox", name="أدخل البريد الإلكتروني").fill("kook53281@gmail.com")
    page.get_by_placeholder("أدخل رقم الجوال").fill(r_phone)

    # --- Select2 الذكي ---
    match_success = False
    try:
        page.locator("#select2-merchant_address_form_city-container").click()
        page.get_by_role("searchbox").fill(city)
        page.wait_for_timeout(1500)

        # سحب الخيارات والمطابقة
        options = page.locator("li[role='option']").all()
        target_norm = normalize_arabic(f"{city} - {region}")

        for opt in options:
            opt_text = opt.inner_text()
            if target_norm in normalize_arabic(opt_text) or normalize_arabic(opt_text) in target_norm:
                opt.click()
                match_success = True
                print(f"      ✅ مطابقة ذكية: {opt_text}")
                break
        
        # محاولة ثانية بالمدينة فقط
        if not match_success:
            city_norm = normalize_arabic(city)
            for opt in options:
                if city_norm in normalize_arabic(opt.inner_text()):
                    opt.click()
                    match_success = True
                    print(f"      ✅ مطابقة بالمدينة فقط: {opt.inner_text()}")
                    break

    except Exception as e:
        print(f"      ❌ خطأ في القائمة: {e}")

    if not match_success:
        send_telegram_msg(f"⚠️ <b>تنبيه:</b> لم أجد مدينة مطابقة للطلب:\nالاسم: {r_name}\nالمدينة: {city}")
        return False

    # إكمال وتأكيد
    page.locator("#merchant_address_form_google_map_toggle").uncheck()
    page.get_by_role("textbox", name="تفاصيل العنوان").fill(full_address)

    try:
        page.get_by_role("button", name="إرسال").click()
        page.wait_for_timeout(2000)
        
        # التحقق النهائي
        if "settings/address" in page.url and "create" not in page.url:
            # رسالة نجاح لتليقرام
            msg = f"✅ <b>تمت الإضافة بنجاح!</b>\n👤 العميل: {r_name}\n📍 المدينة: {city}\n📱 الجوال: {r_phone}"
            send_telegram_msg(msg)
            return True
        return True # افتراض النجاح
    except:
        return False

# ======================================================
# 🚀 المحرك الرئيسي
# ======================================================
def start_bot():
    db = init_firebase()
    
    print("📡 جاري البحث عن طلبات (pending)...")
    # تم تعديل طريقة البحث لإصلاح التحذير السابق
    docs_stream = db.collection('orders').where(field_path='status', op_string='==', value='pending').stream()
    pending_orders = list(docs_stream)

    if not pending_orders:
        print("😴 لا توجد طلبات جديدة.")
        return

    print(f"📦 وجدنا {len(pending_orders)} طلبات.")
    send_telegram_msg(f"📦 <b>وجدنا {len(pending_orders)} طلبات جديدة</b>\nجاري البدء في المعالجة...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context()
        page = context.new_page()

        if login_to_torod(page):
            for doc in pending_orders:
                print("---------------------------------")
                if process_single_order(page, doc.to_dict(), doc.id):
                    print("      ✅ تحديث الحالة لـ done...")
                    db.collection('orders').document(doc.id).update({'status': 'done'})
                else:
                    print("      ❌ تخطي الطلب.")
            
            print("🏁 انتهى العمل.")
            send_telegram_msg("🏁 <b>انتهت جميع المهام!</b>")
        
        page.pause()
        browser.close()

if __name__ == "__main__":
    start_bot()
