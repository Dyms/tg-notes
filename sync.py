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
OUTPUT_DIR = "notes"
MEDIA_DIR = os.path.join(OUTPUT_DIR, "media")

def parse_styled_text(msg):
    """Превращает форматированный текст сообщения в HTML-подобную структуру или Markdown."""
    # Telethon может отдавать текст сразу в Markdown или HTML
    # Мы будем использовать Markdown для хранения в JSON, это универсально
    return msg.text if msg.text else ""

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
        print("--- Синхронизация контента ---")
        async for msg in client.iter_messages(channel, limit=20):
            # Пропускаем, если нет ни текста, ни медиа
            if not msg.text and not msg.media: continue

            slug = f"log-{msg.id}"
            media_info = None

            # ОБРАБОТКА ВЛОЖЕНИЙ (Фото и Файлы)
            if msg.media:
                # Определяем расширение и имя файла
                filename = f"{slug}"
                if msg.photo:
                    filename += ".jpg"
                else:
                    # Для документов пытаемся взять оригинальное имя
                    original_name = getattr(msg.media, 'document', None)
                    ext = utils.get_extension(msg.media)
                    filename += ext if ext else ".bin"

                file_path = os.path.join(MEDIA_DIR, filename)
                
                if not os.path.exists(file_path):
                    print(f"Скачиваю медиа для {slug}...")
                    await msg.download_media(file=file_path)
                
                media_info = {
                    "type": "photo" if msg.photo else "document",
                    "url": f"media/{filename}",
                    "name": filename
                }

            # ФОРМИРОВАНИЕ ЗАМЕТКИ
            note_data = {
                "id": msg.id,
                "slug": slug,
                "date": str(msg.date.date()),
                "content": parse_styled_text(msg), # Здесь теперь текст с форматированием
                "media": media_info
                "tg_link": f"https://t.me/{channel}/{msg.id}"
            }

            with open(os.path.join(OUTPUT_DIR, f"{slug}.json"), "w", encoding="utf-8") as f:
                json.dump(note_data, f, ensure_ascii=False, indent=2)

            existing_notes[msg.id] = {
                "id": msg.id,
                "slug": slug,
                "date": str(msg.date.date()),
                "title": (msg.text or "Вложение").split("\n")[0][:60],
                "has_media": bool(media_info)
            }

    sorted_notes = sorted(existing_notes.values(), key=lambda x: x['id'], reverse=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"notes": sorted_notes}, f, ensure_ascii=False, indent=2)
    
    print(f"Обновлено. Всего записей: {len(sorted_notes)}")

if __name__ == "__main__":
    asyncio.run(main())
