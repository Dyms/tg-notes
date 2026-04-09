import asyncio
import os
import re
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.extensions import html

# --- КОНФИГУРАЦИЯ ---
api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
channel = os.environ["TG_CHANNEL"]
session_str = os.environ.get("TG_SESSION")

WP_BASE_URL = "https://dbogatov.ru/wp-json/wp/v2"
WP_USER = os.environ["WP_USER"]
WP_PASS = os.environ["WP_PASS"]
FB_FOLDER_ID = 15 # Убедись, что ID верный

client = TelegramClient(StringSession(session_str), api_id, api_hash)
auth = (WP_USER, WP_PASS)

async def upload_to_wp_media(msg):
    file_path = await msg.download_media()
    if not file_path: return None, None
    filename = os.path.basename(file_path)
    
    with open(file_path, 'rb') as f:
        headers = {'Content-Disposition': f'attachment; filename={filename}'}
        res = requests.post(f"{WP_BASE_URL}/media", auth=auth, files={'file': f}, headers=headers)
    
    if os.path.exists(file_path): os.remove(file_path)

    if res.status_code == 201:
        media_data = res.json()
        media_id = media_data['id']
        
        # Попытка переместить в FileBird с расширенным логированием
        fb_url = "https://dbogatov.ru/wp-json/filebird/v1/move-files"
        fb_res = requests.post(fb_url, auth=auth, json={"folder_id": FB_FOLDER_ID, "ids": [media_id]})
        
        if fb_res.status_code != 200:
            print(f"FileBird API Error: {fb_res.text}")
        else:
            print(f"Файл {filename} успешно перемещен в папку ID:{FB_FOLDER_ID}")
            
        return media_id, media_data['source_url']
    return None, None

async def main():
    async with client:
        messages = []
        async for msg in client.iter_messages(channel, limit=10):
            messages.append(msg)

        groups = {}
        for msg in messages:
            if not msg.message and not msg.media: continue
            gid = msg.grouped_id if msg.grouped_id else f"single-{msg.id}"
            
            if gid not in groups:
                # Генерируем HTML из Telegram-сущностей
                raw_html = html.unparse(msg.message, msg.entities) if msg.message else ""
                groups[gid] = {"id": msg.id, "text": raw_html, "media": [], "date": msg.date}
            if msg.media:
                groups[gid]["media"].append(msg)

        for gid, data in groups.items():
            slug = f"tg-{data['id']}"
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

            # source_link
            footer = f'<div class="tg-source" style="margin-top:20px; border-top:1px solid #eee; padding-top:10px;"><a href="https://t.me/{channel}/{data["id"]}">Оригинал в Telegram</a></div>'
            
            # ВАЖНО: white-space: pre-wrap сохранит переносы строк и форматирование кода
            full_content = (
                f"{media_html}"
                f"<div class='tg-body' style='white-space: pre-wrap; font-family: inherit;'>"
                f"{data['text']}"
                f"</div>{footer}"
            )

            title_clean = re.sub('<[^<]+?>', '', data["text"]).split('\n')[0][:60].strip() or "Заметка"
            
            payload = {
                "title": title_clean,
                "content": full_content,
                "status": "publish",
                "slug": slug,
                "featured_media": featured_image_id,
                "date": data["date"].isoformat()
            }
            requests.post(f"{WP_BASE_URL}/tg_post", auth=auth, json=payload)
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
