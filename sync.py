import asyncio
import json
import os
import shutil
import re
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon import utils

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
channel = os.environ["TG_CHANNEL"]
session_str = os.environ.get("TG_SESSION")

client = TelegramClient(StringSession(session_str), api_id, api_hash)
client.parse_mode = 'html'

OUTPUT_DIR = "notes"
MEDIA_DIR = os.path.join(OUTPUT_DIR, "media")
MAX_VIDEO_SIZE = 50 * 1024 * 1024 

async def main():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(MEDIA_DIR, exist_ok=True)
    
    index_path = os.path.join(OUTPUT_DIR, "index.json")
    all_messages = []

    async with client:
        # Убеждаемся, что мы подключены
        if not await client.is_user_authorized():
            print("Ошибка: Клиент не авторизован")
            return

        print("--- Получение сообщений ---")
        async for msg in client.iter_messages(channel, limit=30):
            all_messages.append(msg)

        processed_groups = {} 
        
        print(f"--- Обработка медиа ({len(all_messages)} сообщений) ---")
        for msg in all_messages:
            # ... (логика тегов и group_id остается прежней) ...
            
            # В блоке обработки медиа:
            if msg.media:
                is_video = bool(msg.video)
                file_size = msg.file.size if msg.file else 0
                is_too_large = is_video and file_size > MAX_VIDEO_SIZE
                
                slug = f"media-{msg.id}"
                ext = ".mp4" if is_video and not is_too_large else (".jpg" if msg.photo else utils.get_extension(msg.media))
                filename = f"{slug}{ext}"
                file_path = os.path.join(MEDIA_DIR, filename)

                if not is_too_large:
                    # ПРОВЕРКА СОЕДИНЕНИЯ ПЕРЕД СКАЧИВАНИЕМ
                    if not client.is_connected():
                        await client.connect()
                    
                    try:
                        await msg.download_media(file=file_path)
                    except Exception as e:
                        print(f"Ошибка при скачивании {filename}: {e}")

    processed_groups = {} # Для группировки альбомов
    final_notes = []

    for msg in all_messages:
        # Извлекаем хештеги
        tags = []
        if msg.text:
            tags = re.findall(r'#(\w+)', msg.text)
        
        # Уникальный ключ для заметки (ID сообщения или grouped_id)
        group_id = msg.grouped_id if msg.grouped_id else f"single-{msg.id}"
        
        if group_id not in processed_groups:
            processed_groups[group_id] = {
                "id": msg.id,
                "date": msg.date.isoformat(),
                "content": msg.text if msg.text else "",
                "media": [],
                "tags": tags,
                "tg_link": f"https://t.me/{channel}/{msg.id}"
            }
        else:
            # Если это часть альбома, дополняем текст (если его нет в первом элементе)
            if not processed_groups[group_id]["content"] and msg.text:
                processed_groups[group_id]["content"] = msg.text
                processed_groups[group_id]["tags"] = tags

        # Обработка медиа
        if msg.media:
            is_video = bool(msg.video)
            file_size = msg.file.size if msg.file else 0
            is_too_large = is_video and file_size > MAX_VIDEO_SIZE
            
            slug = f"media-{msg.id}"
            ext = ".mp4" if is_video and not is_too_large else (".jpg" if msg.photo else utils.get_extension(msg.media))
            filename = f"{slug}{ext}"
            file_path = os.path.join(MEDIA_DIR, filename)

            if not is_too_large:
                await msg.download_media(file=file_path)
            
            processed_groups[group_id]["media"].append({
                "type": "video" if is_video else "photo",
                "url": f"media/{filename}" if not is_too_large else None,
                "too_large": is_too_large
            })

    # Сохраняем каждый JSON
    for g_id, data in processed_groups.items():
        slug = f"log-{data['id']}"
        data["slug"] = slug
        with open(os.path.join(OUTPUT_DIR, f"{slug}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        final_notes.append({
            "id": data["id"],
            "slug": slug,
            "date": data["date"],
            "tags": data["tags"]
        })

    # Сортировка и индекс
    final_notes.sort(key=lambda x: x['id'], reverse=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"notes": final_notes[:20]}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
