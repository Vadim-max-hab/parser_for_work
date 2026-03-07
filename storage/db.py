from pathlib import Path


KEYWORDS_FILE = Path("storage/keywords.txt")
SEEN_URLS_FILE = Path("storage/seen_urls.txt")


DEFAULT_KEYWORDS = [
    "инфографика",
    "инфографика wb",
    "дизайн карточки",
    "карточка товара",
    "wildberries дизайн",
    "ozon дизайн",
]


def ensure_keywords_file() -> None:
    KEYWORDS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not KEYWORDS_FILE.exists():
        KEYWORDS_FILE.write_text(
            "\n".join(DEFAULT_KEYWORDS) + "\n",
            encoding="utf-8",
        )


def get_keywords() -> list[str]:
    ensure_keywords_file()

    lines = KEYWORDS_FILE.read_text(encoding="utf-8").splitlines()
    keywords = []

    for line in lines:
        value = line.strip()
        if value and value not in keywords:
            keywords.append(value)

    return keywords


def add_keyword(keyword: str) -> bool:
    keyword = keyword.strip()
    if not keyword:
        return False

    keywords = get_keywords()

    if keyword in keywords:
        return False

    keywords.append(keyword)
    KEYWORDS_FILE.write_text("\n".join(keywords) + "\n", encoding="utf-8")
    return True


def remove_keyword(keyword: str) -> bool:
    keyword = keyword.strip()
    if not keyword:
        return False

    keywords = get_keywords()

    if keyword not in keywords:
        return False

    keywords.remove(keyword)
    KEYWORDS_FILE.write_text("\n".join(keywords) + "\n", encoding="utf-8")
    return True


def ensure_seen_urls_file() -> None:
    SEEN_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not SEEN_URLS_FILE.exists():
        SEEN_URLS_FILE.write_text("", encoding="utf-8")


def get_seen_urls() -> set[str]:
    ensure_seen_urls_file()

    lines = SEEN_URLS_FILE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip()}


def is_seen_url(url: str) -> bool:
    return url.strip() in get_seen_urls()


def add_seen_url(url: str) -> bool:
    url = url.strip()
    if not url:
        return False

    seen_urls = get_seen_urls()

    if url in seen_urls:
        return False

    with SEEN_URLS_FILE.open("a", encoding="utf-8") as file:
        file.write(url + "\n")

    return True
