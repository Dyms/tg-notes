import asyncio
import os
import re
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.extensions import html

# --- КОНФИГУРАЦИЯ ---
# Эти переменные должны быть добавлены в GitHub Secrets
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

async def upload_to_wp_media(msg):
    """Загружает файл в медиабиблиотеку WP и возвращает (ID, URL)"""
    file_path = await msg.download_media()
    if not file_path:
        return None, None

    filename = os.path.basename(file_path)
    # Определяем тип файла для корректного заголовка Content-Type
    is_video = filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))
    mime_type = 'video/mp4' if is_video else 'image/jpeg'
    
    print(f"Загрузка файла {filename}...")
    
    with open(file_path, 'rb') as f:
        headers = {
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': mime_type
        }
        res = requests.post(f"{WP_BASE_URL}/media", auth=auth, files={'file': f}, headers=headers)
    
    if os.path.exists(file_path):
        os.remove(file_path)

    if res.status_code == 201:
        data = res.json()
        return data['id'], data['source_url']
    else:
        print(f"Ошибка загрузки медиа: {res.text}")
        return None, None

async def main():
    async with client:
        print("Сбор сообщений из Telegram...")
        messages = []
        # Берем последние 15 сообщений для проверки
        async for msg in client.iter_messages(channel, limit=15):
            messages.append(msg)

        # Группируем сообщения (поддержка альбомов)
        groups = {}
        for msg in messages:
            if not msg.message and not msg.media:
                continue
            
            gid = msg.grouped_id if msg.grouped_id else f"single-{msg.id}"
            
            if gid not in groups:
                # Сохраняем форматирование (HTML)
                formatted_text = html.unparse(msg.message, msg.entities) if msg.message else ""
                groups[gid] = {
                    "id": msg.id,
                    "text": formatted_text,
                    "media": [],
                    "date": msg.date
                }
            else:
                # Если в группе несколько текстовых блоков (редко), дополняем
                if msg.message and not groups[gid]["text"]:
                    groups[gid]["text"] = html.unparse(msg.message, msg.entities)
            
            if msg.media:
                groups[gid]["media"].append(msg)

        for gid, data in groups.items():
            slug = f"tg-{data['id']}"
            
            # Проверка на дубликаты
            check = requests.get(f"{WP_BASE_URL}/tg_post", params={"slug": slug}, auth=auth)
            if check.status_code == 200 and len(check.json()) > 0:
                print(f"Запись {slug} уже существует. Пропуск.")
                continue

            print(f"Создание записи: {slug}")

            media_html = ""
            featured_image_id = None

            # Обработка вложений
            for m in data["media"]:
                m_id, m_url = await upload_to_wp_media(m)
                if m_url:
                    filename = m_url.lower()
                    if filename.endswith(('.mp4', '.mov', '.avi')):
                        # Вставка ВИДЕО через правильный тег
                        media_html += (
                            f'<video controls style="width:100%; border-radius:15px; margin-bottom:20px;">'
                            f'<source src="{m_url}" type="video/mp4">'
                            f'Ваш браузер не поддерживает видео.'
                            f'</video>'
                        )
                    else:
                        # Вставка КАРТИНКИ
                        media_html += f'<img src="{m_url}" style="width:100%; border-radius:15px; margin-bottom:20px;">'
                        # Первое фото делаем миниатюрой поста
                        if not featured_image_id:
                            featured_image_id = m_id

            # Ссылка на оригинал
            source_link = f"https://t.me/{channel}/{data['id']}"
            footer = (
                f'<div class="tg-source" style="margin-top:30px; border-top:1px solid #eee; padding-top:15px; font-size:13px; color:#888;">'
                f'Опубликовано в <a href="{source_link}" target="_blank">Telegram</a>'
                f'</div>'
            )

            # Очистка заголовка от HTML-тегов для корректного отображения в админке
            title_clean = re.sub('<[^<]+?>', '', data["text"]).split('\n')[0][:60].strip() or f"Заметка {data['id']}"

            # Формирование поста
            post_payload = {
                "title": title_clean,
                "content": f"{media_html}<div class='tg-body'>{data['text']}</div>{footer}",
                "status": "publish",
                "slug": slug,
                "featured_media": featured_image_id,
                "date": data["date"].isoformat()
            }

            res = requests.post(f"{WP_BASE_URL}/tg_post", auth=auth, json=post_payload)
            
            if res.status_code == 201:
                print(f"Успешно опубликовано: {title_clean}")
            else:
                print(f"Ошибка публикации: {res.text}")

            # Небольшая пауза, чтобы не спамить API
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
