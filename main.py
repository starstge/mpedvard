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

# ТВОЙ КОД ИЗ ВК (ВСТАВИЛ ЗА ТЕБЯ)
CONFIRMATION_CODE = "db771a86" 

bot = Bot(TOKEN)
queue = deque()
PEER_ID = None
queue_msg_id = None
db_pool = None

# ================= БД И ЛОГИКА =================
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, ssl="require")
    async with db_pool.acquire() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, value TEXT)")

async def save_to_db():
    if not db_pool: return
    async with db_pool.acquire() as conn:
        data = [("queue", json.dumps(list(queue))), 
                ("peer_id", str(PEER_ID) if PEER_ID else ""),
                ("msg_id", str(queue_msg_id) if queue_msg_id else "")]
        for k, v in data:
            await conn.execute("INSERT INTO bot_state (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2", k, v)

async def load_from_db():
    global queue, PEER_ID, queue_msg_id
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM bot_state")
        d = {r['key']: r['value'] for r in rows}
        if "queue" in d: queue = deque(json.loads(d["queue"]))
        if "peer_id" in d and d["peer_id"]: PEER_ID = int(d["peer_id"])
        if "msg_id" in d and d["msg_id"]: queue_msg_id = int(d["msg_id"])

def get_kb():
    return Keyboard(inline=False).add(Text("Занять", {"action": "join"}), color="positive").add(Text("Выйти", {"action": "exit"}), color="negative").get_json()

async def refresh_msg():
    if not PEER_ID: return
    text = "📝 **Очередь на лог-МП:**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    if not queue:
        text += "Очередь пуста. Нажми кнопку ниже!"
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
        await save_to_db()

# ================= ОБРАБОТКА WEBHOOK =================
async def webhook_handler(request):
    try:
        data = await request.json()
        # ВК просит подтверждение
        if data.get("type") == "confirmation":
            return web.Response(text=CONFIRMATION_CODE)
        
        # Обработка событий (сообщения, кнопки)
        if "type" in data:
            asyncio.create_task(bot.router.route(data, bot.api))
        
        return web.Response(text="ok")
    except:
        return web.Response(text="ok")

# ================= КОМАНДЫ =================
@bot.on.message(text="/peer")
async def cmd_peer(message: Message):
    if message.from_id == OWNER_ID:
        global PEER_ID, queue_msg_id
        PEER_ID, queue_msg_id = message.peer_id, None
        await refresh_msg()
        await message.answer("✅ Чат успешно привязан!")

@bot.on.raw_event(GroupEventType.MESSAGE_EVENT)
async def handle_buttons(event: MessageEvent):
    user = event.user_id
    action = event.payload.get("action")
    if action == "join":
        if user not in queue:
            queue.append(user)
            await save_to_db(); await refresh_msg(); await event.show_snackbar("Вы добавлены!")
        else:
            await event.show_snackbar("Вы уже в списке!")
    elif action == "exit":
        if user in queue:
            queue.remove(user)
            await save_to_db(); await refresh_msg(); await event.show_snackbar("Вы вышли!")
        else:
            await event.show_snackbar("Вас нет в списке.")

# ================= ЗАПУСК =================
async def main():
    await init_db()
    await load_from_db()
    
    app = web.Application()
    app.router.add_post("/webhook", webhook_handler) # Путь для ВК
    app.router.add_get("/", lambda r: web.Response(text="Alive")) # Для проверки в браузере
    
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    print(f"--- Webhook server started on port {port} ---")
    # Держим процесс живым
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
