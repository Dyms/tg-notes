import asyncio
import os
import re
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon import utils

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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_or_create_tag(tag_name):
    """Находит ID тега или создает новый"""
    try:
        # Поиск существующего тега
        res = requests.get(f"{WP_BASE_URL}/tags", params={"search": tag_name}, auth=auth)
        tags = res.json()
        for t in tags:
            if t['name'].lower() == tag_name.lower():
                return t['id']
        
        # Создание, если не найден
        res = requests.post(f"{WP_BASE_URL}/tags", json={"name": tag_name}, auth=auth)
        return res.json().get('id') if res.status_code == 201 else None
    except:
        return None

async def upload_to_wp_media(msg, slug):
    """Загружает файл в медиабиблиотеку WP"""
    file_path = await msg.download_media()
    if not file_path:
        return None, None

    filename = os.path.basename(file_path)
    with open(file_path, 'rb') as f:
        headers = {'Content-Disposition': f'attachment; filename={filename}'}
        res = requests.post(f"{WP_BASE_URL}/media", auth=auth, files={'file': f}, headers=headers)
    
    os.remove(file_path)
    if res.status_code == 201:
        data = res.json()
        return data['id'], data['source_url']
    return None, None

async def post_exists(slug):
    """Проверка дубликата по слагу"""
    res = requests.get(f"{WP_BASE_URL}/tg_post", params={"slug": slug}, auth=auth)
    return len(res.json()) > 0 if res.status_code == 200 else False

# --- ОСНОВНАЯ ЛОГИКА ---

async def main():
    async with client:
        print("Начинаю сбор сообщений...")
        messages = []
        async for msg in client.iter_messages(channel, limit=30):
            messages.append(msg)

        # Группировка по grouped_id (для альбомов)
        groups = {}
        for msg in messages:
            if not msg.text and not msg.media: continue
            gid = msg.grouped_id if msg.grouped_id else f"single-{msg.id}"
            if gid not in groups:
                groups[gid] = {"id": msg.id, "text": "", "media": [], "date": msg.date}
            
            if msg.text:
                groups[gid]["text"] = msg.text
            if msg.media:
                groups[gid]["media"].append(msg)

        for gid, data in groups.items():
            slug = f"tg-{data['id']}"
            
            if await post_exists(slug):
                print(f"Запись {slug} уже есть на сайте. Пропуск.")
                continue

            print(f"Обработка новой записи {slug}...")

            # 1. Работа с тегами
            tag_names = re.findall(r'#(\w+)', data["text"])
            tag_ids = [get_or_create_tag(t) for t in tag_names]
            tag_ids = [t for t in tag_ids if t]

            # 2. Работа с медиа
            media_html = ""
            featured_image_id = None
            
            # Если это альбом (галерея)
            if len(data["media"]) > 1:
                media_html = '<div class="tg-gallery" style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:20px;">'
                for m in data["media"]:
                    m_id, m_url = await upload_to_wp_media(m, slug)
                    if m_url:
                        if m.photo:
                            media_html += f'<img src="{m_url}" style="width:100%; border-radius:10px;">'
                            if not featured_image_id: featured_image_id = m_id
                        elif m.video:
                            media_html += f'<video controls style="width:100%; border-radius:10px;"><source src="{m_url}"></video>'
                media_html += '</div>'
            # Если одиночное медиа
            elif len(data["media"]) == 1:
                m = data["media"][0]
                m_id, m_url = await upload_to_wp_media(m, slug)
                if m_url:
                    if m.photo:
                        media_html = f'<img src="{m_url}" style="width:100%; border-radius:15px; margin-bottom:20px;">'
                        featured_image_id = m_id
                    elif m.video:
                        media_html = f'<video controls style="width:100%; border-radius:15px; margin-bottom:20px;"><source src="{m_url}"></video>'

            # 3. Текст и очистка
            clean_text = re.sub(r'#\w+', '', data["text"]).strip()
            # Заголовок — первая строка или дата
            title = clean_text.split('\n')[0][:60].strip() or f"Заметка от {data['date'].strftime('%d.%m.%Y')}"
            
            source_link = f"https://t.me/{channel}/{data['id']}"
            footer = f'<div class="tg-source" style="margin-top:30px; border-top:1px solid #eee; padding-top:10px; font-style:italic; font-size:13px; color:#888;">Опубликовано в <a href="{source_link}" target="_blank">Telegram</a></div>'

            # 4. Отправка в WordPress
            post_payload = {
                "title": title,
                "content": f"{media_html}<div class='tg-body'>{clean_text}</div>{footer}",
                "status": "publish",
                "slug": slug,
                "tags": tag_ids,
                "featured_media": featured_image_id,
                "date": data["date"].isoformat() # Сохраняем оригинальную дату из TG
            }

            res = requests.post(f"{WP_BASE_URL}/tg_post", auth=auth, json=post_payload)
            if res.status_code == 201:
                print(f"Успешно: {title}")
            else:
                print(f"Ошибка: {res.text}")
            
            await asyncio.sleep(1) # Плавность

if __name__ == "__main__":
    asyncio.run(main())
