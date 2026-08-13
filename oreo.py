import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import aiohttp

# ================= НАСТРОЙКИ =================
# ВАЖНО: цветные кнопки (style=...) требуют aiogram >= 3.20 (Bot API 9.4)
# Токен берётся из переменной окружения BOT_TOKEN — задай её в настройках
# сервиса на Render (Environment -> Add Environment Variable).
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = -1004420294467
WEBHOOK_PATH = "/webhook"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 8080))

# Картинка должна лежать в той же папке, что и этот файл
PHOTO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "set.jpg")

# Первый в списке — первый в кнопках
SELLER_USERNAMES = ["godcop", "Negot_iopp"]
# ============================================

PRICE_LIST = [
    (50, 3.49, 6.49),
    (75, 5.49, 8.49),
    (100, 6.99, 9.99),
    (150, 10.49, 13.49),
    (250, 17.49, 20.49),
    (350, 24.49, 27.49),
    (500, 34.99, 37.99),
    (750, 52.49, 55.49),
    (1000, 69.99, 72.99),
    (1500, 104.99, 107.99),
    (2500, 174.99, 177.99),
    (5000, 349.99, 352.99),
    (10000, 699.99, 702.99),
]

CATEGORIES = {
    "small":  {"title": "Маленький", "range": "50-500 ⭐",     "min": 0,    "max": 500},
    "medium": {"title": "Средний",   "range": "750-1500 ⭐",   "min": 501,  "max": 1500},
    "large":  {"title": "Большой",   "range": "2500-10000 ⭐", "min": 1501, "max": 10**9},
}

def get_category_id(stars: int) -> str:
    for cat_id, cat in CATEGORIES.items():
        if cat["min"] <= stars <= cat["max"]:
            return cat_id
    return "medium"

def packages_in_category(cat_id: str):
    cat = CATEGORIES[cat_id]
    return [p for p in PRICE_LIST if cat["min"] <= p[0] <= cat["max"]]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================= КЛАВИАТУРЫ =================
def get_subscribe_keyboard() -> InlineKeyboardMarkup:
    """Подписка на канал — синяя (primary), проверка — зелёная (success)"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="ПОДПИСАТЬСЯ НА КАНАЛ",
            url="https://t.me/+WPfMvpVjCehlNDQ6",
            style="primary"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="✅ Я ПОДПИСАЛСЯ — ПРОВЕРИТЬ",
            callback_data="check_sub",
            style="success"
        )
    )
    return builder.as_markup()

def get_categories_keyboard() -> InlineKeyboardMarkup:
    """Верхний уровень: выбор объёма пакета"""
    builder = InlineKeyboardBuilder()
    for cat_id, cat in CATEGORIES.items():
        builder.row(
            InlineKeyboardButton(
                text=cat['title'],
                callback_data=f"cat_{cat_id}",
                style="primary"
            )
        )
    return builder.as_markup()

def get_category_packages_keyboard(cat_id: str) -> InlineKeyboardMarkup:
    """Второй уровень: конкретные пакеты внутри категории, 2 в ряд"""
    builder = InlineKeyboardBuilder()
    for stars, official, our in packages_in_category(cat_id):
        btn_text = f"{stars} ⭐ — {our:.2f} BYN"
        builder.button(
            text=btn_text,
            callback_data=f"package_{stars}_{cat_id}",
            style="primary"
        )
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="🔙 НАЗАД К ОБЪЁМАМ", callback_data="back_to_categories")
    )
    return builder.as_markup()

def get_order_keyboard(cat_id: str) -> InlineKeyboardMarkup:
    """Кнопки оплаты (продавцы) — зелёные (success), назад — в свою категорию"""
    builder = InlineKeyboardBuilder()
    for username in SELLER_USERNAMES:
        builder.row(
            InlineKeyboardButton(
                text=f"💳 Написать @{username}",
                url=f"https://t.me/{username}",
                style="success"
            )
        )
    builder.row(
        InlineKeyboardButton(text="🔙 НАЗАД К ПАКЕТАМ", callback_data=f"cat_{cat_id}")
    )
    return builder.as_markup()

# ================= ПРОВЕРКА ПОДПИСКИ =================
async def check_subscription(user_id: int) -> bool:
    """Проверяет подписку пользователя на канал"""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

# ================= ПОКАЗ ЭКРАНОВ =================
async def show_categories(message_or_callback):
    """Показывает верхний уровень: выбор объёма пакета"""
    lines = "\n".join(f"<b>{cat['title']}: {cat['range']}</b>" for cat in CATEGORIES.values())
    text = f"⭐ <b>ПАКЕТЫ ЗВЁЗД</b> ⭐\n\n{lines}"
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer_photo(
            photo=FSInputFile(PHOTO_PATH),
            caption=text, parse_mode="HTML", reply_markup=get_categories_keyboard()
        )
    else:
        await message_or_callback.message.edit_caption(
            caption=text, parse_mode="HTML", reply_markup=get_categories_keyboard()
        )

async def show_category_packages(callback: CallbackQuery, cat_id: str):
    """Показывает пакеты внутри выбранной категории"""
    cat = CATEGORIES[cat_id]
    text = (
        f"⭐ <b>{cat['title'].upper()}</b> ⭐\n\n"
        f"<b>Выбери точный пакет ниже</b>"
    )
    await callback.message.edit_caption(
        caption=text, parse_mode="HTML", reply_markup=get_category_packages_keyboard(cat_id)
    )

async def show_subscribe_prompt(message_or_callback):
    """Показывает запрос на подписку"""
    subscribe_text = (
        "🔒 <b>ДЛЯ ИСПОЛЬЗОВАНИЯ БОТА НЕОБХОДИМА ПОДПИСКА НА КАНАЛ</b>\n\n"
        "<b>Подпишись и нажми кнопку ниже для проверки.</b>"
    )
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer_photo(
            photo=FSInputFile(PHOTO_PATH),
            caption=subscribe_text, parse_mode="HTML", reply_markup=get_subscribe_keyboard()
        )
    else:
        await message_or_callback.message.edit_caption(
            caption=subscribe_text, parse_mode="HTML", reply_markup=get_subscribe_keyboard()
        )

# ================= /start =================
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if await check_subscription(user_id):
        await show_categories(message)
    else:
        await show_subscribe_prompt(message)

# ================= "Я ПОДПИСАЛСЯ — ПРОВЕРИТЬ" =================
@dp.callback_query(F.data == "check_sub")
async def process_check_sub(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    if await check_subscription(user_id):
        await show_categories(callback)
    else:
        error_text = (
            "❌ <b>ТЫ ЕЩЁ НЕ ПОДПИСАЛСЯ!</b>\n\n"
            "<b>Подпишись на канал и нажми кнопку снова.</b>"
        )
        await callback.answer("Подписка не найдена", show_alert=True)
        await callback.message.edit_caption(
            caption=error_text, parse_mode="HTML", reply_markup=get_subscribe_keyboard()
        )

# ================= ВЫБОР КАТЕГОРИИ (ОБЪЁМА) =================
@dp.callback_query(F.data.startswith("cat_"))
async def process_category(callback: CallbackQuery):
    await callback.answer()

    if not await check_subscription(callback.from_user.id):
        await show_subscribe_prompt(callback)
        return

    cat_id = callback.data.split("_", 1)[1]
    if cat_id in CATEGORIES:
        await show_category_packages(callback, cat_id)

# ================= НАЗАД К КАТЕГОРИЯМ =================
@dp.callback_query(F.data == "back_to_categories")
async def process_back_to_categories(callback: CallbackQuery):
    await callback.answer()
    await show_categories(callback)

# ================= ВЫБОР КОНКРЕТНОГО ПАКЕТА =================
@dp.callback_query(F.data.startswith("package_"))
async def process_package(callback: CallbackQuery):
    await callback.answer()

    # На всякий случай перепроверяем подписку — вдруг человек отписался
    if not await check_subscription(callback.from_user.id):
        await show_subscribe_prompt(callback)
        return

    # package_<stars>_<cat_id>
    _, stars_str, cat_id = callback.data.split("_", 2)
    stars = int(stars_str)
    package_info = next((p for p in PRICE_LIST if p[0] == stars), None)

    if package_info:
        official, our = package_info[1], package_info[2]
        order_text = (
            f"✅ <b>ЗАКАЗ ПРИНЯТ</b>\n\n"
            f"<b>Пакет: {stars} ⭐</b>\n"
            f"<b>Официальная цена: {official:.2f} BYN</b>\n"
            f"<b>Твоя цена: {our:.2f} BYN</b>\n\n"
            f"<b>Напиши одному из продавцов для оплаты:</b>"
        )
        await callback.message.edit_caption(
            caption=order_text, parse_mode="HTML", reply_markup=get_order_keyboard(cat_id)
        )

# ================= WEBHOOK HANDLER ДЛЯ RENDER =================
async def webhook_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.feed_update(bot, update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=500)

async def health_check(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})

async def keep_alive_loop() -> None:
    """
    Подстраховка от сна на Render. НЕ панацея: если инстанс уже уснул,
    эта корутина тоже не работает (процесс остановлен), поэтому дополнительно
    настрой внешний пинг (UptimeRobot / cron-job.org) на /health каждые 5 минут —
    только внешний пинг умеет БУДИТЬ уже уснувший бесплатный инстанс.
    """
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if not hostname:
        logger.warning("RENDER_EXTERNAL_HOSTNAME не задан — внутренний keep-alive выключен")
        return

    url = f"https://{hostname}/health"
    await asyncio.sleep(10)

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    logger.info(f"Keep-alive: {resp.status}")
            except Exception as e:
                logger.warning(f"Keep-alive ping не удался: {e}")
            await asyncio.sleep(300)  # каждые 5 минут — с запасом до 15-минутного тайм-аута Render

async def on_startup(app: web.Application) -> None:
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'localhost')}{WEBHOOK_PATH}"
    try:
        await bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook установлен: {webhook_url}")
        me = await bot.get_me()
        logger.info(f"Бот запущен: @{me.username}")
    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}")
    app["keep_alive_task"] = asyncio.create_task(keep_alive_loop())

async def on_shutdown(app: web.Application) -> None:
    task = app.get("keep_alive_task")
    if task:
        task.cancel()
    try:
        await bot.delete_webhook()
        logger.info("Webhook удален")
    except Exception:
        pass

# ================= ЗАПУСК =================
async def main() -> None:
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
    asyncio.run(main())
                
