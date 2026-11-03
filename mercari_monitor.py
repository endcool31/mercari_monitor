from datetime import datetime
import json
import os
from dotenv import load_dotenv
import requests

# 載入環境變數（本機開發用 .env，GitHub Actions 會讀取 Secrets）
load_dotenv()

# ==================== 參數讀取 ====================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
KEYWORD = os.getenv("MONITOR_KEYWORD", "PS5 主機")
MIN_PRICE = int(os.getenv("MIN_PRICE", "0"))
MAX_PRICE = int(os.getenv("MAX_PRICE", "99999999"))

# 負向詞排除名單（標題包含任一詞即忽略）
EXCLUDE_WORDS = ["ジャンク", "故障", "訳あり", "箱のみ", "説明書のみ"]

SEEN_ITEMS_FILE = "seen_items.txt"
# =================================================


def load_seen_items():
    try:
        with open(SEEN_ITEMS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()


def save_seen_item(item_id):
    with open(SEEN_ITEMS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{item_id}\n")


def send_discord_notification(item):
    if not DISCORD_WEBHOOK_URL or "discord.com" not in DISCORD_WEBHOOK_URL:
        print(f"[模擬通知] 新商品: {item['name']} - ¥{item['price']:,}")
        return

    payload = {
        "embeds": [
            {
                "title": f"🔔 發現新商品：{item['name']}",
                "url": f"https://jp.mercari.com/item/{item['id']}",
                "color": 15158332,
                "fields": [
                    {
                        "name": "價格",
                        "value": f"¥{int(item['price']):,}",
                        "inline": True,
                    },
                    {"name": "狀態", "value": item["status"], "inline": True},
                ],
                "image": {"url": item.get("thumbnail", "")},
                "footer": {
                    "text": f"Mercari Monitor • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                },
            }
        ]
    }
    try:
        res = requests.post(
            DISCORD_WEBHOOK_URL,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        res.raise_for_status()
    except Exception as e:
        print(f"發送 Discord 通知失敗: {e}")


def search_mercari(keyword):
    api_url = "https://api.mercari.jp/v2/entities:search"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://jp.mercari.com",
        "Referer": "https://jp.mercari.com/",
    }

    payload = {
        "pageSize": 30,
        "searchCondition": {
            "keyword": keyword,
            "sort": "SORT_CREATED_TIME",
            "order": "ORDER_DESC",
            "status": ["STATUS_ON_SALE"],
        },
    }

    try:
        response = requests.post(
            api_url, headers=headers, json=payload, timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            items = []
            for item in data.get("items", []):
                price = int(item.get("price", 0))
                name = item.get("name", "")

                if not (MIN_PRICE <= price <= MAX_PRICE):
                    continue
                if any(bad_word in name for bad_word in EXCLUDE_WORDS):
                    continue

                items.append(
                    {
                        "id": item.get("id"),
                        "name": name,
                        "price": price,
                        "thumbnail": item.get("thumbnails", [""])[0]
                        if item.get("thumbnails")
                        else "",
                        "status": "販售中"
                        if item.get("status") == "STATUS_ON_SALE"
                        else "已售出",
                    }
                )
            return items
        else:
            print(f"Mercari API 回應異常，HTTP 狀態碼: {response.status_code}")
            return []
    except Exception as e:
        print(f"網路連線錯誤: {e}")
        return []


def run_once():
    """執行單趟檢查後直接結束程式"""
    seen_ids = load_seen_items()
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] 開始單次檢查：{KEYWORD} (歷史記錄: {len(seen_ids)} 件)"
    )

    items = search_mercari(KEYWORD)
    new_items_count = 0

    # 如果是第一次執行（檔案是空的），先記錄現有項目但不推播，避免一次跳出幾十筆訊息洗版
    is_first_run = len(seen_ids) == 0

    for item in reversed(items):
        item_id = item["id"]
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            save_seen_item(item_id)
            new_items_count += 1

            if not is_first_run:
                print(f"推播新商品: {item['name']} (¥{item['price']:,})")
                send_discord_notification(item)

    if is_first_run:
        print(
            f"初始化完成：已寫入現有 {len(items)} 件商品至清單，下回排程有更新將立即通知。"
        )
    else:
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] 檢查完成，本次發現 {new_items_count} 件新商品。"
        )


if __name__ == "__main__":
    run_once()
