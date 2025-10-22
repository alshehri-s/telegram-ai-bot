import os
from typing import Optional
from fastapi import FastAPI, Request, Response
import uvicorn

from telegram import Update, Message
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ---------- OpenAI ----------
from openai import OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # مثال: -1001234567890 أو @MyChannel

SYSTEM_PROMPT = (
    "أنت مساعد تعليمي عربي فصيح. أجب بإيجاز ووضوح، "
    "وإن كان السؤال من منهج العلوم للصف السادس فاذكر المفهوم بدقة وخطوات مبسطة."
)

def ask_chatgpt(user_text: str) -> str:
    try:
        res = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            max_output_tokens=600,
        )
        return (res.output_text or "").strip() or "لم أتمكن من توليد إجابة الآن."
    except Exception as e:
        return f"حدث خطأ أثناء الاتصال بالنموذج: {e}"

# ---------- Telegram + FastAPI (Webhook) ----------
app = FastAPI()
telegram_app: Optional[Application] = None

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("مرحبًا! أرسل سؤالك أو استخدم /ask متبوعًا بسؤالك.")

async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_q = " ".join(context.args) if context.args else (update.message.text or "")
    if not user_q:
        await update.message.reply_text("اكتب سؤالك بعد الأمر /ask")
        return
    await update.message.chat.send_action("typing")
    answer = ask_chatgpt(user_q)
    await update.message.reply_text(answer)

    if CHANNEL_ID:
        try:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=f"🔔 سؤال:\n{user_q}\n\n💡 الإجابة:\n{answer}")
        except Exception as e:
            await update.message.reply_text(f"تنبيه: لم أستطع النشر في القناة: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg: Message = update.effective_message
    text = (msg.text or "").strip()
    if not text:
        return

    await msg.chat.send_action("typing")
    answer = ask_chatgpt(text)

    if update.channel_post:  # منشور قناة
        await context.bot.send_message(chat_id=msg.chat_id, text=answer, reply_to_message_id=msg.message_id)
    else:  # خاص/مجموعة
        await msg.reply_text(answer)
        if CHANNEL_ID:
            try:
                await context.bot.send_message(chat_id=CHANNEL_ID, text=f"🧩 سؤال عضو:\n{text}\n\n🧠 الإجابة:\n{answer}")
            except Exception:
                pass

@app.on_event("startup")
async def on_startup():
    global telegram_app
    telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start_cmd))
    telegram_app.add_handler(CommandHandler("ask", ask_cmd))
    telegram_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    await telegram_app.initialize()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    global telegram_app
    if telegram_app is None:
        return Response(status_code=500)

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return Response(status_code=200)

@app.get("/")
async def index():
    return {"ok": True, "msg": "Bot is running."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
