import asyncio
import os
import re
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.extensions import html

# --- НАСТРОЙКИ ---
api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
channel = os.environ["TG_CHANNEL"]
session_str = os.environ.get("TG_SESSION")

WP_BASE_URL = "https://dbogatov.ru/wp-json/wp/v2"
WP_USER = os.environ["WP_USER"]
WP_PASS = os.environ["WP_PASS"]
FB_FOLDER_ID = 1 # ЗАМЕНИТЕ НА ВАШ ID ИЗ ШАГА 2

client = TelegramClient(StringSession(session_str), api_id, api_hash)
auth = (WP_USER, WP_PASS)

async def upload_to_wp_media(msg):
    file_path = await msg.download_media()
    if not file_path: return None, None
    filename = os.path.basename(file_path)
    is_video = filename.lower().endswith(('.mp4', '.mov', '.avi'))
    
    with open(file_path, 'rb') as f:
        headers = {'Content-Disposition': f'attachment; filename={filename}'}
        res = requests.post(f"{WP_BASE_URL}/media", auth=auth, files={'file': f}, headers=headers)
    
    if os.path.exists(file_path): os.remove(file_path)
    
    if res.status_code == 201:
        data = res.json()
        media_id = data['id']
        # Привязка к папке FileBird
        requests.post(f"https://dbogatov.ru/wp-json/filebird/v1/move-files", 
                      auth=auth, json={"folder_id": FB_FOLDER_ID, "ids": [media_id]})
        return media_id, data['source_url']
    return None, None

async def main():
    async with client:
        messages = []
        async for msg in client.iter_messages(channel, limit=15):
            messages.append(msg)

        groups = {}
        for msg in messages:
            if not msg.message and not msg.media: continue
            gid = msg.grouped_id if msg.grouped_id else f"single-{msg.id}"
            if gid not in groups:
                # Сохраняем форматирование
                groups[gid] = {"id": msg.id, "text": html.unparse(msg.message, msg.entities) if msg.message else "", "media": [], "date": msg.date}
            if msg.media: groups[gid]["media"].append(msg)

        for gid, data in groups.items():
            slug = f"tg-{data['id']}"
            # Проверка дубликатов постов
            check = requests.get(f"{WP_BASE_URL}/tg_post", params={"slug": slug}, auth=auth)
            if check.status_code == 200 and len(check.json()) > 0: continue

            media_html = ""
            featured_image_id = None

            for m in data["media"]:
                m_id, m_url = await upload_to_wp_media(m)
                if m_url:
                    if m.video:
                        media_html += f'<video controls style="width:100%; border-radius:15px; margin-bottom:20px;"><source src="{m_url}" type="video/mp4"></video>'
                    else:
                        media_html += f'<img src="{m_url}" style="width:100%; border-radius:15px; margin-bottom:20px;">'
                        if not featured_image_id: featured_image_id = m_id

            title_clean = re.sub('<[^<]+?>', '', data["text"]).split('\n')[0][:60].strip() or f"Post {data['id']}"
            
            payload = {
                "title": title_clean,
                "content": f"{media_html}<div class='tg-body'>{data['text']}</div>",
                "status": "publish",
                "slug": slug,
                "featured_media": featured_image_id,
                "date": data["date"].isoformat()
            }
            requests.post(f"{WP_BASE_URL}/tg_post", auth=auth, json=payload)
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
