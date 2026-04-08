import asyncio
import json
import os
import shutil  # Добавили для удаления папок
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon import utils

# ... (ваши переменные api_id, api_hash и т.д.) ...

async def main():
    # ОЧИСТКА: Удаляем старые данные перед синхронизацией
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    
    os.makedirs(MEDIA_DIR, exist_ok=True)
    index_path = os.path.join(OUTPUT_DIR, "index.json")
    
    # Теперь existing_notes всегда пустой в начале
    existing_notes = {}

    async with client:
        print("--- Синхронизация последних 20 сообщений ---")
        async for msg in client.iter_messages(channel, limit=30):
            if not msg.text and not msg.media: continue

            slug = f"log-{msg.id}"
            media_info = None

            if msg.media:
                filename = f"{slug}"
                if msg.photo:
                    filename += ".jpg"
                else:
                    ext = utils.get_extension(msg.media)
                    filename += ext if ext else ".bin"

                file_path = os.path.join(MEDIA_DIR, filename)
                # Скачиваем заново, так как мы очистили папку
                await msg.download_media(file=file_path)
                
                media_info = {"type": "photo" if msg.photo else "document", "url": f"media/{filename}"}

            note_data = {
                "id": msg.id,
                "slug": slug,
                "date": msg.date.isoformat(),
                "content": msg.text if msg.text else "",
                "media": media_info,
                "tg_link": f"https://t.me/{channel}/{msg.id}"
            }

            with open(os.path.join(OUTPUT_DIR, f"{slug}.json"), "w", encoding="utf-8") as f:
                json.dump(note_data, f, ensure_ascii=False, indent=2)

            existing_notes[msg.id] = {
                "id": msg.id,
                "slug": slug,
                "date": msg.date.isoformat(),
                "title": (msg.message or "Вложение").split("\n")[0][:60]
            }

    # Сохраняем только актуальные 20 штук
    sorted_notes = sorted(existing_notes.values(), key=lambda x: x['id'], reverse=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"notes": sorted_notes}, f, ensure_ascii=False, indent=2)

    print(f"Синхронизация завершена. Опубликовано: {len(sorted_notes)}")
