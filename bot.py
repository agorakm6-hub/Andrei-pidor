import asyncio
import logging
import os
import sys
import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Set

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.functions.account import ReportPeerRequest
from telethon.tl.types import InputReportReasonPersonalDetails
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.contacts import BlockRequest

# ============ НАСТРОЙКИ ИЗ ENV ============

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не установлен!")
    sys.exit(1)

API_ID = int(os.getenv("API_ID", 39328144))
API_HASH = os.getenv("API_HASH", "b4c02b2f6297f1b61d3073fd50629711")

WEBHOOK_PATH = "/webhook"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", "10000"))

# ============ 10 ШАБЛОНОВ ДЛЯ ЖАЛОБ ============

TEMPLATES = [
    "Здравствуйте! Прошу принять меры и заблокировать бота @{username}. Данный сервис нарушает правила Telegram и законодательство о персональных данных, занимаясь незаконным распространением конфиденциальной информации третьих лиц (паспорта, ИНН, СНИЛС, адреса и номера телефонов).",
    "Данный бот @{username} нарушает правила Telegram, распространяя личные данные пользователей без их согласия. Прошу заблокировать данный аккаунт.",
    "Бот @{username} занимается незаконным сбором и распространением персональных данных. Это нарушает политику конфиденциальности Telegram. Прошу принять меры.",
    "Прошу заблокировать бота @{username}. Данный сервис предоставляет доступ к личным данным третьих лиц, что является нарушением законодательства и правил Telegram.",
    "Бот @{username} нарушает правила Telegram, распространяя конфиденциальную информацию (паспорта, номера телефонов, адреса). Прошу заблокировать.",
    "Обращаю ваше внимание на бота @{username}, который занимается незаконной продажей личных данных. Прошу заблокировать данный аккаунт.",
    "Бот @{username} нарушает политику Telegram в отношении персональных данных. Прошу принять меры и заблокировать этот аккаунт.",
    "Данный бот @{username} распространяет личные данные третьих лиц без их согласия. Это нарушает правила Telegram и законодательство. Прошу заблокировать.",
    "Бот @{username} предоставляет доступ к конфиденциальной информации пользователей. Прошу заблокировать данный аккаунт за нарушение правил.",
    "Прошу принять меры в отношении бота @{username}, который нарушает правила Telegram, распространяя личные данные (паспорта, ИНН, адреса)."
]

# ============ ЛОГИРОВАНИЕ ============

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ============ ХРАНИЛИЩА ============

REPORT_SESSIONS: Dict[str, TelegramClient] = {}
active_tasks: Dict[str, asyncio.Task] = {}
stop_flags: Dict[str, bool] = {}
processed_bots: Set[str] = set()
blocked_bots: Set[str] = set()

# ============ СОСТОЯНИЯ ============

class ReportStates(StatesGroup):
    waiting_bot_name = State()
    waiting_bot_list = State()
    waiting_continuous_bot = State()

router = Router()

# ============ РАБОТА С СЕССИЯМИ ============

async def connect_session(name: str, entry) -> TelegramClient:
    try:
        if isinstance(entry, str):
            client = TelegramClient(StringSession(entry), API_ID, API_HASH)
        elif isinstance(entry, dict) and entry.get("type") == "file":
            client = TelegramClient(entry["path"], API_ID, API_HASH)
        else:
            client = TelegramClient(StringSession(entry.get("value", "")), API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return None
        client.flood_sleep_threshold = 0
        return client
    except Exception as e:
        logger.error(f"Ошибка подключения сессии {name}: {e}")
        return None

async def load_all_sessions():
    global REPORT_SESSIONS
    REPORT_SESSIONS.clear()
    
    env_raw = os.getenv("SESSION_STRINGS", "")
    env_lines = [ln.strip() for ln in env_raw.replace(",", "\n").splitlines() if ln.strip()]
    for i, ss in enumerate(env_lines):
        name = f"session{i+1}"
        client = await connect_session(name, ss)
        if client:
            REPORT_SESSIONS[name] = client
    
    logger.info(f"✅ Загружено сессий: {len(REPORT_SESSIONS)}")

async def get_sessions_list() -> list:
    return [(name, client) for name, client in REPORT_SESSIONS.items()]

# ============ ОТПРАВКА ЖАЛОБ ============

async def send_profile_report(client, entity, text: str) -> bool:
    try:
        await asyncio.wait_for(
            client(ReportPeerRequest(
                peer=entity,
                reason=InputReportReasonPersonalDetails(),
                message=text
            )),
            timeout=15
        )
        return True
    except Exception as e:
        logger.warning(f"Ошибка жалобы на профиль: {e}")
        return False

async def send_message_report(client, entity, message_id: int, text: str) -> bool:
    try:
        await asyncio.wait_for(
            client(ReportRequest(
                peer=entity,
                id=[message_id],
                option=b'',
                message=text
            )),
            timeout=15
        )
        return True
    except Exception as e:
        logger.warning(f"Ошибка жалобы на сообщение: {e}")
        return False

async def block_bot(client, entity) -> bool:
    try:
        await asyncio.wait_for(
            client(BlockRequest(id=entity)),
            timeout=10
        )
        return True
    except Exception as e:
        logger.warning(f"Ошибка блокировки бота: {e}")
        return False

async def get_bot_response(client, entity):
    try:
        await client.send_message(entity, "/start")
        await asyncio.sleep(1)
        
        for _ in range(10):
            msgs = await client.get_messages(entity, limit=2)
            if msgs and len(msgs) >= 2:
                last_msg = msgs[0]
                if last_msg.from_id and last_msg.from_id.user_id == entity.id:
                    return last_msg
            await asyncio.sleep(1)
        
        msgs = await client.get_messages(entity, limit=1)
        return msgs[0] if msgs else None
    except Exception as e:
        logger.warning(f"Ошибка получения сообщения от бота: {e}")
        return None

async def process_bot(client, username: str) -> dict:
    result = {
        "username": username,
        "profile_success": 0,
        "message_success": 0,
        "total": 0,
        "success": 0,
        "error": None,
        "message_id": None,
        "blocked": False,
        "template_used": None
    }
    
    try:
        entity = await asyncio.wait_for(client.get_entity(username), timeout=15)
    except Exception as e:
        result["error"] = f"Бот не найден: {e}"
        return result
    
    last_msg = await get_bot_response(client, entity)
    if last_msg:
        result["message_id"] = last_msg.id
    
    template = random.choice(TEMPLATES)
    result["template_used"] = template[:80] + "..."
    report_text = template.format(username=username.lstrip('@'))
    
    for _ in range(3):
        success = await send_profile_report(client, entity, report_text)
        if success:
            result["profile_success"] += 1
            result["success"] += 1
        result["total"] += 1
        await asyncio.sleep(random.uniform(1.0, 2.5))
    
    if last_msg and last_msg.id:
        for _ in range(3):
            success = await send_message_report(client, entity, last_msg.id, report_text)
            if success:
                result["message_success"] += 1
                result["success"] += 1
            result["total"] += 1
            await asyncio.sleep(random.uniform(1.0, 2.5))
    else:
        for _ in range(3):
            success = await send_profile_report(client, entity, report_text)
            if success:
                result["profile_success"] += 1
                result["success"] += 1
            result["total"] += 1
            await asyncio.sleep(random.uniform(1.0, 2.5))
        result["message_success"] = 0
    
    if result["success"] > 0:
        blocked = await block_bot(client, entity)
        if blocked:
            result["blocked"] = True
            blocked_bots.add(username)
    
    return result

async def search_bots(client, query: str) -> List[str]:
    results = []
    try:
        found = await client(SearchRequest(q=query, limit=25))
        for user in found.users:
            if getattr(user, 'bot', False) and getattr(user, 'username', None):
                results.append(f"@{user.username}")
                if len(results) >= 25:
                    break
    except Exception as e:
        logger.warning(f"Ошибка поиска ботов: {e}")
        try:
            entity = await client.get_entity(query)
            if getattr(entity, 'bot', False) and getattr(entity, 'username', None):
                results.append(f"@{entity.username}")
        except Exception:
            pass
    return results
    # ============ РЕЖИМ 1: РЕПОРТ НА СПИСОК ============

async def run_mass_report(bot: Bot, chat_id: int, bot_list: List[str], task_id: str, continuous: bool = False):
    status_msg = await bot.send_message(chat_id, f"🔄 Начинаю жалобы на {len(bot_list)} ботов...")
    results = []
    total = len(bot_list)
    current = 0
    
    try:
        sessions = await get_sessions_list()
        if not sessions:
            await status_msg.edit_text("❌ Нет доступных сессий!")
            return
        
        for username in bot_list:
            current += 1
            if stop_flags.get(task_id, False):
                await status_msg.edit_text(f"🛑 Остановлено! Обработано: {current-1}/{total}")
                break
            
            if continuous and username in processed_bots:
                continue
            
            await status_msg.edit_text(f"🔄 [{current}/{total}] {username}...")
            
            name, client = random.choice(sessions)
            result = await process_bot(client, username)
            
            if continuous and result.get("success", 0) > 0:
                processed_bots.add(username)
            
            results.append(result)
            await asyncio.sleep(random.uniform(0.5, 1.5))
        
        report_text = f"📊 ИТОГ\n\nОбработано: {len(results)}/{total}\n\n"
        for r in results:
            if r.get("error"):
                report_text += f"❌ {r['username']}: {r['error']}\n"
            else:
                template_preview = r.get("template_used", "не указан")
                report_text += (
                    f"✅ {r['username']}: "
                    f"профиль={r.get('profile_success', 0)}, "
                    f"сообщение={r.get('message_success', 0)}"
                    f"{' 🚫 заблокирован' if r.get('blocked') else ''}\n"
                    f"   📝 шаблон: {template_preview}\n"
                )
        
        if len(report_text) > 4000:
            report_text = report_text[:4000] + "\n... (обрезано)"
        
        await status_msg.edit_text(report_text)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")
    finally:
        if task_id in active_tasks:
            del active_tasks[task_id]
        if task_id in stop_flags:
            del stop_flags[task_id]

# ============ РЕЖИМ 2: НЕПРЕРЫВНЫЙ РЕПОРТ ============

async def run_continuous_report(bot: Bot, chat_id: int, bot_name: str, task_id: str):
    status_msg = await bot.send_message(chat_id, f"🔄 Запускаю непрерывный репорт на ботов по запросу '{bot_name}'...")
    
    try:
        sessions = await get_sessions_list()
        if not sessions:
            await status_msg.edit_text("❌ Нет доступных сессий!")
            return
        
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=1)
        total_reports = 0
        total_bots = 0
        cycle = 0
        
        while datetime.now() < end_time and not stop_flags.get(task_id, False):
            cycle += 1
            _, client = random.choice(sessions)
            
            await status_msg.edit_text(f"🔍 Цикл {cycle}: Ищу ботов по запросу '{bot_name}'...")
            
            found_bots = await search_bots(client, bot_name)
            new_bots = [b for b in found_bots if b not in processed_bots]
            
            if not new_bots:
                await status_msg.edit_text(f"⚠️ Цикл {cycle}: Новых ботов не найдено. Жду 30 сек...")
                await asyncio.sleep(30)
                continue
            
            await status_msg.edit_text(f"🔄 Цикл {cycle}: Найдено {len(new_bots)} новых ботов.")
            
            for username in new_bots[:10]:
                if stop_flags.get(task_id, False):
                    break
                
                processed_bots.add(username)
                total_bots += 1
                
                await status_msg.edit_text(f"🔄 [{total_bots}] {username}...")
                
                result = await process_bot(client, username)
                total_reports += result.get("success", 0)
                
                await asyncio.sleep(random.uniform(1.0, 2.5))
            
            elapsed = int((datetime.now() - start_time).total_seconds())
            remaining = max(0, 3600 - elapsed)
            minutes = remaining // 60
            seconds = remaining % 60
            
            await status_msg.edit_text(
                f"✅ Цикл {cycle} готов.\n"
                f"📊 Ботов: {total_bots}\n"
                f"📊 Жалоб: {total_reports}\n"
                f"⏳ Осталось: {minutes}м {seconds}с"
            )
            
            await asyncio.sleep(5)
        
        elapsed = int((datetime.now() - start_time).total_seconds())
        minutes = elapsed // 60
        seconds = elapsed % 60
        
        final_text = (
            f"🛑 НЕПРЕРЫВНЫЙ РЕПОРТ ЗАВЕРШЁН\n\n"
            f"⏳ Время: {minutes}м {seconds}с\n"
            f"🎯 Ботов: {total_bots}\n"
            f"📊 Жалоб: {total_reports}\n"
            f"🔄 Циклов: {cycle}"
        )
        await status_msg.edit_text(final_text)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")
    finally:
        if task_id in active_tasks:
            del active_tasks[task_id]
        if task_id in stop_flags:
            del stop_flags[task_id]
            # ============ КЛАВИАТУРЫ ============

def kb_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Найти ботов", callback_data="search_bot")],
        [InlineKeyboardButton(text="📋 Репорт на список", callback_data="mass_report")],
        [InlineKeyboardButton(text="🔄 Непрерывный репорт", callback_data="continuous_report")],
        [InlineKeyboardButton(text="📊 Статус", callback_data="sessions_status")],
        [InlineKeyboardButton(text="🛑 Остановить", callback_data="stop_report")],
    ])

def kb_back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])

# ============ ХЕНДЛЕРЫ ============

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🤖 MASS BOT REPORT TOOL v3.0\n\n"
        "Выберите действие:",
        reply_markup=kb_main_menu()
    )

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "🤖 MASS BOT REPORT TOOL v3.0\n\nВыберите действие:",
        reply_markup=kb_main_menu()
    )

@router.callback_query(F.data == "search_bot")
async def search_bot(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ReportStates.waiting_bot_name)
    await callback.message.edit_text(
        "🔍 Введите имя бота для поиска:\n\n"
        "После поиска вы получите список юзернеймов текстом.\n"
        "Скопируйте их и используйте в 'Репорт на список'.",
        reply_markup=kb_back_to_menu()
    )

@router.message(ReportStates.waiting_bot_name, F.text)
async def process_search_bot(message: Message, state: FSMContext):
    query = message.text.strip()
    if not query:
        await message.answer("❌ Введите имя для поиска")
        return
    
    status = await message.answer(f"🔍 Ищу ботов по запросу: {query}...")
    
    try:
        sessions = await get_sessions_list()
        if not sessions:
            await status.edit_text("❌ Нет доступных сессий!")
            return
        
        _, client = sessions[0]
        results = await search_bots(client, query)
        
        if not results:
            await status.edit_text(f"❌ Боты по запросу '{query}' не найдены.")
            return
        
        text = f"✅ Найдено {len(results)} ботов:\n\n"
        for username in results:
            text += f"{username}\n"
        text += "\n📋 Скопируйте этот список и используйте в 'Репорт на список'"
        
        await state.clear()
        await status.edit_text(text, reply_markup=kb_back_to_menu())
        
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}", reply_markup=kb_back_to_menu())
        await state.clear()

@router.callback_query(F.data == "mass_report")
async def mass_report(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ReportStates.waiting_bot_list)
    await callback.message.edit_text(
        "📋 Вставьте список юзернеймов ботов (по одному на строку):\n\n"
        "Пример:\n"
        "@bot1\n"
        "@bot2\n"
        "@bot3\n\n"
        "На каждого бота: 3 жалобы на профиль + 3 жалобы на сообщение.",
        reply_markup=kb_back_to_menu()
    )

@router.message(ReportStates.waiting_bot_list, F.text)
async def process_mass_report(message: Message, state: FSMContext):
    await state.clear()
    task_id = str(message.chat.id)
    
    if task_id in active_tasks and not active_tasks[task_id].done():
        await message.answer("⚠️ Уже идёт отправка! Используйте /stop")
        return
    
    sessions = await get_sessions_list()
    if not sessions:
        await message.answer("❌ Нет доступных сессий!")
        return
    
    lines = [ln.strip() for ln in message.text.splitlines() if ln.strip()]
    bot_list = []
    for ln in lines:
        if ln.startswith("@"):
            bot_list.append(ln)
        else:
            bot_list.append(f"@{ln}")
    
    if not bot_list:
        await message.answer("❌ Список пуст!")
        return
    
    await message.answer(f"🔄 Начинаю жалобы на {len(bot_list)} ботов...")
    
    stop_flags[task_id] = False
    task = asyncio.create_task(
        run_mass_report(message.bot, message.chat.id, bot_list, task_id, continuous=False)
    )
    active_tasks[task_id] = task

@router.callback_query(F.data == "continuous_report")
async def continuous_report(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ReportStates.waiting_continuous_bot)
    await callback.message.edit_text(
        "🔄 НЕПРЕРЫВНЫЙ РЕПОРТ\n\n"
        "Введите имя для поиска ботов.\n"
        "Бот будет искать новых ботов каждые 30 сек и отправлять жалобы.\n"
        "Работает ровно 1 час, затем останавливается.\n\n"
        "⚠️ Каждый бот: 3 профиль + 3 сообщение.",
        reply_markup=kb_back_to_menu()
    )

@router.message(ReportStates.waiting_continuous_bot, F.text)
async def process_continuous_report(message: Message, state: FSMContext):
    query = message.text.strip()
    if not query:
        await message.answer("❌ Введите имя для поиска")
        return
    
    await state.clear()
    task_id = str(message.chat.id)
    
    if task_id in active_tasks and not active_tasks[task_id].done():
        await message.answer("⚠️ Уже идёт отправка! Используйте /stop")
        return
    
    sessions = await get_sessions_list()
    if not sessions:
        await message.answer("❌ Нет доступных сессий!")
        return
    
    global processed_bots
    processed_bots.clear()
    
    await message.answer(f"🔄 Запускаю непрерывный репорт на 1 час по запросу '{query}'...")
    
    stop_flags[task_id] = False
    task = asyncio.create_task(
        run_continuous_report(message.bot, message.chat.id, query, task_id)
    )
    active_tasks[task_id] = task

@router.callback_query(F.data == "stop_report")
async def stop_report(callback: CallbackQuery):
    task_id = str(callback.message.chat.id)
    stop_flags[task_id] = True
    await callback.answer("🛑 Останавливаю...", show_alert=True)

@router.callback_query(F.data == "sessions_status")
async def sessions_status(callback: CallbackQuery):
    sessions = await get_sessions_list()
    text = f"📊 СЕССИИ\n\nВсего: {len(sessions)}\n\n"
    for name, _ in sessions:
        text += f"  ✅ {name}\n"
    if not sessions:
        text += "  ❌ Нет активных сессий"
    text += f"\n\n📊 Обработано ботов: {len(processed_bots)}"
    text += f"\n🚫 Заблокировано ботов: {len(blocked_bots)}"
    await callback.answer()
    await callback.message.edit_text(text, reply_markup=kb_back_to_menu())

# ============ WEBHOOK ============

async def webhook_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        update = Update(**data)
        await dp.feed_update(bot, update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=500)

async def health_check(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "sessions": len(REPORT_SESSIONS)})

async def keep_alive_loop():
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if not hostname:
        return
    url = f"https://{hostname}/health"
    await asyncio.sleep(10)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url, timeout=10) as resp:
                    logger.info(f"Keep-alive: {resp.status}")
            except Exception:
                pass
            await asyncio.sleep(150)

async def on_startup(app: web.Application):
    await load_all_sessions()
    
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'localhost')}{WEBHOOK_PATH}"
    if os.getenv('RENDER_EXTERNAL_HOSTNAME'):
        webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"
    
    try:
        await bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook: {webhook_url}")
        me = await bot.get_me()
        logger.info(f"Бот: @{me.username}")
    except Exception as e:
        logger.error(f"Ошибка старта: {e}")
    
    app["keep_alive_task"] = asyncio.create_task(keep_alive_loop())

async def on_shutdown(app: web.Application):
    task = app.get("keep_alive_task")
    if task:
        task.cancel()
    try:
        await bot.delete_webhook()
    except Exception:
        pass
    for _, client in REPORT_SESSIONS.items():
        try:
            await client.disconnect()
        except Exception:
            pass

# ============ ЗАПУСК ============

async def main():
    global bot, dp
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    await site.start()
    
    logger.info(f"Сервер запущен на порту {WEB_SERVER_PORT}")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Остановка...")
    finally:
        await runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    try:
        import aiohttp
    except ImportError:
        pass
    asyncio.run(main())
