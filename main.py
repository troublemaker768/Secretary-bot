import os
import datetime
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
import asyncio

# Попытка импортировать openai (если нет ключа, будет просто отключена команда /ask)
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")  # берем токен из переменных окружения
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

if OPENAI_AVAILABLE and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# Храним задачи в памяти для простоты.
# tasks[user_id] = [ {"text": "...", "date": date, "done": False}, ... ]
tasks = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой бот-секретарь.\n\n"
        "• /add <дата YYYY-MM-DD> <текст задачи> — добавить задачу.\n"
        "• /tasks — показать задачи на сегодня.\n"
        "• /ask <вопрос> — вопрос к AI (если есть ключ OpenAI).\n"
        "Каждое утро я пришлю невыполненные задачи!"
    )

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if len(args) < 2:
        await update.message.reply_text("Формат: /add YYYY-MM-DD Текст задачи")
        return

    # Первая часть — это строка даты
    date_str = args[0]
    task_text = " ".join(args[1:])

    # Парсим дату
    try:
        task_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Используй YYYY-MM-DD.")
        return

    if user_id not in tasks:
        tasks[user_id] = []

    tasks[user_id].append({
        "text": task_text,
        "date": task_date,
        "done": False
    })

    await update.message.reply_text(f"Задача добавлена: {task_text} на {task_date}")

async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today = datetime.date.today()

    user_tasks = tasks.get(user_id, [])
    # Собираем невыполненные задачи, у которых дата <= сегодня
    today_tasks = [(i, t) for i, t in enumerate(user_tasks) if (t['date'] <= today and not t['done'])]

    if not today_tasks:
        await update.message.reply_text("У тебя нет задач на сегодня!")
        return

    # Делаем кнопки
    buttons = []
    for idx, t in today_tasks:
        text_btn = f"✅ {t['text']} (до {t['date']})"
        callback_data = f"done_{idx}"  # например, done_3
        buttons.append([InlineKeyboardButton(text_btn, callback_data=callback_data)])

    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Задачи на сегодня:", reply_markup=markup)

async def done_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data.startswith("done_"):
        idx_str = data.split("_")[1]
        idx = int(idx_str)

        if user_id in tasks and 0 <= idx < len(tasks[user_id]):
            tasks[user_id][idx]['done'] = True
            await query.edit_message_text(f"Задача выполнена: {tasks[user_id][idx]['text']}")
        else:
            await query.edit_message_text("Ошибка: задача не найдена.")

# Автоматическая рассылка каждое утро
async def send_daily_tasks(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.now().date()
    for user_id in tasks.keys():
        user_tasks = tasks[user_id]

        # Перенос всех просроченных и невыполненных задач на сегодня
        for t in user_tasks:
            if not t['done'] and t['date'] < now:
                t['date'] = now

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="Доброе утро! Загляни в /tasks, чтобы увидеть задачи на сегодня."
            )
        except:
            # Возможно, пользователь не нажимал /start
            pass

# Вопрос к OpenAI (опционально)
async def ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (OPENAI_AVAILABLE and OPENAI_API_KEY):
        await update.message.reply_text("OpenAI не настроен (нет ключа).")
        return

    question = " ".join(context.args)
    if not question:
        await update.message.reply_text("Нужно написать вопрос после /ask")
        return

    # Посылаем вопрос в GPT
    import openai
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Ты - полезный ассистент."},
            {"role": "user", "content": question}
        ]
    )
    answer = response.choices[0].message.content.strip()
    await update.message.reply_text(answer)

# Главная функция запуска бота
async def main():
    from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_task))
    app.add_handler(CommandHandler("tasks", show_tasks))
    app.add_handler(CommandHandler("ask", ask_ai))

    # Обработка нажатия кнопки
    app.add_handler(CallbackQueryHandler(done_button))

    # Ежедневная рассылка в 08:00 (UTC) — возможно, у тебя будет сдвиг по времени
    app.job_queue.run_daily(
        send_daily_tasks,
        time=datetime.time(hour=8, minute=0, second=0)
    )

    # Запуск
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
