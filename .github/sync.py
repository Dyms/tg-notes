import asyncio
import json
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
channel = os.environ["TG_CHANNEL"]
session_str = os.environ.get("TG_SESSION")

client = TelegramClient(StringSession(session_str), api_id, api_hash)

# ТЕПЕРЬ ПУТЬ ПРОСТО 'notes'
OUTPUT_DIR = "notes"

def parse(text):
    blocks = []
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line: continue
        blocks.append({"type": "text", "content": line})
    return blocks

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    index_path = os.path.join(OUTPUT_DIR, "index.json")
    
    # Загружаем существующий индекс для накопления
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                existing_notes = {n['id']: n for n in data.get("notes", [])}
            except:
                existing_notes = {}
    else:
        existing_notes = {}

    async with client:
        print(f"--- Проверка обновлений ---")
        
        async for msg in client.iter_messages(channel, limit=20):
            if not msg.text: continue

            slug = f"log-{msg.id}"
            
            # Сохраняем индивидуальный файл
            note_data = {
                "id": msg.id,
                "slug": slug,
                "date": str(msg.date.date()),
                "blocks": parse(msg.text)
            }
            
            file_path = os.path.join(OUTPUT_DIR, f"{slug}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(note_data, f, ensure_ascii=False, indent=2)

            # Обновляем запись в индексе
            existing_notes[msg.id] = {
                "id": msg.id,
                "slug": slug,
                "date": str(msg.date.date()),
                "title": msg.text.split("\n")[0][:60],
                "tags": []
            }

    # Сортируем (новые сверху) и сохраняем
    sorted_notes = sorted(existing_notes.values(), key=lambda x: x['id'], reverse=True)
    
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"notes": sorted_notes}, f, ensure_ascii=False, indent=2)
    
    print(f"Готово. Всего в архиве: {len(sorted_notes)}")

if __name__ == "__main__":
    asyncio.run(main())
