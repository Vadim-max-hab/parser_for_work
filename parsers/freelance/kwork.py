import requests
from bs4 import BeautifulSoup


SEARCH_URL = "https://kwork.ru/projects?fc=1&keyword={query}"


def search_projects(query: str) -> list[dict]:
    url = SEARCH_URL.format(query=query)
    headers = {
        "User-Agent": "Mozilla/5.0 (Android 15; Mobile) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    }

    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    links = soup.find_all("a", href=True)

    for link in links:
        href = link.get("href", "")
        text = link.get_text(" ", strip=True)

        if not href or not text:
            continue

        if "/projects/" not in href:
            continue

        if href.startswith("/"):
            href = f"https://kwork.ru{href}"

        results.append({
            "title": text[:200],
            "url": href
        })

    unique = []
    seen = set()

    for item in results:
        key = item["url"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique[:10]
