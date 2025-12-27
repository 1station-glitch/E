import os
import json
import tempfile
import requests
import firebase_admin
from firebase_admin import credentials, firestore

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
    district_street = f"{district} {street}"
    
    status = order.get("status", "")

    # إرسال إشعار Telegram
    msg = (f"📦 طلب جديد:\n"
           f"المستودع: {store_name}\n"
           f"المسؤول: {receiver_name}\n"
           f"الهاتف: {receiver_phone}\n"
           f"المدينة/المنطقة: {city_region}\n"
           f"الحي/الشارع: {district_street}\n"
           f"الحالة: {status}")
    
    notify(msg)
    print(msg)

    # تحديث الحالة إلى done بعد الإرسال
    doc_ref.update({"status": "done"})
    print(f"تم تحديث حالة الطلب: {doc.id} → done")
