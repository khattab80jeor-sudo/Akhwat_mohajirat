import os
import asyncio
import logging
import random
import fitz  # PyMuPDF
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, MessageHandler, filters, ContextTypes
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

# التذييل الإجباري لمنشورات كل 3 ساعات
MANDATORY_FOOTER = "هذي القناة هي صدقه جارية للأخت الأندلسية أم عقيدة وحمزة غـفر الله لها وجعلها في ميزان حسناتها ☝🏻⚔️🖤"

# تهيئة مكتبة جروج (Groq)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ==========================================
# 📖 وظائف معالجة ونشر المجلة (الصباح والمساء)
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

def extract_page_data(pdf_path, page_num):
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        if page_num >= total_pages:
            logging.info("تم الوصول إلى نهاية المجلة.")
            return None, None, total_pages

        page = doc[page_num]
        text = page.get_text()

        # استخراج الصفحة كصورة عالية الجودة
        pix = page.get_pixmap(dpi=200)
        image_path = f"page_{page_num + 1}.jpg"
        pix.save(image_path)

        doc.close()
        return image_path, text, total_pages
    except Exception as e:
        logging.error(f"خطأ أثناء استخراج بيانات الصفحة: {e}")
        return None, None, 0

async def generate_groq_magazine_caption(raw_text, page_num):
    """إعادة صياغة نص صفحة المجلة عبر جروج (Groq AI)"""
    if not groq_client or not raw_text or len(raw_text.strip()) < 10:
        return f"📖 **منشور المجلة - الصفحة {page_num}**\n\n{raw_text[:800]}..."

    prompt = f"""
أنت مساعد محتوى إسلامي احترافي. أعد صياغة وتنسيق النص التالي المستخرج من مجلة إسلامية ليكون منشوراً رائعاً وجذاباً لقناة تليجرام:

---
{raw_text}
---

المطلوب:
1. نسّق النص باستخدام الماركداون (عناوين، نقاط، إيموجي إسلامية مناسبة).
2. اجعل الصياغة قوية وواضحة.
3. أضف هاشتاجات مناسبة في نهاية النص.
4. اعد النص فقط بدون مقدمات.
"""
    try:
        loop = asyncio.get_event_loop()
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
        logging.error(f"خطأ أثناء الاتصال بجروج (Groq): {e}")
        return f"📖 **منشور المجلة - الصفحة {page_num}**\n\n{raw_text[:800]}..."

async def publish_magazine_page(bot: Bot):
    """نشر صفحة من المجلة (الصباح والمساء)"""
    try:
        current_page = get_current_page()
        logging.info(f"جاري معالجة صفحة المجلة رقم: {current_page + 1}")

        image_path, raw_text, total_pages = extract_page_data(PDF_PATH, current_page)

        if image_path is None:
            return

        caption = await generate_groq_magazine_caption(raw_text, current_page + 1)
        final_caption = f"{caption}\n\n📢 **القناة:** {CHANNEL_USERNAME}"

        if len(final_caption) > 1024:
            final_caption = final_caption[:1020] + "..."

        with open(image_path, 'rb') as photo:
            await bot.send_photo(
                chat_id=CHANNEL_USERNAME,
                photo=photo,
                caption=final_caption,
                parse_mode=ParseMode.MARKDOWN
            )

        logging.info(f"تم بنجاح نشر الصفحة {current_page + 1} من {total_pages}")
        save_current_page(current_page + 1)

        if os.path.exists(image_path):
            os.remove(image_path)

    except TelegramError as e:
        logging.error(f"خطأ في إرسال التليجرام: {e}")
    except Exception as e:
        logging.error(f"خطأ غير متوقع في نشر المجلة: {e}")


# ==========================================
# 🔄 وظيفة النشر كل 3 ساعات عبر جروج (Groq)
# ==========================================
async def generate_motivational_content():
    """توليد توجيهات ونصائح تحفيزية عبر جروج (Groq AI)"""
    fallback_messages = [
        "إلى الإخوة والأخوات الموحدين: ثباتكم على الحق هو الحصن المنيع للأمة. استعينوا بالله ولا تعجزوا، وكونوا دائماً يداً واحدة ودرعاً حامياً لقضايا أمتكم الإسلامية. ⚔️",
        "نصيحة للموحدين المناصرين: اجعلوا عملكم خالصاً لوجه الله، وتسلحوا بالوعي والعلم، واعلموا أن كلمة الحق ونصرة المظلوم هي سهم في حماية الأمة ودفع الظلم عنها. ☝🏻",
        "يا أبناء الأمة الإسلامية: إن الأمة اليوم بأشد الحاجة إلى الوعي والثبات. كونوا درعاً للأمة ونوراً يضيء طريق الموحدين بالتذكير والدعاء والنصرة بالكلمة الطيبة."
    ]

    if not groq_client:
        return random.choice(fallback_messages)

    prompt = """
أكتب منشوراً إيمانياً وتوجيهياً قصيراً ومؤثراً وموجهاً للإخوة والأخوات (الموحدين المناصرين).
المواضيع المطلوبة:
1. نصائح وتوجيهات هامة للموحدين في الثبات، الصبر، الإخلاص، والوعي.
2. رسائل تحفيزية ومشجعة تحثهم على أن يكونوا درعاً حامياً للأمة الإسلامية ونصرة قضاياها بالكلمة والحق.

الشروط:
- أسلوب قوي، إيماني، وبليغ.
- استخدام التنسيق الجذاب مع الرموز التعبيرية (Emojis) والهاشتاجات.
- الطول: فقرة إلى فقرتين قصيرة فقط.
- اعد النص المكتوب مباشرة بدون أي مقدمات أو كلام جانبي.
"""
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.7,
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"خطأ في جروج أثناء توليد منشور الـ 3 ساعات: {e}")
        return random.choice(fallback_messages)

async def publish_interval_post(bot: Bot):
    """النشر التلقائي كل 3 ساعات مع التذييل الإجباري"""
    try:
        logging.info("جاري إعداد ونشر المنشور الدوري بواسطة جروج (كل 3 ساعات)...")
        content = await generate_motivational_content()

        final_post = f"{content}\n\n{MANDATORY_FOOTER}"

        await bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=final_post,
            parse_mode=ParseMode.MARKDOWN
        )
        logging.info("تم نشر المنشور الدوري بنجاح.")

    except TelegramError as e:
        logging.error(f"خطأ في إرسال المنشور الدوري على التليجرام: {e}")
    except Exception as e:
        logging.error(f"حدث خطأ في عملية النشر الدوري: {e}")


# ==========================================
# 💬 الرد على رسائل المجموعة (الأسئلة الشرعية والتفاعل)
# ==========================================
async def generate_channel_post_comment(post_text: str) -> str:
    """توليد تعليق إسلامي تلقائي على منشورات القناة في المجموعة"""
    fallback = (
        "بارك الله فيكم على هذا المنشور القيّم 🤍\n"
        "نسأل الله أن ينفع به الأمة ويجعله في ميزان حسنات الجميع. ☝🏻⚔️"
    )

    if not groq_client:
        return fallback

    prompt = f"""أنت مشرف إسلامي متفاعل في مجموعة تليجرام إسلامية. القناة نشرت هذا المنشور وظهر في المجموعة.

نص المنشور:
{post_text[:1000]}

المطلوب:
- اكتب تعليقاً قصيراً ومحفزاً على هذا المنشور (3 أسطر كحد أقصى).
- أسلوب إيماني دافئ يشجع الإخوة والأخوات على التفاعل والقراءة.
- يمكنك إضافة آية أو حديث مختصر يناسب موضوع المنشور إن أمكن.
- استخدم إيموجي إسلامية مناسبة.
- لا تكرر نص المنشور، فقط علّق عليه.
- اكتب التعليق مباشرة بدون مقدمات."""

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.6,
                max_tokens=200,
            )
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"خطأ في Groq أثناء توليد تعليق منشور القناة: {e}")
        return fallback


async def generate_islamic_reply(user_message: str, user_name: str) -> str:
    """توليد رد إسلامي على رسائل أعضاء المجموعة عبر Groq"""
    fallback = (
        "جزاك الله خيراً على مشاركتك أخي/أختي الكريم/ة. 🤍\n"
        "نسأل الله أن يبارك فيك وأن يثبتنا وإياك على الحق. ☝🏻"
    )

    if not groq_client:
        return fallback

    prompt = f"""أنت مساعد إسلامي متخصص في الفقه والتوجيه الديني، تتحدث بأسلوب لطيف ومحبب موجه للموحدين والمناصرين.

رسالة العضو ({user_name}):
{user_message}

المطلوب:
- أجب بشكل مختصر ومفيد ومؤدب.
- إذا كان سؤالاً شرعياً، أجب بما يوافق مذهب أهل السنة والجماعة مع الاستشهاد بالدليل إن أمكن.
- إذا كانت مشاركة أو تعليقاً، تفاعل معه بإيجابية وإيمانية.
- اختم دائماً بدعاء أو جملة تحفيزية قصيرة.
- الرد لا يزيد عن 5 أسطر.
- لا تذكر أنك ذكاء اصطناعي.
- اكتب الرد مباشرة بدون مقدمات."""

    try:
        loop = asyncio.get_event_loop()
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
        logging.error(f"خطأ في Groq أثناء توليد الرد على المجموعة: {e}")
        return fallback


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة رسائل المجموعة: التعليق على منشورات القناة + الرد على أسئلة الأعضاء"""
    try:
        message = update.message
        if not message or not message.text:
            return

        user_text = message.text.strip()

        # ✅ الحالة 1: منشور من القناة ظهر في المجموعة المرتبطة
        # يحدث هذا عندما sender_chat هو قناة (channel)
        is_channel_post = (
            message.sender_chat is not None
            and message.sender_chat.type == "channel"
        )

        if is_channel_post:
            logging.info(f"منشور قناة جديد في المجموعة، جاري التعليق عليه...")
            await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")
            comment = await generate_channel_post_comment(user_text)
            await message.reply_text(text=comment, parse_mode=ParseMode.MARKDOWN)
            return

        # تجاهل رسائل البوتات الأخرى
        if message.from_user and message.from_user.is_bot:
            return

        # ✅ الحالة 2: رسائل الأعضاء (أسئلة أو ردود أو استدعاء)
        user_name = message.from_user.first_name if message.from_user else "عضو"
        bot_username = context.bot.username or ""

        is_question = "?" in user_text or "؟" in user_text
        is_reply_to_bot = (
            message.reply_to_message is not None
            and message.reply_to_message.from_user is not None
            and message.reply_to_message.from_user.is_bot
        )
        is_mention = f"@{bot_username}" in user_text

        if not (is_question or is_reply_to_bot or is_mention):
            return

        logging.info(f"سؤال/رسالة من {user_name}: {user_text[:50]}...")
        await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")
        reply_text = await generate_islamic_reply(user_text, user_name)
        await message.reply_text(text=reply_text, parse_mode=ParseMode.MARKDOWN)

    except TelegramError as e:
        logging.error(f"خطأ Telegram في معالجة رسالة المجموعة: {e}")
    except Exception as e:
        logging.error(f"خطأ غير متوقع في معالجة رسالة المجموعة: {e}")


# ==========================================
# ⏰ المحرك والجدولة الرئيسية (post_init + run_polling)
# ==========================================
async def post_init(application: Application) -> None:
    """يُستدعى بعد تهيئة التطبيق — نبدأ الجدولة والمنشور الأول هنا"""
    bot = application.bot
    tz = pytz.timezone("Africa/Algiers")  # توقيت الجزائر/مكة

    scheduler = AsyncIOScheduler(timezone=tz)

    # 1. جدول منشورات المجلة (الصباح 09:00 والمساء 20:00)
    scheduler.add_job(publish_magazine_page, 'cron', hour=9, minute=0, args=[bot])
    scheduler.add_job(publish_magazine_page, 'cron', hour=20, minute=0, args=[bot])

    # 2. جدول المنشورات التحفيزية عبر Groq (كل 3 ساعات)
    scheduler.add_job(publish_interval_post, 'interval', hours=3, args=[bot])

    scheduler.start()
    application.bot_data['scheduler'] = scheduler
    logging.info("تم تشغيل الجدولة بنجاح (المجلة + منشور كل 3 ساعات + ردود المجموعة)...")

    # 🚀 نشر فوري عند الانطلاق للتأكد من عمل البوت
    logging.info("جاري نشر أول منشور تجريبي...")
    await publish_magazine_page(bot)


async def post_stop(application: Application) -> None:
    """يُستدعى عند إيقاف التطبيق — نوقف الجدولة بأمان"""
    scheduler = application.bot_data.get('scheduler')
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logging.info("تم إيقاف الجدولة بأمان.")


def main():
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )

    # إضافة معالج رسائل المجموعة
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_message)
    )

    logging.info("البوت يعمل...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
    
