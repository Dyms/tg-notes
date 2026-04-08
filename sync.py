import asyncio
import json
import os
import shutil
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon import utils

# Данные авторизации из окружения
api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"])
channel = os.environ["TG_CHANNEL"]
session_str = os.environ.get("TG_SESSION")

client = TelegramClient(StringSession(session_str), api_id, api_hash)
client.parse_mode = 'html' # Сохраняем оригинальную разметку Telegram

OUTPUT_DIR = "notes"
MEDIA_DIR = os.path.join(OUTPUT_DIR, "media")
MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50 MB

async def main():
    # Полная очистка перед синхронизацией для удаления дублей и лишних файлов
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    
    os.makedirs(MEDIA_DIR, exist_ok=True)
    index_path = os.path.join(OUTPUT_DIR, "index.json")
    existing_notes = {}

    async with client:
        print("--- Синхронизация: Режим зеркала (последние 20) ---")
        async for msg in client.iter_messages(channel, limit=20):
            if not msg.text and not msg.media: continue

            slug = f"log-{msg.id}"
            media_info = None

            if msg.media:
                is_video = bool(msg.video)
                # Проверка размера видео
                file_size = msg.file.size if msg.file else 0
                is_too_large = is_video and file_size > MAX_VIDEO_SIZE
                
                filename = f"{slug}"
                if msg.photo:
                    filename += ".jpg"
                elif is_video and not is_too_large:
                    filename += ".mp4"
                else:
                    ext = utils.get_extension(msg.media)
                    filename += ext if ext else ".bin"

                file_path = os.path.join(MEDIA_DIR, filename)
                
                # Загружаем только если это фото или видео в пределах лимита
                if not is_too_large:
                    await msg.download_media(file=file_path)
                
                media_info = {
                    "type": "video" if is_video else "photo",
                    "url": f"media/{filename}" if not is_too_large else None,
                    "too_large": is_too_large
                }

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

    # Сохраняем индекс
    sorted_notes = sorted(existing_notes.values(), key=lambda x: x['id'], reverse=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"notes": sorted_notes}, f, ensure_ascii=False, indent=2)
    
    print(f"Готово. Актуальных записей: {len(sorted_notes)}")

if __name__ == "__main__":
    asyncio.run(main())
