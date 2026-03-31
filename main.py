import asyncio
import json
import sqlite3
import os
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
active_user = None
queue_msg_id = None
PEER_ID = None # Определится автоматически после команды /peer
ranks = {}
lock = asyncio.Lock()

# ================= ВЕБ-СЕРВЕР (Для Render) =================
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render передает порт через переменную окружения PORT
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"--- Web server started on port {port} ---")

# ================= БАЗА ДАННЫХ =================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS ranks (user_id INTEGER PRIMARY KEY, rank INTEGER DEFAULT 0)")
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
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM state")
    data = dict(cur.fetchall())
    if "queue" in data: queue = deque(json.loads(data["queue"]))
    if "peer_id" in data and data["peer_id"]: PEER_ID = int(data["peer_id"])
    if "msg_id" in data and data["msg_id"]: queue_msg_id = int(data["msg_id"])
    
    cur.execute("SELECT user_id, rank FROM ranks")
    for uid, r in cur.fetchall(): ranks[uid] = r
    conn.close()

# ================= ЛОГИКА ОЧЕРЕДИ =================
def get_kb():
    return Keyboard(inline=False).add(Text("Занять очередь", {"action": "join"})).get_json()

async def update_queue_msg():
    if not PEER_ID: return
    text = " **Очередь на МП:**\n"
    if not queue:
        text += "Пусто. Будь первым!"
    for i, uid in enumerate(queue, 1):
        text += f"{i}. [id{uid}|Участник]\n"
    
    global queue_msg_id
    try:
        if queue_msg_id:
            await bot.api.messages.edit(peer_id=PEER_ID, message=text, message_id=queue_msg_id, keyboard=get_kb())
        else: raise Exception()
    except:
        res = await bot.api.messages.send(peer_id=PEER_ID, message=text, keyboard=get_kb(), random_id=0)
        queue_msg_id = res
        save_data()

# ================= ОБРАБОТЧИКИ =================
@bot.on.message(text="/peer")
async def set_peer(message: Message):
    global PEER_ID
    PEER_ID = message.peer_id
    save_data()
    await message.answer(f"✅ Чат привязан! Peer ID: {PEER_ID}")
    await update_queue_msg()

@bot.on.message(text="/clear")
async def clear_q(message: Message):
    if ranks.get(message.from_id, 0) < 2 and message.from_id != OWNER_ID: return
    queue.clear()
    save_data()
    await update_queue_msg()

@bot.on.raw_event(GroupEventType.MESSAGE_EVENT)
async def buttons(event: MessageEvent):
    user = event.user_id
    action = event.payload.get("action")
    
    if action == "join":
        if user in queue:
            await event.show_snackbar("Ты уже записан!")
        else:
            queue.append(user)
            save_data()
            await event.show_snackbar("Добавлен в очередь!")
            await update_queue_msg()

async def main():
    init_db()
    load_data()
    ranks[OWNER_ID] = 2
    
    # Запускаем веб-сервер фоном
    await start_web_server()
    
    print("Бот запущен и готов к работе!")
    await bot.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
