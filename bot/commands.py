import os
from pathlib import Path

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.main import check_projects
from storage.db import add_keyword, get_keywords, remove_keyword


WAITING_ADD = "waiting_add"
WAITING_REMOVE = "waiting_remove"


def load_env(path: str = ".env") -> None:
    env_path = Path(path)

    if not env_path.exists():
        raise FileNotFoundError(".env файл не найден")

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📋 Показать ключевые слова"],
            ["➕ Добавить ключевое слово"],
            ["➖ Удалить ключевое слово"],
            ["🚀 Найти заказы сейчас"],
            ["📊 Статус"],
        ],
        resize_keyboard=True,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["mode"] = None

    await update.message.reply_text(
        "Панель управления ботом",
        reply_markup=keyboard(),
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keywords = get_keywords()

    await update.message.reply_text(
        f"Бот работает.\nКлючевых слов: {len(keywords)}",
        reply_markup=keyboard(),
    )


async def show_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keywords = get_keywords()

    if not keywords:
        await update.message.reply_text(
            "Ключевых слов нет.",
            reply_markup=keyboard(),
        )
        return

    text = "Текущие ключевые слова:\n\n"

    for i, keyword in enumerate(keywords, start=1):
        text += f"{i}. {keyword}\n"

    await update.message.reply_text(
        text,
        reply_markup=keyboard(),
    )


async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["mode"] = WAITING_ADD

    await update.message.reply_text(
        "Отправь ключевое слово или фразу для добавления.",
        reply_markup=keyboard(),
    )


async def start_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["mode"] = WAITING_REMOVE

    await update.message.reply_text(
        "Отправь ключевое слово или фразу для удаления.",
        reply_markup=keyboard(),
    )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    mode = context.user_data.get("mode")

    if text == "📋 Показать ключевые слова":
        await show_keywords(update, context)
        return

    if text == "➕ Добавить ключевое слово":
        await start_add(update, context)
        return

    if text == "➖ Удалить ключевое слово":
        await start_remove(update, context)
        return

    if text == "🚀 Найти заказы сейчас":
        result = await check_projects()
        await update.message.reply_text(result, reply_markup=keyboard())
        return

    if text == "📊 Статус":
        await status(update, context)
        return

    if mode == WAITING_ADD:
        if add_keyword(text):
            await update.message.reply_text(
                f"Добавлено: {text}",
                reply_markup=keyboard(),
            )
        else:
            await update.message.reply_text(
                "Такое ключевое слово уже есть или оно пустое.",
                reply_markup=keyboard(),
            )

        context.user_data["mode"] = None
        return

    if mode == WAITING_REMOVE:
        if remove_keyword(text):
            await update.message.reply_text(
                f"Удалено: {text}",
                reply_markup=keyboard(),
            )
        else:
            await update.message.reply_text(
                "Не найдено такое ключевое слово.",
                reply_markup=keyboard(),
            )

        context.user_data["mode"] = None
        return

    await update.message.reply_text(
        "Выбери действие кнопкой ниже.",
        reply_markup=keyboard(),
    )


def main() -> None:
    load_env()

    token = os.getenv("BOT_TOKEN")

    if not token:
        raise ValueError("BOT_TOKEN не найден")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Telegram command bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
