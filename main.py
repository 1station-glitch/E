import json
import os
import requests
import tempfile
import firebase_admin
from firebase_admin import credentials, firestore

# ==== Firebase setup ====
firebase_json = os.environ['FIREBASE_JSON']
# نكتب JSON مؤقت لأن firebase-admin يحتاج ملف
with tempfile.NamedTemporaryFile(mode='w+', delete=False) as f:
    f.write(firebase_json)
    firebase_file = f.name

cred = credentials.Certificate(firebase_file)
firebase_admin.initialize_app(cred)
db = firestore.client()

# ==== Telegram setup ====
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

def notify(msg):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg})

# ==== جلب البيانات من Firebase ====
docs = db.collection("orders").stream()

for doc in docs:
    data = doc.to_dict()
    # مثال: البيانات تشمل "name" و "city"
    name = data.get("name")
    city = data.get("city")
    msg = f"تم استلام طلب جديد!\nالاسم: {name}\nالمدينة: {city}"
    print(msg)   # للطباعة في Log
    notify(msg)  # إرسال Telegram
