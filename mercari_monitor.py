import json
import time
from datetime import datetime
import requests

# ==================== 設定區塊 ====================
# 1. 填入你的 Discord Webhook URL（也可用 Telegram 或 LINE 替換）
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL_HERE"

# 2. 監控的關鍵字與篩選條件
KEYWORD = "PS5 主機"  # 請輸入想監控的日文或中文關鍵字
CHECK_INTERVAL_SECONDS = 180  # 每幾秒檢查一次（建議不要低於 60 秒，避免被鎖 IP）

# 3. 狀態記錄（記錄已通知過的商品 ID，避免重複洗版）
SEEN_ITEMS_FILE = "seen_items.txt"
# =================================================


def load_seen_items():
    """讀取已經發過通知的商品 ID"""
    try:
        with open(SEEN_ITEMS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()


def save_seen_item(item_id):
    """保存新通知過的商品 ID"""
    with open(SEEN_ITEMS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{item_id}\n")


def send_discord_notification(item):
    """發送 Discord 嵌入式卡片通知"""
    if not DISCORD_WEBHOOK_URL or "YOUR_DISCORD" in DISCORD_WEBHOOK_URL:
        print(f"[模擬通知] 發現新商品: {item['name']} - ¥{item['price']}")
        return

    payload = {
        "embeds": [
            {
                "title": f"🔔 發現新商品：{item['name']}",
                "url": f"https://jp.mercari.com/item/{item['id']}",
                "color": 15158332,  # Mercari 紅色系
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
        print(f"發送通知失敗: {e}")


def search_mercari(keyword):
    """呼叫 Mercari 搜尋 API 取得最新上架商品"""
    api_url = "https://api.mercari.jp/v2/entities:search"

    # 模擬瀏覽器 Header，Mercari 需要特定的 App-Version 或 DPoP，一般搜尋可用通用 Header
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

    # 搜尋條件：依最新上架排序 (ORDER_CREATED_TIME / SORT_SCORE)
    payload = {
        "userId": "",
        "pageSize": 20,
        "pageToken": "",
        "searchSessionId": "",
        "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
        "searchCondition": {
            "keyword": keyword,
            "sort": "SORT_CREATED_TIME",  # 按上架時間排序
            "order": "ORDER_DESC",  # 降序（最新在上）
            "status": ["STATUS_ON_SALE"],  # 只看販售中
        },
        "default японCondition": {},
        "serviceFrom": "surugaya",
    }

    try:
        response = requests.post(
            api_url, headers=headers, json=payload, timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            items = []
            for item in data.get("items", []):
                items.append(
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "price": item.get("price"),
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
            print(
                f"搜尋失敗，HTTP 狀態碼: {response.status_code}（可能遇到 Cloudflare 驗證）"
            )
            return []
    except Exception as e:
        print(f"網路連線錯誤: {e}")
        return []


def run_monitor():
    seen_ids = load_seen_items()
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] 監控啟動，關鍵字：'{KEYWORD}'"
    )
    print(f"已記錄歷史商品數：{len(seen_ids)}")

    is_first_run = len(seen_ids) == 0

    while True:
        try:
            items = search_mercari(KEYWORD)
            new_items_found = 0

            # 逆序比對（從較舊到最新發送，維持時間順序）
            for item in reversed(items):
                item_id = item["id"]
                if item_id not in seen_ids:
                    seen_ids.add(item_id)
                    save_seen_item(item_id)
                    new_items_found += 1

                    # 第一次啟動腳本時只記錄商品，不洗版發通知
                    if not is_first_run:
                        print(f"發現新上架: {item['name']} (¥{item['price']})")
                        send_discord_notification(item)

            if is_first_run:
                print(
                    f"初始化完成，已暫存當前前 {len(items)} 筆商品，之後有新商品將會推播通知。"
                )
                is_first_run = False
            else:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] 巡檢完成，新增 {new_items_found} 件商品"
                )

        except Exception as e:
            print(f"監控迴圈出錯: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_monitor()
