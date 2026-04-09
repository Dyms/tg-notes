import asyncio
import os
import re
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.extensions import html

# --- КОНФИГУРАЦИЯ (через Environment Variables) ---
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
    """Загружает файл в медиабиблиотеку WordPress."""
    file_path = await msg.download_media()
    if not file_path:
        return None, None
    
    filename = os.path.basename(file_path)
    
    with open(file_path, 'rb') as f:
        headers = {'Content-Disposition': f'attachment; filename={filename}'}
        res = requests.post(f"{WP_BASE_URL}/media", auth=auth, files={'file': f}, headers=headers)
    
    if os.path.exists(file_path):
        os.remove(file_path)

    if res.status_code == 201:
        data = res.json()
        return data['id'], data['source_url']
    return None, None

async def main():
    async with client:
        messages = []
        # Загружаем последние 10 сообщений
        async for msg in client.iter_messages(channel, limit=10):
            messages.append(msg)

        groups = {}
        for msg in messages:
            if not msg.message and not msg.media:
                continue
            
            # Группируем медиа по grouped_id (альбомы)
            gid = msg.grouped_id if msg.grouped_id else f"single-{msg.id}"
            
            if gid not in groups:
                # Получаем HTML-разметку из Telegram
                raw_html = html.unparse(msg.message, msg.entities) if msg.message else ""
                
                # ФИКС ФОРМАТИРОВАНИЯ: Заменяем переносы строк на <br />, 
                # чтобы текст не слипался в ленте Avada
                formatted_text = raw_html.replace('\n', '<br />')
                
                groups[gid] = {
                    "id": msg.id, 
                    "text": formatted_text, 
                    "media": [], 
                    "date": msg.date
                }
            
            if msg.media:
                groups[gid]["media"].append(msg)

        for gid, data in groups.items():
            slug = f"tg-{data['id']}"
            
            # Проверяем, существует ли уже такой пост
            check = requests.get(f"{WP_BASE_URL}/tg_post", params={"slug": slug}, auth=auth)
            if check.status_code == 200 and len(check.json()) > 0:
                continue

            media_html = ""
            featured_image_id = None
            uploaded_ids = []

            # Обработка вложений
            for m in data["media"]:
                m_id, m_url = await upload_to_wp_media(m)
                if m_url:
                    uploaded_ids.append(m_id)
                    if m.video:
                        media_html += f'<video controls style="width:100%; border-radius:15px; margin-bottom:20px;"><source src="{m_url}" type="video/mp4"></video>'
                    else:
                        media_html += f'<img src="{m_url}" style="width:100%; border-radius:15px; margin-bottom:20px;">'
                        # Первое изображение делаем миниатюрой поста
                        if not featured_image_id:
                            featured_image_id = m_id

            # Ссылка на оригинал
            source_url = f"https://t.me/{channel}/{data['id']}"
            footer = f'<div class="tg-source" style="margin-top:20px; border-top:1px solid #eee; padding-top:10px;"><a href="{source_url}" target="_blank">Original Telegram Post</a></div>'
            
            # ЛОГИКА ЗАГОЛОВКА: Берем первую строку, чистим от HTML и ограничиваем длину
            first_line = data["text"].split('<br')[0].split('\n')[0]
            clean_title = re.sub('<[^<]+?>', '', first_line).strip()[:50]
            
            payload = {
                "title": clean_title or f"Post {data['id']}",
                "content": f"{media_html}<div class='tg-body'>{data['text']}</div>{footer}",
                "status": "publish",
                "slug": slug,
                "featured_media": featured_image_id,
                "date": data["date"].isoformat()
            }
            
            # 1. Создаем пост
            post_res = requests.post(f"{WP_BASE_URL}/tg_post", auth=auth, json=payload)
            
            if post_res.status_code == 201:
                post_id = post_res.json()['id']
                # 2. Привязываем медиафайлы к созданному посту
                # Это необходимо для корректной работы PHP-скрипта удаления вложений
                for m_id in uploaded_ids:
                    requests.post(f"{WP_BASE_URL}/media/{m_id}", auth=auth, json={"post": post_id})
                print(f"Successfully synced: {slug}")
            else:
                print(f"Error creating post {slug}: {post_res.text}")

            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
