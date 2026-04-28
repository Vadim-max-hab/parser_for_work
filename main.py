import hashlib
import html
import os
import re
import sqlite3
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


load_dotenv(".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")

DB_PATH = "leads.db"
CHANNELS_FILE = "channels.txt"

if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN в .env")

if not OWNER_ID:
    raise RuntimeError("Не найден OWNER_ID в .env")


GOOD_KEYWORDS = [
    "бот", "telegram", "телеграм", "чат-бот", "чатбот",
    "ai", "ии", "нейросеть", "gpt", "openai",
    "автоматизация", "парсер", "скрипт", "python",
    "заявки", "интеграция", "crm", "google sheets",
    "таблиц", "wildberries", "wb", "ozon",
    "карточка", "дизайн карточки", "инфографика",
    "лендинг", "сайт", "api"
]

BAD_KEYWORDS = [
    "спам", "массовая рассылка", "накрутка", "казино",
    "ставки", "букмекер", "18+", "скам", "обман",
    "взлом", "фишинг", "серые схемы", "наркот", "кардинг"
]



def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            lead_id TEXT PRIMARY KEY,
            source TEXT,
            post_id TEXT,
            text TEXT,
            url TEXT,
            score INTEGER,
            category TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id TEXT,
            source TEXT,
            action TEXT,
            text TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def load_channels():
    if not os.path.exists(CHANNELS_FILE):
        return []

    channels = []

    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            channel = line.strip().replace("@", "")
            if channel and not channel.startswith("#"):
                channels.append(channel)

    return channels


def is_seen(lead_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT lead_id FROM leads WHERE lead_id = ?", (lead_id,))
    row = cur.fetchone()

    conn.close()
    return row is not None


def save_lead(lead):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO leads
        (lead_id, source, post_id, text, url, score, category, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lead["lead_id"],
        lead["source"],
        lead["post_id"],
        lead["text"],
        lead["url"],
        lead["score"],
        lead["category"],
        datetime.now().isoformat(timespec="seconds"),
    ))

    conn.commit()
    conn.close()


def make_lead_id(source, post_id, text):
    raw = f"{source}:{post_id}:{text[:300]}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def clean_text(text, limit=1200):
    text = re.sub(r"\n{3,}", "\n\n", text.strip())

    if len(text) > limit:
        text = text[:limit] + "..."

    return text



STRICT_DEV_PHRASES = [
    "telegram-бот", "телеграм-бот", "чат-бот", "chat-bot", "chatbot",
    "бот для", "бота для", "бот под", "бота под",
    "нужен бот", "нужен телеграм", "нужен telegram",
    "сделать бот", "создать бот", "разработать бот", "собрать бот",
    "aiogram", "telethon",
    "парсер", "парсинг", "скрипт", "python",
    "api", "webhook", "backend", "frontend",
    "интеграц", "автоматизац", "crm",
    "google sheets", "гугл таблиц",
    "openai", "chatgpt", "gpt", "llm", "rag",
    "ai-агент", "ии-агент", "ai agent",
    "база знаний", "нейро-бот", "нейробот",
    "сайт", "лендинг", "wordpress"
]

STRICT_HARD_BLOCK = [
    "ваканс", "резюме", "зарплат", "оклад", "без опыта",
    "менеджер", "продаж", "sales", "hr", "рекрутер", "найм",
    "finder.work/vacancies", "hh.ru", "superjob",
    "полная занятость", "частичная занятость", "график работы"
]

STRICT_CONTENT_BLOCK = [
    "копирайтер", "редактор", "тексты", "текстики",
    "написание текст", "tone of voice", "статьи", "контент",
    "социальных медиа", "соцмедиа", "соцсет", "smm",
    "блогер", "блогерств", "посты", "новости",
    "присоединяйтесь", "первые объявления",
    "дизайн-студи", "архитектурн", "логотип", "брендбук",
    "рилс", "reels", "монтаж", "видео", "перевод"
]


def strict_contains_any(lower, phrases):
    return any(phrase in lower for phrase in phrases)


def strict_count_hits(lower, phrases):
    return sum(1 for phrase in phrases if phrase in lower)

def is_relevant(text):
    lower = text.lower()

    if len(lower) < 50:
        return False

    if any(word in lower for word in BAD_KEYWORDS):
        return False

    # Вакансии, продажи, HR, копирайтинг, контент и SMM не берём.
    if strict_contains_any(lower, STRICT_HARD_BLOCK):
        return False

    if strict_contains_any(lower, STRICT_CONTENT_BLOCK):
        return False

    # Просто слова "ИИ" или "нейросеть" больше не считаются заявкой.
    # Нужен явный признак разработки: бот, парсер, API, интеграция, GPT, RAG и т.д.
    if not strict_contains_any(lower, STRICT_DEV_PHRASES):
        return False

    return True

def calculate_score(text):
    lower = text.lower()

    if strict_contains_any(lower, STRICT_HARD_BLOCK):
        return 1

    if strict_contains_any(lower, STRICT_CONTENT_BLOCK):
        return 1

    hits = strict_count_hits(lower, STRICT_DEV_PHRASES)

    if hits == 0:
        return 1

    score = 4 + min(hits, 4)

    if "срочно" in lower or "сегодня" in lower or "завтра" in lower:
        score += 1

    if "бюджет" in lower or "₽" in lower or "руб" in lower or "$" in lower:
        score += 1

    if "оплата" in lower or "предоплата" in lower:
        score += 1

    if "без предоплаты" in lower:
        score -= 3

    if "тестовое" in lower and "оплач" not in lower:
        score -= 2

    return max(1, min(score, 10))

def detect_category(text):
    lower = text.lower()

    if any(x in lower for x in ["telegram-бот", "телеграм-бот", "чат-бот", "бот для", "бота для", "aiogram", "telethon"]):
        return "Telegram-бот / автоматизация"

    if any(x in lower for x in ["openai", "chatgpt", "gpt", "llm", "rag", "ai-агент", "ии-агент", "база знаний", "нейро-бот", "нейробот"]):
        return "AI-продукт / AI-агент"

    if any(x in lower for x in ["парсер", "парсинг", "скрипт", "python"]):
        return "Парсер / Python-скрипт"

    if any(x in lower for x in ["api", "webhook", "crm", "интеграц", "автоматизац"]):
        return "Интеграция / автоматизация"

    if any(x in lower for x in ["сайт", "лендинг", "wordpress", "frontend", "backend"]):
        return "Сайт / лендинг"

    return "IT-разработка"

def suggest_price(text):
    lower = text.lower()

    if any(x in lower for x in ["openai", "chatgpt", "gpt", "llm", "rag", "ai-агент", "ии-агент", "база знаний"]):
        return "10 000–35 000 ₽"

    if any(x in lower for x in ["api", "webhook", "crm", "интеграц", "автоматизац"]):
        return "8 000–25 000 ₽"

    if any(x in lower for x in ["telegram-бот", "телеграм-бот", "чат-бот", "бот для", "бота для"]):
        return "5 000–15 000 ₽"

    if any(x in lower for x in ["парсер", "парсинг", "скрипт", "python"]):
        return "5 000–15 000 ₽"

    if any(x in lower for x in ["сайт", "лендинг", "wordpress"]):
        return "5 000–20 000 ₽"

    return "3 000–10 000 ₽"

def detect_risks(text):
    lower = text.lower()
    risks = []

    if "без предоплаты" in lower:
        risks.append("не работать без предоплаты")

    if "тестовое" in lower and "оплач" not in lower:
        risks.append("риск бесплатного тестового")

    if "срочно" in lower or "сегодня" in lower:
        risks.append("срочность — можно ставить цену выше")

    if not risks:
        return "явных рисков нет"

    return "; ".join(risks)


def generate_reply(text, category):
    lower = text.lower()

    if "бот" in lower or "telegram" in lower or "телеграм" in lower:
        return (
            "Здравствуйте. Могу собрать Telegram-бота под вашу задачу.\n\n"
            "Сделаю понятную структуру: меню, кнопки, сценарии, сбор заявок и уведомления. "
            "Сначала уточню логику, затем соберу рабочую версию, покажу тест и внесу правки.\n\n"
            "Готов обсудить детали и предложить оптимальную реализацию."
        )

    if "ai" in lower or "ии" in lower or "нейросеть" in lower or "gpt" in lower:
        return (
            "Здравствуйте. Могу помочь с AI-решением под вашу задачу.\n\n"
            "Сначала разберу сценарий, затем предложу простую рабочую архитектуру: база знаний, "
            "логика ответов, интеграция с Telegram/таблицами/CRM при необходимости.\n\n"
            "Готов быстро обсудить детали."
        )

    if "парсер" in lower or "скрипт" in lower or "python" in lower:
        return (
            "Здравствуйте. Могу сделать Python-скрипт/парсер под вашу задачу.\n\n"
            "Уточню источник данных, формат результата и ограничения, после этого соберу рабочую версию "
            "и передам понятную инструкцию по запуску.\n\n"
            "Готов обсудить детали."
        )

    if "карточк" in lower or "wb" in lower or "ozon" in lower:
        return (
            "Здравствуйте. Могу помочь с карточками для маркетплейса.\n\n"
            "Могу разобрать текущую карточку, предложить улучшение визуала, структуры смыслов, "
            "SEO и подготовить более продающую подачу.\n\n"
            "Готов посмотреть товар и предложить конкретный план."
        )

    return (
        f"Здравствуйте. Могу выполнить задачу по направлению: {category}.\n\n"
        "Работаю с Telegram-ботами, автоматизацией, парсерами, AI-решениями и упаковкой услуг. "
        "Могу быстро разобрать задачу, предложить структуру и собрать рабочую версию.\n\n"
        "Готов обсудить детали."
    )


def parse_channel(channel):
    url = f"https://t.me/s/{channel}"

    headers = {
        "User-Agent": "Mozilla/5.0 Android LeadHunterAI"
    }

    response = requests.get(url, headers=headers, timeout=20)

    if response.status_code != 200:
        print(f"[!] @{channel}: статус {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    posts = []

    for message in soup.select(".tgme_widget_message"):
        post_ref = message.get("data-post")

        if not post_ref or "/" not in post_ref:
            continue

        source, post_id = post_ref.split("/", 1)

        text_block = message.select_one(".tgme_widget_message_text")

        if not text_block:
            continue

        text = text_block.get_text("\n", strip=True)

        if not text:
            continue

        posts.append({
            "source": source,
            "post_id": post_id,
            "text": text,
            "url": f"https://t.me/{source}/{post_id}",
        })

    return posts


def analyze_post(post):
    text = post["text"]

    if not is_relevant(text):
        return None

    lead_id = make_lead_id(post["source"], post["post_id"], text)

    if is_seen(lead_id):
        return None

    score = calculate_score(text)

    if score < 5:
        return None

    category = detect_category(text)

    return {
        "lead_id": lead_id,
        "source": post["source"],
        "post_id": post["post_id"],
        "text": text,
        "url": post["url"],
        "score": score,
        "category": category,
        "price": suggest_price(text),
        "risks": detect_risks(text),
        "reply": generate_reply(text, category),
    }


def format_card(lead):
    score = lead["score"]

    if score >= 8:
        verdict = "🔥 сильная заявка, надо откликаться"
    else:
        if score >= 5:
            verdict = "🟡 средняя заявка, можно попробовать"
        else:
            verdict = "🔴 слабая заявка, осторожно"

    text = clean_text(lead["text"])
    reply = clean_text(lead["reply"], limit=1000)

    return (
        "<b>🔥 Найдена заявка</b>\n\n"
        f"<b>Источник:</b> @{html.escape(lead['source'])}\n"
        f"<b>Оценка:</b> {lead['score']}/10\n"
        f"<b>Вердикт:</b> {html.escape(verdict)}\n"
        f"<b>Категория:</b> {html.escape(lead['category'])}\n"
        f"<b>Цена:</b> {html.escape(lead['price'])}\n"
        f"<b>Риски:</b> {html.escape(lead['risks'])}\n\n"
        f"<b>Текст заявки:</b>\n{html.escape(text)}\n\n"
        f"<b>Готовый отклик:</b>\n<code>{html.escape(reply)}</code>\n\n"
        "<i>Открой заявку, скопируй отклик и отправь вручную.</i>"
    )

def send_message(text, keyboard=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": OWNER_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    if keyboard:
        payload["reply_markup"] = keyboard

    response = requests.post(url, json=payload, timeout=20)

    if response.status_code != 200:
        print("[!] Ошибка отправки:", response.text)



def send_lead(lead):
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🚀 Открыть заявку", "url": lead["url"]}
            ],
            [
                {"text": "✅ Подходит", "callback_data": f"good:{lead['lead_id']}"},
                {"text": "🗑 Мусор", "callback_data": f"trash:{lead['lead_id']}"},
            ],
            [
                {"text": "🚫 Бан канала", "callback_data": f"ban:{lead['source']}"}
            ],
            [
                {"text": "📌 Открыть канал", "url": f"https://t.me/{lead['source']}"}
            ],
        ]
    }

    send_message(format_card(lead), keyboard)


BOT_UPDATE_OFFSET = None
SCAN_INTERVAL_SECONDS = 300


def bot_api(method, payload=None, params=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    try:
        if payload is not None:
            response = requests.post(url, json=payload, timeout=20)
        else:
            response = requests.get(url, params=params or {}, timeout=20)

        if response.status_code != 200:
            print(f"[!] Bot API {method} error:", response.text)
            return None

        return response.json()

    except Exception as e:
        print(f"[!] Bot API {method} exception:", e)
        return None


def normalize_channel_name(raw):
    channel = raw.strip()
    channel = channel.replace("@", "")
    channel = channel.replace("https://t.me/s/", "")
    channel = channel.replace("http://t.me/s/", "")
    channel = channel.replace("https://t.me/", "")
    channel = channel.replace("http://t.me/", "")
    channel = channel.split("/")[0]
    channel = channel.strip()
    return channel


def save_channels(channels):
    clean = []
    seen = set()

    for ch in channels:
        ch = normalize_channel_name(ch)
        if not ch:
            continue
        if ch in seen:
            continue
        seen.add(ch)
        clean.append(ch)

    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        for ch in clean:
            f.write(ch + "\n")


def add_channel(channel):
    channel = normalize_channel_name(channel)

    if not channel:
        return False, "Пустое название канала."

    channels = load_channels()

    if channel in channels:
        return False, f"@{channel} уже есть в списке."

    channels.append(channel)
    save_channels(channels)

    return True, f"@{channel} добавлен в мониторинг."


def remove_channel(channel):
    channel = normalize_channel_name(channel)
    channels = load_channels()

    if channel not in channels:
        return False, f"@{channel} не найден в списке."

    channels = [ch for ch in channels if ch != channel]
    save_channels(channels)

    return True, f"@{channel} удалён из мониторинга."



def get_lead_from_db(lead_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT lead_id, source, text, url, score, category FROM leads WHERE lead_id = ?",
        (lead_id,)
    )

    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "lead_id": row[0],
        "source": row[1],
        "text": row[2],
        "url": row[3],
        "score": row[4],
        "category": row[5],
    }


def save_feedback(lead_id, action, source=None, text=None):
    lead = get_lead_from_db(lead_id)

    if lead:
        source = source or lead["source"]
        text = text or lead["text"]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO feedback
        (lead_id, source, action, text, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            lead_id,
            source or "",
            action,
            text or "",
            datetime.now().isoformat(timespec="seconds"),
        )
    )

    conn.commit()
    conn.close()


def get_feedback_count(action):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM feedback WHERE action = ?", (action,))
    count = cur.fetchone()[0]

    conn.close()
    return count



def get_stats_text():
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM leads")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT source) FROM leads")
        sources = cur.fetchone()[0]

        cur.execute("SELECT MAX(created_at) FROM leads")
        last = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM feedback WHERE action = 'good'")
        good = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM feedback WHERE action = 'trash'")
        trash = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM feedback WHERE action = 'ban'")
        banned = cur.fetchone()[0]

        conn.close()

        return (
            "📊 Статистика\n\n"
            f"Заявок в базе: {total}\n"
            f"Источников с заявками: {sources}\n"
            f"✅ Подходящих: {good}\n"
            f"🗑 Мусора: {trash}\n"
            f"🚫 Бан каналов: {banned}\n"
            f"Последняя заявка: {last or 'пока нет'}"
        )

    except Exception as e:
        return f"Не смог получить статистику: {e}"


def main_menu_keyboard():
    return {
        "keyboard": [
            [
                {"text": "🔎 Скан"},
                {"text": "📌 Каналы"},
            ],
            [
                {"text": "📊 Статистика"},
                {"text": "❓ Помощь"},
            ],
            [
                {"text": "➕ Добавить канал"},
                {"text": "➖ Удалить канал"},
            ],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


def help_text():
    return (
        "🤖 AI Lead Hunter\n\n"
        "Кнопки:\n"
        "🔎 Скан — запустить поиск заявок вручную\n"
        "📌 Каналы — показать список каналов\n"
        "📊 Статистика — посмотреть статистику\n"
        "➕ Добавить канал — инструкция по добавлению\n"
        "➖ Удалить канал — инструкция по удалению\n\n"
        "Команды также работают вручную:\n"
        "/scan — запустить скан\n"
        "/channels — показать каналы\n"
        "/add channelname — добавить канал\n"
        "/remove channelname — удалить канал\n"
        "/stats — статистика\n"
        "/help — помощь\n\n"
        "Примеры:\n"
        "/add workzavr\n"
        "/add https://t.me/theyseeku\n"
        "/remove freelancechoice"
    )


def is_owner_user(user_id):
    return str(user_id) == str(OWNER_ID)


def answer_callback(callback_id, text=None, alert=False):
    payload = {
        "callback_query_id": callback_id,
        "show_alert": alert,
    }

    if text:
        payload["text"] = text

    bot_api("answerCallbackQuery", payload=payload)


def delete_message(chat_id, message_id):
    bot_api("deleteMessage", payload={
        "chat_id": chat_id,
        "message_id": message_id,
    })




USER_STATE = {}


def set_user_state(user_id, state):
    USER_STATE[str(user_id)] = state


def get_user_state(user_id):
    return USER_STATE.get(str(user_id))


def clear_user_state(user_id):
    USER_STATE.pop(str(user_id), None)



def handle_text_command(message):
    chat_id = message["chat"]["id"]
    user_id = message.get("from", {}).get("id")
    text = message.get("text", "").strip()

    if not is_owner_user(user_id):
        bot_api("sendMessage", payload={
            "chat_id": chat_id,
            "text": "Доступ закрыт.",
        })
        return

    current_state = get_user_state(user_id)

    if text in ["/cancel", "❌ Отмена"]:
        clear_user_state(user_id)
        send_message("Ок, действие отменено.", main_menu_keyboard())
        return

    if current_state == "wait_add_channel":
        channel = normalize_channel_name(text)
        ok, msg = add_channel(channel)
        clear_user_state(user_id)
        send_message(("✅ " if ok else "⚠️ ") + msg, main_menu_keyboard())
        return

    if current_state == "wait_remove_channel":
        channel = normalize_channel_name(text)
        ok, msg = remove_channel(channel)
        clear_user_state(user_id)
        send_message(("✅ " if ok else "⚠️ ") + msg, main_menu_keyboard())
        return

    if text in ["/start", "/help", "❓ Помощь"]:
        send_message(help_text(), main_menu_keyboard())
        return

    if text in ["/channels", "📌 Каналы"]:
        channels = load_channels()

        if not channels:
            send_message("Список каналов пуст.", main_menu_keyboard())
            return

        lines = [f"{i + 1}. @{ch}" for i, ch in enumerate(channels)]
        send_message("📌 Каналы в мониторинге:\n\n" + "\n".join(lines), main_menu_keyboard())
        return

    if text in ["/stats", "📊 Статистика"]:
        send_message(get_stats_text(), main_menu_keyboard())
        return

    if text in ["/scan", "🔎 Скан"]:
        send_message("🔎 Запускаю ручной скан...", main_menu_keyboard())
        run_once()
        return

    if text in ["➕ Добавить канал"]:
        set_user_state(user_id, "wait_add_channel")
        send_message(
            "➕ Отправь username канала или ссылку.\n\n"
            "Примеры:\n"
            "<code>workzavr</code>\n"
            "<code>@workzavr</code>\n"
            "<code>https://t.me/workzavr</code>\n\n"
            "Важно: канал должен быть публичным.\n\n"
            "Для отмены напиши /cancel.",
            main_menu_keyboard()
        )
        return

    if text in ["➖ Удалить канал"]:
        channels = load_channels()

        if not channels:
            send_message("Список каналов пуст. Удалять нечего.", main_menu_keyboard())
            return

        lines = [f"{i + 1}. @{ch}" for i, ch in enumerate(channels)]

        set_user_state(user_id, "wait_remove_channel")
        send_message(
            "➖ Отправь username канала, который нужно удалить.\n\n"
            "Сейчас в списке:\n" + "\n".join(lines) +
            "\n\nДля отмены напиши /cancel.",
            main_menu_keyboard()
        )
        return

    if text.startswith("/add "):
        channel = text.replace("/add", "", 1).strip()
        ok, msg = add_channel(channel)
        send_message(("✅ " if ok else "⚠️ ") + msg, main_menu_keyboard())
        return

    if text.startswith("/remove "):
        channel = text.replace("/remove", "", 1).strip()
        ok, msg = remove_channel(channel)
        send_message(("✅ " if ok else "⚠️ ") + msg, main_menu_keyboard())
        return

    send_message(
        "Не понял команду. Нажми кнопку ❓ Помощь.",
        main_menu_keyboard()
    )



def handle_callback(callback):
    callback_id = callback["id"]
    user_id = callback.get("from", {}).get("id")
    data = callback.get("data", "")

    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")

    if not is_owner_user(user_id):
        answer_callback(callback_id, "Доступ закрыт.", alert=True)
        return

    if data.startswith("good:"):
        lead_id = data.replace("good:", "", 1).strip()
        save_feedback(lead_id, "good")

        answer_callback(callback_id, "Сохранил как подходящую заявку.")
        send_message(
            "✅ Заявка сохранена как подходящая.\n\n"
            "Эти отметки потом используем для обучения фильтра."
        )
        return

    if data.startswith("trash:"):
        lead_id = data.replace("trash:", "", 1).strip()
        save_feedback(lead_id, "trash")

        answer_callback(callback_id, "Сохранил как мусор.")
        if chat_id and message_id:
            delete_message(chat_id, message_id)
        return

    if data.startswith("ban:"):
        source = data.replace("ban:", "", 1).strip()
        ok, msg = remove_channel(source)

        save_feedback("channel:" + source, "ban", source=source, text="channel banned")

        answer_callback(callback_id, "Канал убран из мониторинга.")
        if chat_id and message_id:
            delete_message(chat_id, message_id)

        send_message(("🚫 " if ok else "⚠️ ") + msg)
        return

    answer_callback(callback_id)


def discard_old_updates():
    global BOT_UPDATE_OFFSET

    result = bot_api("getUpdates", params={
        "timeout": 1,
        "allowed_updates": '["message","callback_query"]',
    })

    if not result or "result" not in result:
        BOT_UPDATE_OFFSET = 0
        return

    updates = result["result"]

    if updates:
        BOT_UPDATE_OFFSET = max(update["update_id"] for update in updates) + 1
    else:
        BOT_UPDATE_OFFSET = 0


def process_updates():
    global BOT_UPDATE_OFFSET

    params = {
        "timeout": 1,
        "offset": BOT_UPDATE_OFFSET or 0,
        "allowed_updates": '["message","callback_query"]',
    }

    result = bot_api("getUpdates", params=params)

    if not result or "result" not in result:
        return

    for update in result["result"]:
        BOT_UPDATE_OFFSET = update["update_id"] + 1

        if "message" in update:
            handle_text_command(update["message"])

        elif "callback_query" in update:
            handle_callback(update["callback_query"])


def run_once():
    channels = load_channels()

    total_posts = 0
    sent_count = 0
    channel_lines = []

    print(f"[*] Каналов в списке: {len(channels)}")

    for channel in channels:
        print(f"[*] Проверяю @{channel}")

        try:
            posts = parse_channel(channel)
        except Exception as e:
            print(f"[!] Ошибка @{channel}: {e}")
            channel_lines.append(f"@{channel}: ошибка")
            continue

        total_posts += len(posts)
        print(f"    найдено постов: {len(posts)}")

        before_sent = sent_count

        for post in posts:
            lead = analyze_post(post)

            if not lead:
                continue

            save_lead(lead)
            send_lead(lead)
            sent_count += 1

            print(f"    [+] заявка: @{lead['source']}/{lead['post_id']}, score={lead['score']}")

        channel_sent = sent_count - before_sent
        channel_lines.append(f"@{channel}: постов {len(posts)}, заявок {channel_sent}")

    print(f"[*] Итог: постов={total_posts}, отправлено заявок={sent_count}")

    report = (
        "📊 Скан завершён\n\n"
        f"Проверено постов: {total_posts}\n"
        f"Найдено заявок: {sent_count}\n\n"
        "Каналы:\n" + "\n".join(channel_lines)
    )

    send_message(report)

    return sent_count



def main():
    init_db()
    discard_old_updates()

    send_message(
        "✅ AI Lead Hunter запущен.\\n\\n"
        "Управление теперь доступно кнопками снизу. Нажми ❓ Помощь.",
        main_menu_keyboard()
    )

    last_scan = 0

    while True:
        process_updates()

        now = time.time()

        if now - last_scan >= SCAN_INTERVAL_SECONDS:
            run_once()
            last_scan = now

        time.sleep(2)


if __name__ == "__main__":
    main()
