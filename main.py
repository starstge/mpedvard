import asyncio
import json
import os
from collections import deque
from aiohttp import web
import asyncpg

from vkbottle import Bot, Keyboard, Text, GroupEventType
from vkbottle.bot import Message, MessageEvent

# ================= НАСТРОЙКИ =================
TOKEN = "vk1.a.6XXlN1EsapV9TvrnCYwm-IZveSkjzKf48_PugfCJnm8K-dmOeF7b25UnwdsYtRGk6yJz6OLdmmo8xsGeAGdqR4r0B5CuyyvS6kOFYXVubRsvRU8-rR_yX01ZZjlk-Wzi6gmPK2UFqELAiJOg4xXithi4od0RucJYQZ5w5R4p4uTAoyU7ou6awJtDRoNoyeQvjLyYQS_IS5H0ggsdDIMoGw"
OWNER_ID = 621098467
DATABASE_URL = "postgresql://mp_wrz8_user:GAmEc4M3FDQfOtTHhHbDX31BGDW4SgFD@dpg-d75u5hea2pns73d48cig-a.oregon-postgres.render.com/mp_wrz8"

bot = Bot(TOKEN)
queue = deque()
PEER_ID = None
queue_msg_id = None
db_pool = None

# ================= РАБОТА С POSTGRESQL =================
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, ssl="require")
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

async def save_to_db():
    if not db_pool: return
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO bot_state (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2", 
                           "queue", json.dumps(list(queue)))
        await conn.execute("INSERT INTO bot_state (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2", 
                           "peer_id", str(PEER_ID) if PEER_ID else "")
        await conn.execute("INSERT INTO bot_state (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2", 
                           "msg_id", str(queue_msg_id) if queue_msg_id else "")

async def load_from_db():
    global queue, PEER_ID, queue_msg_id
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM bot_state")
        data = {row['key']: row['value'] for row in rows}
        if "queue" in data: queue = deque(json.loads(data["queue"]))
        if "peer_id" in data and data["peer_id"]: PEER_ID = int(data["peer_id"])
        if "msg_id" in data and data["msg_id"]: queue_msg_id = int(data["msg_id"])

# ================= ИНТЕРФЕЙС =================
def get_main_keyboard():
    kb = Keyboard(inline=False)
    kb.add(Text("Занять место", {"action": "join"}), color="positive")
    kb.add(Text("Выйти", {"action": "exit"}), color="negative")
    return kb.get_json()

async def refresh_queue_message():
    if not PEER_ID: return
    content = "📝 **Очередь на лог-МП:**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    if not queue: content += "Очередь пуста. Нажми кнопку!"
    else:
        for i, uid in enumerate(queue, 1):
            content += f"{i}. [id{uid}|👤 Участник]\n"
    
    global queue_msg_id
    try:
        if queue_msg_id:
            await bot.api.messages.edit(peer_id=PEER_ID, message=content, message_id=queue_msg_id, keyboard=get_main_keyboard())
        else: raise Exception()
    except:
        res = await bot.api.messages.send(peer_id=PEER_ID, message=content, keyboard=get_main_keyboard(), random_id=0)
        queue_msg_id = res
        await save_to_db()

# ================= ХЕНДЛЕРЫ =================
@bot.on.message(text="/peer")
async def cmd_peer(message: Message):
    if message.from_id != OWNER_ID: return
    global PEER_ID, queue_msg_id
    PEER_ID = message.peer_id
    queue_msg_id = None
    await refresh_queue_message()

@bot.on.message(text="/clear")
async def cmd_clear(message: Message):
    if message.from_id != OWNER_ID: return
    queue.clear()
    await save_to_db()
    await refresh_queue_message()

@bot.on.raw_event(GroupEventType.MESSAGE_EVENT)
async def handle_callback(event: MessageEvent):
    user = event.user_id
    action = event.payload.get("action")
    if action == "join":
        if user in queue: await event.show_snackbar("Вы уже в очереди!")
        else:
            queue.append(user)
            await save_to_db(); await refresh_queue_message()
            await event.show_snackbar("Записано!")
    elif action == "exit":
        if user in queue:
            queue.remove(user)
            await save_to_db(); await refresh_queue_message()
            await event.show_snackbar("Удалено.")

# ================= СЕРВЕР И ЗАПУСК =================
async def web_handler(request):
    return web.Response(text="Bot is running with Postgres!")

async def main():
    # 1. Инициализация БД
    await init_db()
    await load_from_db()

    # 2. Настройка веб-сервера
    app = web.Application()
    app.router.add_get("/", web_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"--- HTTP Server started on port {port} ---")

    # 3. Запуск Polling БЕЗ создания нового цикла
    # Это "чистый" способ запустить vkbottle внутри существующего loop
    print("--- Starting VK Polling ---")
    await bot.run_polling()

if __name__ == "__main__":
    # Используем базовый asyncio.run
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
