import asyncio
import json
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon import utils

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
channel = os.environ["TG_CHANNEL"]
session_str = os.environ.get("TG_SESSION")

client = TelegramClient(StringSession(session_str), api_id, api_hash)
client.parse_mode = 'html' # Переключаемся на HTML для сохранения <u> и <blockquote>

OUTPUT_DIR = "notes"
MEDIA_DIR = os.path.join(OUTPUT_DIR, "media")

async def main():
    os.makedirs(MEDIA_DIR, exist_ok=True)
    index_path = os.path.join(OUTPUT_DIR, "index.json")
    
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                existing_notes = {n['id']: n for n in data.get("notes", [])}
            except: existing_notes = {}
    else: existing_notes = {}

    async with client:
        # Используем .iter_messages для получения последних постов
        async for msg in client.iter_messages(channel, limit=20):
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
                if not os.path.exists(file_path):
                    await msg.download_media(file=file_path)
                
                media_info = {"type": "photo" if msg.photo else "document", "url": f"media/{filename}"}

            note_data = {
                "id": msg.id,
                "slug": slug,
                "date": msg.date.isoformat(), # Сохраняем время полностью
                "content": msg.text if msg.text else "", # Теперь здесь будет чистый HTML
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

    sorted_notes = sorted(existing_notes.values(), key=lambda x: x['id'], reverse=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"notes": sorted_notes}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
