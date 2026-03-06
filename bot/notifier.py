import asyncio
import os
from pathlib import Path

from telegram import Bot


def load_env(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        raise FileNotFoundError("Файл .env не найден")

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


async def send_test_message(chat_id: str, text: str) -> None:
    load_env()
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise ValueError("BOT_TOKEN не найден в .env")

    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=text)


if __name__ == "__main__":
    user_chat_id = input("Вставь chat_id: ").strip()
    asyncio.run(send_test_message(user_chat_id, "Тест. Бот подключен и работает."))
