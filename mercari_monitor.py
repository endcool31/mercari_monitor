import asyncio
from datetime import datetime
import json
import os
from dotenv import load_dotenv
from mercapi import Mercapi
import requests

load_dotenv()

# ==================== 設定讀取 ====================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
KEYWORD = os.getenv("MONITOR_KEYWORD", "FGO パーシヴァル アクリルスタンド")
MIN_PRICE = int(os.getenv("MIN_PRICE", "0"))
MAX_PRICE = int(os.getenv("MAX_PRICE", "99999999"))

# 負向詞排除名單
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
    """發送新商品通知卡片"""
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


def send_system_message(content):
    """發送系統狀態通知"""
    if not DISCORD_WEBHOOK_URL or "discord.com" not in DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": content},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
    except Exception as e:
        print(f"發送系統訊息失敗: {e}")


async def search_mercari_async(keyword):
    """使用 mercapi 模擬動態簽章進行搜尋"""
    m = Mercapi()
    items = []
    try:
        results = await m.search(keyword)
        for item in results.items:
            price = int(item.price) if item.price else 0
            name = item.name or ""
            item_id = getattr(item, "id_", getattr(item, "id", ""))

            # 價格範圍與負向詞過濾
            if not (MIN_PRICE <= price <= MAX_PRICE):
                continue
            if any(bad_word in name for bad_word in EXCLUDE_WORDS):
                continue

            # 取得縮圖
            thumb = ""
            if hasattr(item, "thumbnails") and item.thumbnails:
                thumb = item.thumbnails[0]
            elif hasattr(item, "thumbnail") and item.thumbnail:
                thumb = item.thumbnail

            items.append(
                {
                    "id": item_id,
                    "name": name,
                    "price": price,
                    "thumbnail": thumb,
                    "status": "販售中",
                }
            )
        return items
    except Exception as e:
        print(f"Mercari 搜尋抓取失敗: {e}")
        return []


def run_once():
    seen_ids = load_seen_items()
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] 開始巡檢：{KEYWORD} (已記錄商品數: {len(seen_ids)})"
    )

    items = asyncio.run(search_mercari_async(KEYWORD))
    new_items_count = 0
    is_first_run = len(seen_ids) == 0

    for item in reversed(items):
        item_id = item["id"]
        if item_id and item_id not in seen_ids:
            seen_ids.add(item_id)
            save_seen_item(item_id)
            new_items_count += 1

            if not is_first_run:
                print(f"推播新商品: {item['name']} (¥{item['price']:,})")
                send_discord_notification(item)

    if is_first_run:
        msg = f"✅ **Mercari 監控已重新啟動！**\n• 監控關鍵字：`{KEYWORD}`\n• 成功鎖定現有 **{len(items)}** 件歷史商品！後續有新上架將立即推播。"
        print(msg)
        send_system_message(msg)
    else:
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] 檢查完成，本次新增 {new_items_count} 件"
        )


if __name__ == "__main__":
    run_once()
