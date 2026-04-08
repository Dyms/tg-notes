import asyncio
import os
import re
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon import utils

# Конфигурация Telegram
api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
channel = os.environ["TG_CHANNEL"]
session_str = os.environ.get("TG_SESSION")

# Конфигурация WordPress
WP_URL = "https://dbogatov.ru/wp-json/wp/v2/tg_post"

WP_USER = os.environ["WP_USER"]
WP_PASS = os.environ["WP_PASS"]

client = TelegramClient(StringSession(session_str), api_id, api_hash)

async def check_post_exists(slug):
    """Проверяет, существует ли пост с таким slug в WordPress"""
    res = requests.get(f"{WP_URL}/posts", params={"slug": slug}, auth=(WP_USER, WP_PASS))
    return len(res.json()) > 0

async def upload_media(msg, slug):
    """Загружает медиа в библиотеку WordPress"""
    file_path = await msg.download_media()
    if not file_path:
        return None
    
    with open(file_path, 'rb') as f:
        headers = {'Content-Disposition': f'attachment; filename={os.path.basename(file_path)}'}
        res = requests.post(f"{WP_URL}/media", auth=(WP_USER, WP_PASS), files={'file': f}, headers=headers)
    
    os.remove(file_path) # Удаляем временный файл
    if res.status_code == 201:
        return res.json()['id'], res.json()['source_url']
    return None, None

async def main():
    async with client:
        # Получаем последние 20 сообщений
        async for msg in client.iter_messages(channel, limit=20):
            if not msg.text and not msg.media: continue

            # Уникальный slug для предотвращения дублей
            slug = f"tg-msg-{msg.id}"
            
            if await check_post_exists(slug):
                print(f"Пост {msg.id} уже существует. Пропускаю.")
                continue

            print(f"Обработка нового сообщения {msg.id}...")

            # Обработка текста и тегов
            content = msg.text if msg.text else ""
            tags = re.findall(r'#(\w+)', content)
            
            # Удаляем хештеги из заголовка для чистоты
            clean_title = re.sub(r'#\w+', '', content).split('\n')[0][:50].strip() or "Заметка"

            # Загрузка медиа
            media_html = ""
            featured_image_id = None
            if msg.media:
                media_id, media_url = await upload_media(msg, slug)
                if media_url:
                    if msg.photo:
                        media_html = f'<img src="{media_url}" style="width:100%; height:auto; margin-bottom:20px;">'
                        featured_image_id = media_id
                    elif msg.video:
                        media_html = f'<video controls style="width:100%; margin-bottom:20px;"><source src="{media_url}"></video>'

            # Формирование финального контента (с пометкой о Telegram)
            footer = f'<hr><p style="font-size: 0.8em; color: #888;"><i>Это сообщение было импортировано из <a href="https://t.me/{channel}/{msg.id}">Telegram</a></i></p>'
            full_content = f"{media_html}{content}{footer}"

            # Создание поста
            post_data = {
                "title": clean_title,
                "content": full_content,
                "status": "publish",
                "slug": slug,
                "featured_media": featured_image_id,
                "tags": [] # Теги добавим ниже
            }

            # Отправка в WordPress
            res = requests.post(f"{WP_URL}/posts", auth=(WP_USER, WP_PASS), json=post_data)
            
            if res.status_code == 201:
                print(f"Успешно опубликовано: {clean_title}")
            else:
                print(f"Ошибка публикации: {res.text}")

if __name__ == "__main__":
    asyncio.run(main())
