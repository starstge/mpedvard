import asyncio
import json
import sqlite3
import os
import sys
from collections import deque
from aiohttp import web

from vkbottle import Bot, Keyboard, Text, GroupEventType
from vkbottle.bot import Message, MessageEvent

# ================= НАСТРОЙКИ =================
TOKEN = "vk1.a.6XXlN1EsapV9TvrnCYwm-IZveSkjzKf48_PugfCJnm8K-dmOeF7b25UnwdsYtRGk6yJz6OLdmmo8xsGeAGdqR4r0B5CuyyvS6kOFYXVubRsvRU8-rR_yX01ZZjlk-Wzi6gmPK2UFqELAiJOg4xXithi4od0RucJYQZ5w5R4p4uTAoyU7ou6awJtDRoNoyeQvjLyYQS_IS5H0ggsdDIMoGw"
OWNER_ID = 621098467
DB_FILE = "queue.db"

bot = Bot(TOKEN)
queue = deque()
PEER_ID = None
queue_msg_id = None
ranks = {OWNER_ID: 2}

# ================= ВЕБ-СЕРВЕР =================
async def handle_ping(request):
    return web.Response(text="Бот активен!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"--- HTTP Сервер запущен на порту {port} ---")

# ================= БАЗА ДАННЫХ =================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()

def save_data():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("REPLACE INTO state (key, value) VALUES (?, ?)", ("queue", json.dumps(list(queue))))
    cur.execute("REPLACE INTO state (key, value) VALUES (?, ?)", ("peer_id", str(PEER_ID) if PEER_ID else ""))
    cur.execute("REPLACE INTO state (key, value) VALUES (?, ?)", ("msg_id", str(queue_msg_id) if queue_msg_id else ""))
    conn.commit()
    conn.close()

def load_data():
    global queue, PEER_ID, queue_msg_id
    if not os.path.exists(DB_FILE): return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM state")
    data = dict(cur.fetchall())
    if "queue" in data: queue = deque(json.loads(data["queue"]))
    if "peer_id" in data and data["peer_id"]: PEER_ID = int(data["peer_id"])
    if "msg_id" in data and data["msg_id"]: queue_msg_id = int(data["msg_id"])
    conn.close()

# ================= ИНТЕРФЕЙС =================
def get_kb():
    kb = Keyboard(inline=False)
    kb.add(Text("Занять место", {"action": "join"}), color="positive")
    kb.add(Text("Выйти", {"action": "exit"}), color="negative")
    return kb.get_json()

async def update_queue_msg():
    if not PEER_ID: return
    text = "📝 **Очередь на лог-МП:**\n--------------------------\n"
    if not queue:
        text += "Пока никого нет. Будь первым!"
    else:
        for i, uid in enumerate(queue, 1):
            text += f"{i}. [id{uid}|👤 Участник]\n"
    
    global queue_msg_id
    try:
        if queue_msg_id:
            await bot.api.messages.edit(peer_id=PEER_ID, message=text, message_id=queue_msg_id, keyboard=get_kb())
        else: raise Exception()
    except:
        res = await bot.api.messages.send(peer_id=PEER_ID, message=text, keyboard=get_kb(), random_id=0)
        queue_msg_id = res
        save_data()

# ================= ХЕНДЛЕРЫ =================
@bot.on.message(text="/peer")
async def cmd_peer(message: Message):
    if message.from_id != OWNER_ID: return
    global PEER_ID, queue_msg_id
    PEER_ID = message.peer_id
    queue_msg_id = None
    await update_queue_msg()

@bot.on.message(text="/clear")
async def cmd_clear(message: Message):
    if message.from_id != OWNER_ID: return
    queue.clear()
    save_data()
    await update_queue_msg()

@bot.on.raw_event(GroupEventType.MESSAGE_EVENT)
async def handle_buttons(event: MessageEvent):
    user = event.user_id
    action = event.payload.get("action")
    if action == "join":
        if user in queue: await event.show_snackbar("Вы уже в списке!")
        else:
            queue.append(user)
            save_data()
            await update_queue_msg()
            await event.show_snackbar("Вы добавлены!")
    elif action == "exit":
        if user in queue:
            queue.remove(user)
            save_data()
            await update_queue_msg()
            await event.show_snackbar("Вы вышли.")
        else: await event.show_snackbar("Вас нет в списке.")

# ================= ГЛАВНЫЙ ЗАПУСК =================
async def main():
    init_db()
    load_data()
    
    # Запускаем веб-сервер
    await start_web_server()
    
    print("--- Бот запущен и готов к работе! ---")
    
    # Используем run_polling БЕЗ создания нового цикла
    await bot.run_polling()

if __name__ == "__main__":
    # Запускаем один общий цикл для всего
    asyncio.run(main())
