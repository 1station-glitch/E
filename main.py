import os
import json
import tempfile
import random
import requests
import re
import time
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

# ==== دوال مساعدة ====
def clean_text(text):
    text = text.strip()
    text = text.replace("ة", "ه")
    if text.startswith("ال"):
        text = text[2:]
    return text

def normalize_arabic(text):
    """تنظيف النصوص العربية للمطابقة الذكية"""
    if not text: return ""
    text = str(text)
    text = re.sub(r'[\u064B-\u065F\u0640]', '', text) # تشكيل
    text = re.sub(r'[أإآ]', 'ا', text) # ألف
    text = re.sub(r'ة', 'ه', text) # تاء مربوطة
    text = re.sub(r'\bال', '', text) # ال التعريف
    return text.strip()

def get_variations(text):
    """توليد احتمالات للاسم (مع/بدون ال، تاء/هاء)"""
    if not text: return []
    variations = [text] 
    # معالجة التاء المربوطة والهاء
    if text.endswith("ة"): variations.append(text[:-1] + "ه")
    elif text.endswith("ه"): variations.append(text[:-1] + "ة")
    # معالجة ال التعريف
    if text.startswith("ال"):
        base = text[2:]
        variations.append(base)
        if base.endswith("ة"): variations.append(base[:-1] + "ه")
        elif base.endswith("ه"): variations.append(base[:-1] + "ة")
    else:
        variations.append("ال" + text)
    return list(set(variations))

# ==== جلب الطلبات pending ====
docs = db.collection("orders").where("status", "==", "pending").stream()

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
    city_region_log = f"{city} - {region}" # للعرض فقط
    
    district = order.get("district", "")
    street = order.get("street", "")
    district_street = f"{district} - {street}" 

    # توليد رمز عشوائي
    while True:
        branch_code = str(random.randint(10000, 99999))
        if branch_code not in used_codes:
            used_codes.add(branch_code)
            break

    notify(f"📦 بدء معالجة طلب:\nالمستودع: {store_name}\nالمدينة: {city}\nالمنطقة: {region}")

    # ==== بدء Playwright ====
    try:
        with sync_playwright() as p:
            # headless=True للسيرفرات
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1280, 'height': 720})
            page = context.new_page()

            # 1️⃣ تسجيل الدخول
            print(f"🔐 دخول: {store_name}")
            page.goto("https://torod.co/ar/login", timeout=60000)
            
            page.wait_for_selector("input[type='email']")
            page.locator("input[type='email']").fill("kook53281@gmail.com")
            page.locator("input[type='password']").fill("Abcd_0504989381")
            page.locator("button[type='submit']").click()
            
            # انتظار الانتقال للداشبورد
            page.wait_for_url("**/dashboard", timeout=60000)

            # 2️⃣ الانتقال لصفحة العناوين
            page.goto("https://torod.co/ar/settings/address")
            
            # انتظار زر "عنوان جديد"
            page.wait_for_selector("a[href*='address/create']", state="visible")
            page.locator("a[href*='address/create']").click()

            # 3️⃣ تعبئة البيانات الأساسية
            print("📝 تعبئة البيانات الأساسية...")
            page.wait_for_selector("#merchant_address_form_name")
            
            page.locator("#merchant_address_form_name").fill(store_name)
            page.locator("#merchant_address_form_title").fill(branch_code)
            page.locator("#merchant_address_form_contact_name").fill(receiver_name)
            page.locator("#merchant_address_form_email").fill("noon53281@gmail.com")
            page.locator("#merchant_address_form_phone_number").fill(receiver_phone)

            # ---------------------------------------------------------
            # 🏙️ كود اختيار المدينة (المطابقة الصارمة: مدينة + منطقة)
            # ---------------------------------------------------------
            print(f"🔍 البحث عن: المدينة ({city}) | المنطقة ({region})")

            search_attempts = get_variations(city)
            city_found = False

            for search_term in search_attempts:
                print(f"   🔄 تجربة البحث بكلمة: {search_term}")
                
                try:
                    # فتح القائمة (نضغط على الكونتينر)
                    page.locator("#select2-merchant_address_form_city-container").click(force=True)
                    
                    # مسح وكتابة الاسم ببطء
                    page.locator(".select2-search__field").fill("") 
                    page.locator(".select2-search__field").type(search_term, delay=100)
                    
                    print("   ⏳ انتظار 5 ثواني لتحميل النتائج...")
                    page.wait_for_timeout(5000)

                    # جلب النتائج
                    options = page.locator("li.select2-results__option").all()
                    
                    if not options:
                        print("      ⚠️ القائمة فاضية، نجرب الاحتمال التالي.")
                        page.mouse.click(0, 0) # إغلاق القائمة
                        continue

                    # فحص النتائج
                    target_city_norm = normalize_arabic(city)
                    target_region_norm = normalize_arabic(region)

                    for opt in options:
                        opt_text = opt.inner_text()
                        opt_norm = normalize_arabic(opt_text)

                        # الشرط: هل النص يحتوي على المدينة؟ وهل يحتوي على المنطقة؟
                        match_city = target_city_norm in opt_norm
                        match_region = target_region_norm in opt_norm

                        if match_city and match_region:
                            print(f"      ✅ تطابق ممتاز (مدينة+منطقة): {opt_text}")
                            opt.click()
                            city_found = True
                            break
                        elif match_city:
                            print(f"      👀 تطابق مدينة فقط '{opt_text}' (نبحث عن المنطقة '{region}').. تجاوز.")

                    if city_found:
                        break # تم الاختيار بنجاح
                    
                    # إغلاق القائمة للمحاولة التالية
                    page.mouse.click(0, 0)

                except Exception as e:
                    print(f"      ❌ خطأ أثناء البحث: {e}")
                    # محاولة إغلاق القائمة في حال حدوث خطأ
                    try: page.mouse.click(0, 0)
                    except: pass

            if not city_found:
                print(f"❌ فشل العثور على المدينة: {city} والمنطقة: {region}")
                notify(f"❌ لم يتم العثور على المدينة: {city} - {region}")
                # لن نضغط زر الحفظ حتى لا نسجل بيانات ناقصة، سنغلق المتصفح وننتقل للطلب التالي
                browser.close()
                continue # تخطي هذا الطلب

            # ---------------------------------------------------------

            # إغلاق الخريطة وتكملة العنوان
            if page.locator("#merchant_address_form_google_map_toggle").is_visible():
                page.locator("#merchant_address_form_google_map_toggle").click(force=True)

            page.locator("#merchant_address_form_address_details").fill(district_street)

            # الضغط على زر الحفظ
            page.locator("#address_form_btn").click()
            
            # انتظار بسيط للتأكد من الإرسال
            page.wait_for_timeout(5000)

            browser.close()

            # ==== تحديث الحالة بعد التنفيذ ====
            doc_ref.update({"status": "done"})
            notify(f"✅ تم تنفيذ الطلب بنجاح: {store_name}")

    except PlaywrightTimeoutError as e:
        notify(f"⚠️ الوقت انتهى (Timeout) للطلب {store_name}")
        print("Timeout Error")
    except Exception as e:
        notify(f"⚠️ خطأ غير متوقع: {e}")
        print(f"Error: {e}")
