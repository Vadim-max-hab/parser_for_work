import asyncio
import os
from pathlib import Path

from telegram import Bot

from parsers.freelance.kwork import search_projects
from storage.db import add_seen_url, get_keywords, get_seen_urls


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


async def send_message(text: str) -> None:
    load_env()

    token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")

    if not token:
        raise ValueError("BOT_TOKEN не найден")

    if not chat_id:
        raise ValueError("CHAT_ID не найден")

    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=text)


async def check_projects() -> str:
    queries = get_keywords()

    if not queries:
        return "Список ключевых слов пуст."

    seen_urls = get_seen_urls()
    new_projects = []
    local_seen = set()

    for query in queries:
        try:
            result = search_projects(query)
        except Exception:
            continue

        for item in result:
            url = item.get("url", "").strip()
            title = item.get("title", "Без названия").strip()

            if not url:
                continue

            if url in seen_urls:
                continue

            if url in local_seen:
                continue

            local_seen.add(url)

            new_projects.append(
                {
                    "title": title,
                    "url": url,
                    "query": query,
                }
            )

    if not new_projects:
        return "Новых результатов не найдено."

    for item in new_projects:
        add_seen_url(item["url"])

    lines = [f"Найдено новых результатов: {len(new_projects)}", ""]

    for item in new_projects[:10]:
        lines.append(f"• {item['title']}")
        lines.append(item["url"])
        lines.append(f"Запрос: {item['query']}")
        lines.append("")

    if len(new_projects) > 10:
        lines.append(f"И ещё: {len(new_projects) - 10}")

    return "\n".join(lines)


async def runner() -> None:
    while True:
        try:
            result = await check_projects()

            if result != "Новых результатов не найдено.":
                await send_message(result)

        except Exception as e:
            await send_message(f"Ошибка в мониторинге: {e}")

        await asyncio.sleep(120)


if __name__ == "__main__":
    asyncio.run(runner())

