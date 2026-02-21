import asyncio, aiohttp, json
from pathlib import Path
from datetime import datetime

HISTORY_FILE = Path(__file__).parent / "whatsapp_history.json"

async def test():
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:3001/check-whatsapp",
                               timeout=aiohttp.ClientTimeout(total=35)) as resp:
            data = await resp.json()
            print("MCP STATUS:", data.get("status"))
            msgs = data.get("new_messages", [])
            print("MSGS COUNT:", len(msgs))
            for m in msgs[:5]:
                print(" -", m.get("sender"), "| unread:", m.get("count"), "| preview:", m.get("preview","")[:30])

            now = datetime.now().isoformat()
            entries = []
            seen = set()
            for chat in msgs:
                sender = chat.get("sender","").strip()
                if not sender or sender in seen:
                    continue
                seen.add(sender)
                entries.append({
                    "id": f"wa_{sender}",
                    "service": "whatsapp",
                    "type": "message",
                    "sender": sender,
                    "preview": chat.get("preview",""),
                    "text": chat.get("preview",""),
                    "subject": f"WhatsApp from {sender}",
                    "unread": chat.get("count", 0) > 0,
                    "count": chat.get("count", 0),
                    "timestamp": now,
                })
            HISTORY_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Written {len(entries)} entries, file size:", HISTORY_FILE.stat().st_size)

asyncio.run(test())
