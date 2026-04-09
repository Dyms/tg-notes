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
        data = res.json()
        return data['id'], data['source_url']
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
                # Получаем чистый текст для заголовка
                raw_text = msg.message if msg.message else ""
                first_line = raw_text.split('\n')[0].strip()
                # Убираем HTML и ограничиваем длину заголовка
                clean_title = re.sub('<[^<]+?>', '', first_line)[:60]
                
                # Формируем HTML для контента
                raw_html = html.unparse(msg.message, msg.entities) if msg.message else ""
                formatted_html = raw_html.replace('\n', '<br />')
                
                groups[gid] = {
                    "id": msg.id, 
                    "title": clean_title or f"Post {msg.id}",
                    "text": formatted_html, 
                    "media": [], 
                    "date": msg.date
                }
            if msg.media:
                groups[gid]["media"].append(msg)

        for gid, data in groups.items():
            slug = f"tg-{data['id']}"
            check = requests.get(f"{WP_BASE_URL}/tg_post", params={"slug": slug}, auth=auth)
            if check.status_code == 200 and len(check.json()) > 0: continue

            media_html = ""
            featured_image_id = None
            uploaded_ids = []

            for m in data["media"]:
                m_id, m_url = await upload_to_wp_media(m)
                if m_url:
                    uploaded_ids.append(m_id)
                    if m.video:
                        media_html += f'<video controls style="width:100%; border-radius:15px; margin-bottom:20px;"><source src="{m_url}" type="video/mp4"></video>'
                    else:
                        media_html += f'<img src="{m_url}" style="width:100%; border-radius:15px; margin-bottom:20px;">'
                        if not featured_image_id: featured_image_id = m_id

            source_url = f"https://t.me/{channel}/{data['id']}"
            footer = f'<div class="tg-source"><a href="{source_url}" target="_blank">Original Telegram Post</a></div>'
            
            payload = {
                "title": data["title"],
                "content": f"{media_html}<div class='tg-body'>{data['text']}</div>{footer}",
                "status": "publish",
                "slug": slug,
                "featured_media": featured_image_id,
                "date": data["date"].isoformat()
            }
            
            post_res = requests.post(f"{WP_BASE_URL}/tg_post", auth=auth, json=payload)
            if post_res.status_code == 201:
                post_id = post_res.json()['id']
                for m_id in uploaded_ids:
                    requests.post(f"{WP_BASE_URL}/media/{m_id}", auth=auth, json={"post": post_id})
                print(f"Done: {slug}")

            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
