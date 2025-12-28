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

            current_url = page.url
            print(f"📍 الرابط الحالي: {current_url}")
            
            if "login" in current_url:
                notify(f"❌ البوت فشل في الدخول!\nما زال في: {current_url}")
            elif "dashboard" in current_url or "settings" in current_url:
                notify(f"✅ البوت سجل دخول بنجاح!\nوصل لـ: {current_url}")
            else:
                notify(f"⚠️ البوت في صفحة غير معروفة:\n{current_url}")
            # 👆👆 ---------------------------------- 👆👆
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

          # ---------------------------------------------------------
            # 🏙️ كود اختيار المدينة (مطابقة المدينة + المنطقة بصرامة)
            # ---------------------------------------------------------
            print(f"🔍 جاري البحث عن: المدينة ({city}) | المنطقة ({region})")

            # 1. دالة لتوليد احتمالات اسم المدينة (عشان لو مكتوبة غلط)
            def get_variations(text):
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

            search_attempts = get_variations(city)
            city_found = False

            # 2. حلقة المحاولات
            for search_term in search_attempts:
                print(f"   🔄 تجربة البحث بكلمة: {search_term}")
                
                try:
                    # فتح القائمة
                    page.locator("#select2-merchant_address_form_city-container").click(force=True)
                    
                    # كتابة الاسم وانتظار 5 ثواني (كما طلبت)
                    page.locator(".select2-search__field").fill("") 
                    page.locator(".select2-search__field").type(search_term, delay=100)
                    
                    print("   ⏳ انتظار 5 ثواني لتحميل النتائج...")
                    page.wait_for_timeout(5000)

                    # جلب النتائج
                    options = page.locator("li.select2-results__option").all()
                    
                    if not options:
                        print("      ⚠️ القائمة فاضية، نجرب الاسم اللي بعده...")
                        # نضغط برا عشان نسكر القائمة ونعيد
                        page.mouse.click(0, 0)
                        continue

                    # 3. 🕵️ فحص النتائج (الشرط المزدوج: مدينة + منطقة)
                    target_city_norm = normalize_arabic(city)
                    target_region_norm = normalize_arabic(region)

                    for opt in options:
                        opt_text = opt.inner_text()       # النص الظاهر في الموقع
                        opt_norm = normalize_arabic(opt_text) # النص بعد التنظيف

                        # الشرط: هل المدينة موجودة؟ وهل المنطقة موجودة في نفس السطر؟
                        # مثال: الموقع يعرض "الدمام - المنطقة الشرقية"
                        # ونحن نبحث عن مدينة "الدمام" ومنطقة "الشرقية"
                        
                        match_city = target_city_norm in opt_norm
                        match_region = target_region_norm in opt_norm

                        if match_city and match_region:
                            print(f"      ✅ لقينا تطابق كامل (مدينة+منطقة): {opt_text}")
                            opt.click()
                            city_found = True
                            break
                        elif match_city:
                            # لقينا المدينة بس المنطقة ما تطابقت، نسجل ملاحظة ونكمل تدوير
                            print(f"      👀 لقينا المدينة '{opt_text}' بس المنطقة ما طابقت '{region}'.. نتجاوزها.")

                    if city_found:
                        break # خلاص لقيناه واخترناه
                    
                    # إذا خلصنا القائمة وما اخترنا شي، نسكرها عشان المحاولة الجاية
                    page.mouse.click(0, 0)

                except Exception as e:
                    print(f"      ❌ خطأ أثناء البحث: {e}")
                    page.mouse.click(0, 0)

            # 4. لو فشلت كل المحاولات
            if not city_found:
                print(f"❌ لم يتم العثور على مدينة: {city} في منطقة: {region}")
                notify(f"❌ البوت ما لقى المدينة: {city} مع المنطقة: {region}")
                # (اختياري) هنا ممكن تحط كود يختار أول خيار كاحتياط، أو تتركه فاضي وتخلي البوت يوقف
            
            # ---------------------------------------------------------
            # إكمال وتأكيد (Google Map والتفاصيل)
            page.locator("#merchant_address_form_google_map_toggle").uncheck()
            page.get_by_role("textbox", name="تفاصيل العنوان").fill(district_street)

            # 👇👇 بداية كود الفحص الشامل (7 نقاط) 👇👇
            try:
                # 1. قراءة النصوص العادية
                chk_store = page.locator("#merchant_address_form_name").input_value()
                chk_branch = page.locator("#merchant_address_form_title").input_value()
                chk_contact = page.locator("#merchant_address_form_contact_name").input_value()
                chk_phone = page.locator("#merchant_address_form_phone_number").input_value()
                chk_details = page.locator("#merchant_address_form_address_details").input_value()

                # 2. قراءة المدينة (نقرأ النص الظاهر في القائمة لأنها ليست خانة كتابة عادية)
                chk_city = page.locator("#select2-merchant_address_form_city-container").inner_text()

                # 3. قراءة حالة زر الخريطة (هل هو مفعل؟)
                is_map_checked = page.locator("#merchant_address_form_google_map_toggle").is_checked()
                map_status = "✅ مفعل (مفتوح)" if is_map_checked else "❎ مغلق (وهذا الصح)"

                # إرسال التقرير الكامل
                debug_msg = (
                    f"🕵️ <b>تقرير الفحص الشامل:</b>\n"
                    f"1️⃣ المتجر: {chk_store}\n"
                    f"2️⃣ رمز الفرع: {chk_branch}\n"
                    f"3️⃣ المسؤول: {chk_contact}\n"
                    f"4️⃣ الجوال: {chk_phone}\n"
                    f"5️⃣ المدينة: {chk_city}\n"
                    f"6️⃣ زر الخريطة: {map_status}\n"
                    f"7️⃣ العنوان: {chk_details}"
                )
                notify(debug_msg)
                print("✅ تم إرسال تقرير الفحص الكامل.")

            except Exception as e:
                notify(f"⚠️ فشل قراءة الخانات: {e}")
            # 👆👆 نهاية كود الفحص 👇👇
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
