import os
import asyncio
import logging
import random
import fitz  # PyMuPDF
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from groq import Groq
import pytz

# إعداد التسجيل (Logging)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ==========================================
# 🛠️ إعدادات المتغيرات البيئية والمعلومات الأساسية
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_توكن_البوت_هنا")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@Athar_Dz_Islamic")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "ضع_مفتاح_جروج_هنا")
PDF_PATH = os.getenv("PDF_PATH", "magazine.pdf")
PAGE_TRACKER_FILE = "current_page.txt"

# التذييل الإجباري لمنشورات كل 3 ساعات (بدون إيموجي)
MANDATORY_FOOTER = "هذي القناة هي صدقه جارية للأخت الأندلسية أم عقيدة وحمزة غفر الله لها وجعلها في ميزان حسناتها."

# تهيئة مكتبة جروج (Groq)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ==========================================
# 📖 وظائف معالجة ونشر المجلة
# ==========================================
def get_current_page():
    if os.path.exists(PAGE_TRACKER_FILE):
        with open(PAGE_TRACKER_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except ValueError:
                return 0
    return 0

def save_current_page(page_num):
    with open(PAGE_TRACKER_FILE, "w") as f:
        f.write(str(page_num))

def extract_page_text_only(pdf_path, page_num):
    """استخراج النص فقط من صفحة الـ PDF دون إنشاء صورة"""
    if not os.path.exists(pdf_path):
        logging.error(f"❌ لم يتم العثور على ملف المجلة: {pdf_path}")
        return None, 0

    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        if total_pages == 0:
            return None, 0

        if page_num >= total_pages:
            page_num = 0
            save_current_page(0)

        page = doc[page_num]
        text = page.get_text()
        doc.close()
        return text, total_pages
    except Exception as e:
        logging.error(f"خطأ أثناء استخراج نص الصفحة: {e}")
        return None, 0

def extract_page_data(pdf_path, page_num):
    """استخراج صورة ونص الصفحة"""
    if not os.path.exists(pdf_path):
        logging.error(f"❌ لم يتم العثور على ملف المجلة: {pdf_path}")
        return None, None, 0

    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        if total_pages == 0:
            return None, None, 0

        if page_num >= total_pages:
            page_num = 0
            save_current_page(0)

        page = doc[page_num]
        text = page.get_text()

        pix = page.get_pixmap(dpi=200)
        image_path = f"page_{page_num + 1}.jpg"
        pix.save(image_path)

        doc.close()
        return image_path, text, total_pages
    except Exception as e:
        logging.error(f"خطأ أثناء استخراج بيانات الصفحة: {e}")
        return None, None, 0

async def generate_groq_magazine_caption(raw_text, page_num):
    """إعادة صياغة نص صفحة المجلة عبر جروج (Groq AI) بدون إيموجي ومع هاشتاجات مرتبة"""
    if not groq_client or not raw_text or len(raw_text.strip()) < 10:
        return f"منشور المجلة - الصفحة {page_num}\n\n{raw_text[:800]}"

    prompt = f"""
أنت مساعد محتوى إسلامي احترافي. أعد صياغة وتنسيق النص التالي المستخرج من مجلة إسلامية ليكون منشوراً رائعاً وجذاباً لقناة تليجرام:

---
{raw_text}
---

المطلوب والتعليمات الصارمة:
1. يمنع منعاً باتاً استخدام أي إيموجي أو رموز تعبيرية نهائياً.
2. نسّق النص بأسلوب مرتب وواضح وبدون رموز معقدة.
3. أضف هاشتاجات مناسبة في نهاية النص بحيث تكون مرتبة كل هاشتاج في سطر منفصل، مثل:
#الحمدلله_ربي
#سبحان_الله
4. اعد النص فقط بدون أي مقدمات أو كلام جانبي.
"""
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.5,
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"خطأ أثناء الاتصال بجروج (Groq): {e}")
        return f"منشور المجلة - الصفحة {page_num}\n\n{raw_text[:800]}"

async def publish_magazine_page(bot: Bot) -> bool:
    """نشر صفحة من المجلة كصورة مع جزء من النص، وإكمال المتبقي في رسالة نصية تالية"""
    try:
        current_page = get_current_page()
        logging.info(f"جاري معالجة صفحة المجلة رقم: {current_page + 1}")

        image_path, raw_text, total_pages = extract_page_data(PDF_PATH, current_page)

        if image_path is None or not os.path.exists(image_path):
            logging.error("❌ لم يتم العثور على صورة الصفحة. تأكد من وجود ملف magazine.pdf")
            return False

        full_caption = await generate_groq_magazine_caption(raw_text, current_page + 1)
        footer_text = f"\n\nالقناة: {CHANNEL_USERNAME}"

        MAX_CAPTION_LEN = 950

        if len(full_caption) + len(footer_text) <= MAX_CAPTION_LEN:
            first_part = full_caption + footer_text
            second_part = None
        else:
            split_index = MAX_CAPTION_LEN - len(footer_text) - 10
            last_newline = full_caption.rfind('\n', 0, split_index)
            if last_newline != -1 and last_newline > 300:
                split_index = last_newline

            first_part = full_caption[:split_index] + footer_text
            second_part = "تتمة منشور المجلة:\n\n" + full_caption[split_index:] + footer_text

        # 1. إرسال الصورة مع الجزء الأول
        with open(image_path, 'rb') as photo:
            try:
                await bot.send_photo(
                    chat_id=CHANNEL_USERNAME,
                    photo=photo,
                    caption=first_part,
                    parse_mode=ParseMode.MARKDOWN
                )
            except TelegramError:
                photo.seek(0)
                await bot.send_photo(
                    chat_id=CHANNEL_USERNAME,
                    photo=photo,
                    caption=first_part
                )

        # 2. إرسال الجزء المتبقي إن وجد
        if second_part:
            await asyncio.sleep(1)
            try:
                await bot.send_message(
                    chat_id=CHANNEL_USERNAME,
                    text=second_part,
                    parse_mode=ParseMode.MARKDOWN
                )
            except TelegramError:
                await bot.send_message(
                    chat_id=CHANNEL_USERNAME,
                    text=second_part
                )

        logging.info(f"تم بنجاح نشر الصفحة {current_page + 1} من {total_pages}")
        save_current_page(current_page + 1)

        if os.path.exists(image_path):
            os.remove(image_path)

        return True

    except Exception as e:
        logging.error(f"خطأ غير متوقع في نشر المجلة: {e}")
        return False

async def publish_magazine_text_only(bot: Bot) -> bool:
    """نشر صفحة المجلة كنص فقط في القناة"""
    try:
        current_page = get_current_page()
        logging.info(f"جاري معالجة ونشر نص صفحة المجلة رقم: {current_page + 1}")

        raw_text, total_pages = extract_page_text_only(PDF_PATH, current_page)

        if not raw_text:
            logging.error("❌ لم يتم العثور على نص أو ملف PDF غير موجود.")
            return False

        caption = await generate_groq_magazine_caption(raw_text, current_page + 1)
        final_text = f"{caption}\n\nالقناة: {CHANNEL_USERNAME}"

        try:
            await bot.send_message(
                chat_id=CHANNEL_USERNAME,
                text=final_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except TelegramError:
            await bot.send_message(
                chat_id=CHANNEL_USERNAME,
                text=final_text
            )

        logging.info(f"تم نشر نص الصفحة {current_page + 1} بنجاح.")
        save_current_page(current_page + 1)
        return True

    except Exception as e:
        logging.error(f"خطأ في نشر نص المجلة: {e}")
        return False


# ==========================================
# 🔄 وظيفة النشر كل 3 ساعات
# ==========================================
async def generate_motivational_content():
    fallback_messages = [
        "إلى الإخوة والأخوات الموحدين: ثباتكم على الحق هو الحصن المنيع للأمة. استعينوا بالله ولا تعجزوا، وكونوا دائماً يداً واحدة ودرعاً حامياً لقضايا أمتكم الإسلامية.\n\n#ثبات_الموحدين\n#سبحان_الله",
        "نصيحة للموحدين المناصرين: اجعلوا عملكم خالصاً لوجه الله، وتسلحوا بالوعي والعلم، واعلموا أن كلمة الحق ونصرة المظلوم هي سهم في حماية الأمة ودفع الظلم عنها.\n\n#نصرة_الحق\n#الحمدلله_ربي"
    ]

    if not groq_client:
        return random.choice(fallback_messages)

    prompt = """
أكتب منشوراً إيمانياً وتوجيهياً قصيراً ومؤثراً وموجهاً للإخوة والأخوات (الموحدين المناصرين).
المواضيع المطلوب معالجتها:
1. نصائح وتوجيهات هامة للموحدين في الثبات، الصبر، الإخلاص، والوعي.
2. رسائل تحفيزية ومشجعة تحثهم على أن يكونوا درعاً حامياً للأمة الإسلامية ونصرة قضاياها بالكلمة والحق.

التعليمات الصارمة:
- أسلوب قوي، إيماني، وبليغ.
- يمنع منعاً باتاً استخدام أي إيموجي أو رموز تعبيرية نهائياً.
- أضف هاشتاجات إسلامية مناسبة في النهاية بحيث يكون كل هاشتاج في سطر منفصل، مثل:
#الحمدلله_ربي
#سبحان_الله
- الطول: فقرة إلى فقرتين قصيرة فقط.
- اعد النص المكتوب مباشرة بدون أي مقدمات أو كلام جانبي.
"""
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.6,
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"خطأ في جروج: {e}")
        return random.choice(fallback_messages)

async def publish_interval_post(bot: Bot):
    try:
        logging.info("جاري إعداد ونشر المنشور الدوري...")
        content = await generate_motivational_content()

        final_post = f"{content}\n\n{MANDATORY_FOOTER}"

        try:
            await bot.send_message(
                chat_id=CHANNEL_USERNAME,
                text=final_post,
                parse_mode=ParseMode.MARKDOWN
            )
        except TelegramError:
            await bot.send_message(
                chat_id=CHANNEL_USERNAME,
                text=final_post
            )

        logging.info("تم نشر المنشور الدوري بنجاح.")

    except Exception as e:
        logging.error(f"حدث خطأ في عملية النشر الدوري: {e}")


# ==========================================
# 💬 الرد والتفاعل مع الرسائل
# ==========================================
async def generate_channel_post_comment(post_text: str) -> str:
    fallback = "بارك الله فيكم على هذا المنشور القيّم.\nنسأل الله أن ينفع به الأمة."

    if not groq_client:
        return fallback

    prompt = f"""أنت مشرف إسلامي متفاعل في مجموعة تليجرام إسلامية. القناة نشرت هذا المنشور وظهر في المجموعة.

نص المنشور:
{post_text[:1000]}

المطلوب:
- اكتب تعليقاً قصيراً ومحفزاً على هذا المنشور (3 أسطر كحد أقصى).
- أسلوب إيماني دافئ.
- يمنع منعاً باتاً استخدام أي إيموجي أو رموز تعبيرية.
- اكتب التعليق مباشرة بدون مقدمات."""

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.5,
                max_tokens=200,
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        return fallback


async def generate_islamic_reply(user_message: str, user_name: str) -> str:
    fallback = f"أهلاً بك أخي/أختي {user_name}.\nجزاك الله خيراً وبارك الله فيك."

    if not groq_client:
        return fallback

    prompt = f"""أنت مساعد ومشرف إسلامي في مجموعة تليجرام، تتحدث بأسلوب لطيف ومحبب ومباشر موجه للإخوة والأخوات الموحدين والمناصرين.

رسالة العضو ({user_name}):
{user_message}

المطلوب:
- أجب أو تفاعل مع الرسالة بشكل مختصر ومفيد ومؤدب ودافئ.
- يمنع منعاً باتاً استخدام أي إيموجي أو رموز تعبيرية.
- الرد لا يزيد عن 4 إلى 5 أسطر.
- لا تذكر أبداً أنك ذكاء اصطناعي.
- اكتب الرد مباشرة بدون مقدمات."""

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.5,
                max_tokens=300,
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        return fallback


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        if not message or not message.text:
            return

        user_text = message.text.strip()

        is_channel_post = (
            message.sender_chat is not None
            and message.sender_chat.type == "channel"
        )

        if is_channel_post:
            await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")
            comment = await generate_channel_post_comment(user_text)
            await message.reply_text(text=comment)
            return

        if message.from_user and message.from_user.is_bot:
            return

        user_name = message.from_user.first_name if message.from_user else "عضو"
        await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")
        reply_text = await generate_islamic_reply(user_text, user_name)
        await message.reply_text(text=reply_text)

    except Exception as e:
        logging.error(f"خطأ في معالجة الرسالة: {e}")


# ==========================================
# 🧪 الأوامر المباشرة (Commands)
# ==========================================
async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر لتجربة النشر الفوري للقناة (صورة + نص)"""
    try:
        await update.message.reply_text("جاري اختبار نشر المجلة والمنشور الدوري...")
        success = await publish_magazine_page(context.bot)
        if not success:
            await update.message.reply_text("⚠️ لم يتم نشر المجلة كصورة! تأكد من وجود ملف magazine.pdf.")
        
        await publish_interval_post(context.bot)
        await update.message.reply_text("تم اكتمال الاختبار.")
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء الاختبار: {e}")

async def publish_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر لنشر نص المجلة فقط في القناة بدون صورة"""
    try:
        await update.message.reply_text("جاري نشر نص صفحة المجلة في القناة...")
        success = await publish_magazine_text_only(context.bot)
        if success:
            await update.message.reply_text("✅ تم نشر نص المجلة بنجاح في القناة.")
        else:
            await update.message.reply_text("❌ فشل النشر! تأكد من وجود ملف magazine.pdf.")
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ: {e}")


# ==========================================
# ⏰ المحرك والجدولة الرئيسية
# ==========================================
async def post_init(application: Application) -> None:
    bot = application.bot
    tz = pytz.timezone("Africa/Algiers")

    scheduler = AsyncIOScheduler(timezone=tz)

    scheduler.add_job(publish_magazine_page, 'cron', hour=9, minute=0, args=[bot])
    scheduler.add_job(publish_magazine_page, 'cron', hour=20, minute=0, args=[bot])
    scheduler.add_job(publish_interval_post, 'interval', hours=3, args=[bot])

    scheduler.start()
    application.bot_data['scheduler'] = scheduler
    logging.info("تم تشغيل الجدولة بنجاح...")


async def post_stop(application: Application) -> None:
    scheduler = application.bot_data.get('scheduler')
    if scheduler and scheduler.running:
        scheduler.shutdown()


def main():
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )

    # الأوامر المتاحة:
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(CommandHandler("publish_text", publish_text_command))

    # معالج الرسائل
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_message)
    )

    logging.info("البوت يعمل واستعد للاستجابة...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
                          
