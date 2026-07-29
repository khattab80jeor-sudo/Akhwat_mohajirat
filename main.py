import os
import fitz  # PyMuPDF
from groq import Groq
from telegram import Bot
from telegram.constants import ParseMode
from apscheduler.schedulers.blocking import BlockingScheduler
import pytz
import logging

# إعداد التسجيل (Logging)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# المتغيرات البيئية
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@Athar_Dz_Islamic")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PDF_PATH = os.getenv("PDF_PATH", "magazine.pdf")
PAGE_TRACKER_FILE = "current_page.txt"

# تهيئة Groq و Telegram Bot
groq_client = Groq(api_key=GROQ_API_KEY)
bot = Bot(token=TELEGRAM_TOKEN)

def get_current_page():
    """قراءة رقم الصفحة الحالية من الملف"""
    if os.path.exists(PAGE_TRACKER_FILE):
        with open(PAGE_TRACKER_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except ValueError:
                return 0
    return 0

def save_current_page(page_num):
    """حفظ رقم الصفحة القادمة"""
    with open(PAGE_TRACKER_FILE, "w") as f:
        f.write(str(page_num))

def extract_page_data(pdf_path, page_num):
    """استخراج الصورة والنص من صفحة معينة"""
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    
    if page_num >= total_pages:
        logging.info("تم الوصول إلى نهاية المجلة.")
        return None, None, total_pages

    page = doc[page_num]
    
    # 1. استخراج النص
    text = page.get_text()

    # 2. تحويل الصفحة إلى صورة جودة عالية
    pix = page.get_pixmap(dpi=200)
    image_path = f"page_{page_num + 1}.jpg"
    pix.save(image_path)

    doc.close()
    return image_path, text, total_pages

def rephrase_with_groq(raw_text):
    """صياغة النص باستخدام الذكاء الاصطناعي من Groq"""
    if not raw_text or len(raw_text.strip()) < 10:
        return "✨ **محتوى اليوم من المجلة** ✨\n\nتصفح الصورة المرفقة لمعرفة تفاصيل هذه الصفحة."

    prompt = f"""
أنت مساعد ذكي ومتخصص في إدارة شبكات التواصل الاجتماعي الإسلامية/الثقافية.
لديك النص التالي المستخرج من صفحة في مجلة:

---
{raw_text}
---

المطلوب:
1. أعد صياغة وتحسين النص ليكون منشوراً جذاباً ومناسباً للنشر على قناة تليجرام.
2. نسّق النص باستخدام Markdown (عناوين، نقاط، إيموجي مناسبة).
3. أضف في النهاية هاشتاجات مناسبة وحثاً خفيفاً على القراءة والتفاعل.
4. حافظ على المعنى الأصلي ودقة المعلومات.
5. اجعل الرد بالنص المنقح فقط بدون أي مقدمات أو كلام إضافي منك.
"""

    try:
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.6,
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"خطأ أثناء الاتصال بـ Groq: {e}")
        return f"📖 **محتوى الصفحة:**\n\n{raw_text[:800]}..."

async def publish_next_page():
    """دالة الجدولة والنشر"""
    try:
        current_page = get_current_page()
        logging.info(f"جاري معالجة الصفحة رقم: {current_page + 1}")

        image_path, raw_text, total_pages = extract_page_data(PDF_PATH, current_page)

        if image_path is None:
            logging.info("انتهت كافة صفحات المجلة.")
            return

        # صياغة النص بـ Groq AI
        caption = rephrase_with_groq(raw_text)

        # إضافة حقوق القناة في أسفل منشور التليجرام
        final_caption = f"{caption}\n\n📢 **قناتنا:** {CHANNEL_USERNAME}"
        if len(final_caption) > 1024: # حد تليجرام لوصف الصورة
            final_caption = final_caption[:1020] + "..."

        # النشر في التليجرام
        with open(image_path, 'rb') as photo:
            await bot.send_photo(
                chat_id=CHANNEL_USERNAME,
                photo=photo,
                caption=final_caption,
                parse_mode=ParseMode.MARKDOWN
            )

        logging.info(f"تم بنجاح نشر الصفحة {current_page + 1} من {total_pages}")

        # تحديث الصفحة القادمة
        save_current_page(current_page + 1)

        # حذف الصورة المؤقتة
        if os.path.exists(image_path):
            os.remove(image_path)

    except Exception as e:
        logging.error(f"حدث خطأ أثناء عملية النشر: {e}")

def run_job():
    import asyncio
    asyncio.run(publish_next_page())

if __name__ == "__main__":
    # إعداد الجدول الزمني للنشر (صباحاً ومساءً)
    tz = pytz.timezone("Africa/Algiers") # أو Asia/Riyadh حسب توقيتك
    scheduler = BlockingScheduler(timezone=tz)

    # نشر الصباح الساعة 09:00 صباحاً
    scheduler.add_job(run_job, 'cron', hour=9, minute=0)

    # نشر المساء الساعة 20:00 (8 مساءً)
    scheduler.add_job(run_job, 'cron', hour=20, minute=0)

    logging.info("تم تشغيل البوت والجدولة بنجاح...")
    
    # لتجربة النشر فور تشغيل البوت لأول مرة (اختياري):
    # run_job()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
  
