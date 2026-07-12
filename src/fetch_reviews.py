"""抓取App Store中国区评论RSS，落地当日原始快照。

数据源：https://itunes.apple.com/cn/rss/customerreviews/page={p}/id={app_id}/sortby=mostrecent/json
每App最多10页×50条。单App失败不拖垮整体，失败记录进快照。

用法：python src/fetch_reviews.py
产出：data/raw/YYYY-MM-DD.json
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

APPS = {
    "1296749505": "瑞幸咖啡",
    "499819758": "星巴克中国",
    "1661236690": "库迪咖啡",
    "1504835619": "蜜雪冰城",
    "1412534170": "喜茶GO",
}

UA = "Mozilla/5.0 (compatible; voc-radar/1.0)"
MAX_PAGES = 10


def fetch_json(url: str, retries: int = 2, timeout: int = 30) -> dict:
    last_err: Exception | None = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 单页失败重试，最终失败上抛
            last_err = e
            time.sleep(2)
    raise RuntimeError(f"fetch failed: {url}: {last_err}")


def parse_entry(e: dict) -> dict | None:
    """RSS entry -> 标准化评论。缺关键字段的条目丢弃。"""
    try:
        return {
            "review_id": e["id"]["label"],
            "rating": int(e["im:rating"]["label"]),
            "version": e["im:version"]["label"],
            "date": e["updated"]["label"][:10],
            "title": e["title"]["label"],
            "content": e["content"]["label"][:500],
        }
    except (KeyError, ValueError):
        return None


def fetch_app(app_id: str) -> list[dict]:
    reviews: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        url = (f"https://itunes.apple.com/cn/rss/customerreviews/"
               f"page={page}/id={app_id}/sortby=mostrecent/json")
        data = fetch_json(url)
        entries = data.get("feed", {}).get("entry", [])
        if isinstance(entries, dict):   # 单条时RSS返回dict而非list
            entries = [entries]
        parsed = [r for r in (parse_entry(e) for e in entries) if r]
        if not parsed:
            break
        reviews.extend(parsed)
        time.sleep(0.8)
    return reviews


def main() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "apps": {},
        "failed_apps": [],
    }
    for app_id, name in APPS.items():
        try:
            reviews = fetch_app(app_id)
            snapshot["apps"][app_id] = {"name": name, "reviews": reviews}
            print(f"[ok] {name}: {len(reviews)} reviews")
        except Exception as e:  # noqa: BLE001 单App失败不拖垮整体
            snapshot["failed_apps"].append({"app_id": app_id, "name": name, "error": str(e)})
            print(f"[fail] {name}: {e}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{today}.json"
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(v["reviews"]) for v in snapshot["apps"].values())
    print(f"snapshot -> {out} （{total}条，失败{len(snapshot['failed_apps'])}个App）")


if __name__ == "__main__":
    main()
