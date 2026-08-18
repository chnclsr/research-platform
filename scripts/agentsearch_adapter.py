"""AgentSearch-compatible facade over a plain SearXNG instance."""

import os

import httpx
import uvicorn
from fastapi import FastAPI

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://host.docker.internal:3939").rstrip("/")
ADAPTER_PORT = int(os.environ.get("ADAPTER_PORT", "3940"))
MAX_PAGES = 5

app = FastAPI()
client = httpx.AsyncClient(timeout=30.0)


@app.get("/health")
async def health() -> dict:
    try:
        response = await client.get(f"{SEARXNG_URL}/healthz", timeout=5.0)
        upstream = "ok" if response.is_success else "degraded"
    except Exception:
        upstream = "unreachable"
    return {"status": "ok", "searxng": upstream}


@app.get("/search")
async def search(
    q: str, count: int = 20, mode: str = "general", domain: str | None = None
) -> dict:
    query = f"{q} site:{domain}" if domain else q
    categories = "news" if mode == "news" else "general"
    results: list[dict] = []
    seen: set[str] = set()

    for pageno in range(1, MAX_PAGES + 1):
        try:
            response = await client.get(
                f"{SEARXNG_URL}/search",
                params={
                    "q": query,
                    "format": "json",
                    "categories": categories,
                    "pageno": pageno,
                },
            )
            response.raise_for_status()
            rows = response.json().get("results", [])
        except Exception:
            break
        if not rows:
            break
        for row in rows:
            url = row.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            results.append(
                {
                    "title": row.get("title") or "",
                    "url": url,
                    "snippet": row.get("content") or "",
                    "engines": row.get("engines") or [],
                }
            )
        if len(results) >= count:
            break

    return {"results": results[:count]}


@app.get("/read")
async def read(url: str, max_chars: int = 100000) -> dict:
    # SearXNG has no content-read API. Reporting failure makes acquisition fall through
    # to crawl4ai, which renders pages the platform's plain-HTTP fetch already failed on.
    return {"success": False}


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=ADAPTER_PORT)


if __name__ == "__main__":
    main()
