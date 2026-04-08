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
    
    processed_groups = {}
    final_notes = []

    async with client:
        print("--- Начинаю синхронизацию ---")
        
        # Скачиваем сообщения и медиа ОДНОВРЕМЕННО
        async for msg in client.iter_messages(channel, limit=30):
            if not msg.text and not msg.media: continue

            # Уникальный ключ группы
            group_id = msg.grouped_id if msg.grouped_id else f"single-{msg.id}"
            
            # Извлекаем теги
            tags = re.findall(r'#(\w+)', msg.text) if msg.text else []
            
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
                # Если текст в альбоме пришел в другом сообщении — сохраняем его
                if not processed_groups[group_id]["content"] and msg.text:
                    processed_groups[group_id]["content"] = msg.text
                    processed_groups[group_id]["tags"] = tags

            # Обработка медиа прямо в потоке
            if msg.media:
                is_video = bool(msg.video)
                file_size = msg.file.size if msg.file else 0
                is_too_large = is_video and file_size > MAX_VIDEO_SIZE
                
                slug = f"media-{msg.id}"
                ext = ".mp4" if is_video and not is_too_large else (".jpg" if msg.photo else utils.get_extension(msg.media))
                filename = f"{slug}{ext}"
                file_path = os.path.join(MEDIA_DIR, filename)

                if not is_too_large:
                    try:
                        print(f"Скачиваю: {filename}")
                        await msg.download_media(file=file_path)
                    except Exception as e:
                        print(f"Ошибка скачивания {filename}: {e}")
                
                processed_groups[group_id]["media"].append({
                    "type": "video" if is_video else "photo",
                    "url": f"media/{filename}" if not is_too_large else None,
                    "too_large": is_too_large
                })
                # Небольшая пауза, чтобы Telegram не разорвал соединение
                await asyncio.sleep(0.2)

    # После закрытия 'async with client' сохраняем JSON файлы
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

    final_notes.sort(key=lambda x: x['id'], reverse=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"notes": final_notes[:20]}, f, ensure_ascii=False, indent=2)
    
    print(f"Успешно синхронизировано: {len(final_notes)} записей")

if __name__ == "__main__":
    asyncio.run(main())
