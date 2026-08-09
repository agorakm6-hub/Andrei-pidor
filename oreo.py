"""
Скрипт прогрева Telegram аккаунта для деплоя на Render.
Отправляет сообщения в "Избранное" с заданной периодичностью.

Переменные окружения:
  API_ID                  — твой API ID (my.telegram.org)
  API_HASH                — твой API Hash (my.telegram.org)
  SESSION_STRING          — строка сессии Telethon (обязательно)
  RENDER_EXTERNAL_HOSTNAME — Render подставляет сам
  PORT                     — Render подставляет сам
"""
import asyncio
import logging
import os
import random
from datetime import datetime, timedelta

import aiohttp
from aiohttp import web
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ============ КОНФИГ ============
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")

if not API_ID:
    logger.error("❌ Не задан API_ID")
    raise SystemExit(1)
if not API_HASH:
    logger.error("❌ Не задан API_HASH")
    raise SystemExit(1)
if not SESSION_STRING:
    logger.error("❌ Не задана SESSION_STRING")
    raise SystemExit(1)

WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", "10000"))

# ============ СЛОВАРИ СЛОВ ДЛЯ ПРОГРЕВА ============
RU_WORDS = [
    "привет", "как дела", "что нового", "погода", "сегодня", "завтра",
    "работа", "дом", "семья", "друзья", "отдых", "музыка", "кино",
    "книга", "спорт", "здоровье", "еда", "кофе", "чай", "вечер",
    "утро", "солнце", "небо", "море", "горы", "лес", "город",
    "машина", "улица", "дорога", "время", "жизнь", "любовь", "счастье",
    "успех", "идея", "план", "цель", "мечта", "надежда", "вера",
    "свобода", "творчество", "вдохновение", "радость", "улыбка", "смех",
    "песня", "танец", "игра", "чудо", "сказка", "звезда", "луна",
    "ветер", "дождь", "снег", "весна", "лето", "осень", "зима",
    "птица", "цветок", "дерево", "река", "озеро", "поле", "сад",
    "хлеб", "молоко", "сыр", "фрукты", "овощи", "яблоко", "мед",
    "ночь", "день", "свет", "тьма", "тишина", "звук", "слово",
    "мысль", "чувство", "эмоция", "память", "опыт", "мудрость", "сила",
    "путь", "движение", "скорость", "высота", "глубина", "широта", "простор",
    "огонь", "вода", "земля", "воздух", "энергия", "тепло", "холод",
    "правда", "честь", "долг", "совесть", "душа", "сердце", "разум",
    "стиль", "мода", "дизайн", "цвет", "форма", "ритм", "вкус",
    "сон", "отдых", "тишина", "покой", "воля", "дух", "тело"
]

EN_WORDS = [
    "hello", "world", "peace", "love", "life", "hope", "dream",
    "success", "music", "art", "nature", "ocean", "mountain", "forest",
    "city", "travel", "adventure", "discovery", "future", "present",
    "moment", "time", "space", "energy", "light", "shadow", "spirit",
    "wisdom", "knowledge", "truth", "beauty", "harmony", "balance",
    "freedom", "courage", "strength", "joy", "gratitude", "kindness",
    "passion", "creativity", "inspiration", "wonder", "magic", "star",
    "moon", "wind", "rain", "snow", "spring", "summer", "autumn",
    "winter", "bird", "flower", "tree", "river", "lake", "garden",
    "bread", "honey", "fruit", "apple", "berry", "grape", "lemon",
    "night", "day", "dawn", "dusk", "silence", "sound", "word",
    "thought", "feeling", "memory", "wisdom", "power", "glory", "honor",
    "fire", "water", "earth", "air", "storm", "thunder", "rainbow",
    "truth", "faith", "destiny", "soul", "heart", "mind", "spirit",
    "smile", "laughter", "dance", "song", "story", "legend", "myth",
    "style", "design", "color", "shape", "rhythm", "taste", "dream"
]

# ============ ТЕКСТЫ ДЛЯ ВТОРОГО ЭТАПА (50-300 символов) ============
LONG_TEXTS_RU = [
    "Сегодня замечательный день для того, чтобы начать что-то новое. Каждое утро приносит нам возможность изменить свою жизнь к лучшему. Главное — не упустить этот шанс и сделать первый шаг навстречу своей мечте.",
    "Читал интересную статью о том, как технологии меняют нашу повседневную жизнь. Искусственный интеллект уже помогает врачам ставить диагнозы, а беспилотные автомобили становятся реальностью. Удивительное время!",
    "Вчера посмотрел отличный фильм о путешествиях. Там показывали удивительные места в Исландии — водопады, гейзеры, северное сияние. Обязательно нужно там побывать хотя бы раз в жизни.",
    "Задумался о важности здорового образа жизни. Регулярные прогулки на свежем воздухе, правильное питание и хороший сон — основа всего. Пора записаться в спортзал.",
    "Музыка обладает удивительной силой — она может поднять настроение за считанные секунды. Составил себе плейлист для утренней зарядки, теперь просыпаться стало намного легче.",
    "Прочитал книгу о психологии привычек. Оказывается, чтобы сформировать новую привычку, нужно всего 21 день регулярной практики. Начинаю эксперимент с утренними пробежками.",
    "Как же приятно иногда просто выйти на прогулку без телефона и наушников. Слушать пение птиц, шум ветра в листве, чувствовать запах свежей травы после дождя.",
    "Начал изучать испанский язык. Сначала было сложно, но сейчас уже могу поддержать простой разговор. Говорят, что полное погружение в языковую среду — самый быстрый способ выучить.",
    "Приготовил сегодня потрясающий ужин — пасту с морепродуктами в сливочном соусе. Рецепт нашел на кулинарном канале, добавил немного своих специй.",
    "Фотография — это искусство останавливать время. Сегодня сделал несколько снимков заката с крыши. Игра света и теней была просто волшебной.",
    "Выходные провел на природе с палаткой. Костер, гитара, звездное небо — что еще нужно для полного счастья? Разве что комаров было многовато.",
    "Занимаюсь ремонтом в квартире. Это оказалось сложнее, чем я думал, но результат того стоит. Особенно горжусь стеллажом, который собрал своими руками.",
    "Посетил выставку современного искусства. Не все работы были мне понятны, но некоторые инсталляции действительно заставили задуматься о смысле жизни.",
    "Решил освоить медитацию. Говорят, что даже 10 минут в день помогают снизить уровень стресса и улучшить концентрацию. Попробую, хуже точно не будет.",
    "История Древнего Рима меня всегда завораживала. Как одна цивилизация могла так сильно повлиять на весь современный мир — от права до архитектуры.",
    "Катался сегодня на велосипеде по набережной. Ветер в лицо, солнце, хорошая музыка в наушниках — идеальный способ разгрузить голову после работы.",
    "Научился готовить домашний хлеб на закваске. Процесс долгий, но аромат свежей выпечки, который наполняет весь дом, стоит всех усилий.",
    "Астрономия — невероятно интересная наука. Смотрел документальный фильм про черные дыры и до сих пор под впечатлением от масштабов Вселенной.",
    "Решил навести порядок в своих заметках. Столько интересных идей и мыслей накопилось за год — пора разобрать и что-то начать реализовывать.",
    "Посадил на балконе зелень — базилик, мяту, розмарин. Теперь у меня всегда свежие травы для чая и готовки. Заодно и воздух стал приятнее.",
    "Кофе — это целая культура. Сегодня попробовал новый сорт из Эфиопии с нотками цитруса и шоколада. Вкус просто потрясающий.",
    "Вспомнил детство, когда мы строили шалаши во дворе. Самое беззаботное время — когда главной проблемой было успеть домой до темноты.",
    "Иногда полезно просто ничего не планировать и плыть по течению. Спонтанные решения часто приводят к самым интересным приключениям.",
    "Чайная церемония — это целое искусство. Японцы правы: когда завариваешь чай с полным вниманием к процессу, он становится намного вкуснее.",
    "Составил список книг, которые хочу прочитать до конца года. Оказалось, что если читать по 30 страниц в день, можно осилить около 50 книг.",
    "Записался на курсы по фотографии. Хочу научиться не просто нажимать кнопку, а понимать композицию, свет и цвет.",
    "Сделал генеральную уборку и нашел кучу вещей, о которых давно забыл. Отличный повод отдать ненужное на благотворительность.",
    "Пробовал сегодня йогу на рассвете в парке. Ощущения непередаваемые — тело просыпается вместе с природой, наполняясь энергией.",
    "Море — это лучшее лекарство от всего. Шум волн, соленый воздух, бескрайний горизонт — все проблемы сразу кажутся такими мелкими.",
    "Начал вести дневник благодарности. Каждый вечер записываю три вещи, за которые благодарен прошедшему дню. Настроение стало заметно лучше.",
    "Случайно нашел старые фотографии с друзьями. Столько теплых воспоминаний нахлынуло. Надо почаще встречаться, а не только в чатах переписываться.",
    "Смотрел интервью с известным предпринимателем. Его главный совет: не бояться ошибок, потому что каждая неудача — это шаг к успеху.",
    "Погода сегодня просто сказочная — тепло, легкий ветерок, ни облачка. Идеальный день для пикника в парке с хорошей компанией.",
    "Увлекся настольными играми. Это отличный способ провести время с друзьями, развить стратегическое мышление и просто повеселиться.",
    "Прочитал, что комнатные растения не только украшают интерьер, но и очищают воздух. Купил себе пару новых зеленых питомцев.",
    "Утренняя пробежка вдоль реки — теперь моя любимая рутина. Город еще спит, воздух свежий, мысли чистые. Лучшее начало дня."
]

LONG_TEXTS_EN = [
    "Today is a wonderful day to start something new. Every morning brings us an opportunity to change our lives for the better. The main thing is not to miss this chance and take the first step towards your dream.",
    "I was reading an interesting article about how technology is changing our daily lives. Artificial intelligence is already helping doctors make diagnoses, and self-driving cars are becoming a reality. What an amazing time we live in!",
    "Yesterday I watched a great movie about traveling. It showed incredible places in Iceland — waterfalls, geysers, the northern lights. I definitely need to visit there at least once in my lifetime.",
    "Been thinking about the importance of a healthy lifestyle. Regular walks in the fresh air, proper nutrition and good sleep are the foundation of everything. Time to join a gym.",
    "Music has an amazing power — it can lift your spirits in seconds. I made myself a playlist for morning exercises, now waking up has become much easier and more enjoyable.",
    "Just finished reading a book about habit psychology. Apparently, it only takes 21 days of consistent practice to form a new habit. Starting an experiment with morning jogging tomorrow.",
    "How nice it is sometimes to go for a walk without a phone or headphones. Listening to birds singing, the wind rustling in the leaves, smelling fresh grass after the rain.",
    "Started learning Spanish recently. It was difficult at first, but now I can hold a simple conversation. They say full immersion is the fastest way to learn a language.",
    "Cooked an amazing dinner tonight — pasta with seafood in creamy sauce. Found the recipe on a cooking channel and added some of my own spices to it.",
    "Photography is the art of stopping time. Took some sunset shots from the rooftop today. The play of light and shadows was absolutely magical.",
    "Spent the weekend camping in nature. A campfire, a guitar, a starry sky — what else do you need for complete happiness? Well, maybe fewer mosquitoes.",
    "Working on renovating my apartment. It turned out to be harder than I thought, but the result is worth it. Especially proud of the bookshelf I built myself.",
    "Visited a modern art exhibition today. Not all works were clear to me, but some installations really made me think about the meaning of life.",
    "Decided to try meditation. They say even 10 minutes a day can reduce stress levels and improve concentration. Worth giving it a shot.",
    "The history of Ancient Rome has always fascinated me. How one civilization could influence the entire modern world so much — from law to architecture.",
    "Went cycling along the embankment today. Wind in my face, sunshine, good music in my headphones — the perfect way to clear my head after work.",
    "Learned how to bake homemade sourdough bread. The process is long, but the aroma of fresh baking filling the whole house is worth all the effort.",
    "Astronomy is an incredibly interesting science. Watched a documentary about black holes and I'm still impressed by the scale of the Universe.",
    "Decided to organize my notes today. So many interesting ideas and thoughts have accumulated over the year — time to sort them out and start implementing.",
    "Planted some herbs on my balcony — basil, mint, rosemary. Now I always have fresh herbs for tea and cooking. The air has become nicer too.",
    "Coffee is a whole culture. Tried a new variety from Ethiopia today with notes of citrus and chocolate. The taste is absolutely amazing.",
    "Remembered my childhood when we used to build tree houses in the yard. The most carefree time — when the biggest problem was getting home before dark.",
    "Sometimes it's good to plan nothing and just go with the flow. Spontaneous decisions often lead to the most interesting adventures.",
    "The tea ceremony is a whole art form. The Japanese are right: when you brew tea with full attention to the process, it becomes much tastier.",
    "Made a list of books I want to read by the end of the year. Turns out if you read 30 pages a day, you can get through about 50 books.",
    "Signed up for photography courses. I want to learn not just to press a button, but to understand composition, light and color.",
    "Did a deep cleaning and found a bunch of things I had long forgotten about. Great opportunity to donate unnecessary stuff to charity.",
    "Tried yoga at dawn in the park today. The sensations are indescribable — the body wakes up together with nature, filling with energy.",
    "The sea is the best medicine for everything. The sound of waves, salty air, endless horizon — all problems immediately seem so small.",
    "Started keeping a gratitude journal. Every evening I write down three things I'm grateful for about the day. My mood has noticeably improved.",
    "Accidentally found old photos with friends. So many warm memories came flooding back. We should meet up more often, not just chat online.",
    "Watched an interview with a famous entrepreneur. His main advice: don't be afraid of mistakes, because every failure is a step towards success.",
    "The weather today is just fantastic — warm, light breeze, not a cloud in sight. Perfect day for a picnic in the park with good company.",
    "Got into board games recently. It's a great way to spend time with friends, develop strategic thinking, and just have fun.",
    "Read that indoor plants not only decorate the interior but also purify the air. Bought myself a couple of new green pets today.",
    "Morning jogging along the river is now my favorite routine. The city is still asleep, the air is fresh, thoughts are clear. The best way to start the day.",
    "Started learning to play the guitar. My fingers hurt like hell, but when you manage to play even a simple melody, it feels absolutely amazing.",
    "The smell of freshly brewed coffee in the morning is one of life's simplest yet greatest pleasures. It sets the mood for the entire day.",
    "Just realized how important it is to disconnect from social media sometimes. Spent the whole day offline and felt so much more productive and peaceful.",
    "Rediscovering old music albums from my teenage years. It's amazing how certain songs can instantly transport you back to specific moments in time."
]
def generate_short_message() -> str:
    """Генерирует короткое сообщение (1-3 слова)"""
    if random.random() < 0.5:
        words = random.sample(RU_WORDS, random.randint(1, 3))
        return " ".join(words).capitalize()
    else:
        words = random.sample(EN_WORDS, random.randint(1, 3))
        return " ".join(words).capitalize()


def generate_long_message() -> str:
    """Генерирует более длинное сообщение (50-300 символов)"""
    if random.random() < 0.5:
        return random.choice(LONG_TEXTS_RU)
    else:
        return random.choice(LONG_TEXTS_EN)


# ============ ОСНОВНАЯ ЛОГИКА ПРОГРЕВА ============

class AccountWarmer:
    def __init__(self, api_id: int, api_hash: str, session_string: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.client: TelegramClient | None = None
        self.is_running = False
        self.start_time: datetime | None = None

    async def start(self):
        """Запуск клиента и прогрева"""
        self.client = TelegramClient(
            StringSession(self.session_string),
            self.api_id,
            self.api_hash
        )
        
        try:
            await self.client.connect()
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            raise

        if not await self.client.is_user_authorized():
            logger.error("❌ Сессия не авторизована! Проверьте SESSION_STRING")
            raise SystemExit(1)

        me = await self.client.get_me()
        logger.info(f"✅ Авторизован как: {me.first_name} (@{me.username or 'нет username'})")
        
        self.is_running = True
        self.start_time = datetime.now()
        
        asyncio.create_task(self._warming_loop())

    async def _warming_loop(self):
        """Цикл прогрева"""
        logger.info("🔥 Запуск цикла прогрева аккаунта...")
        
        while self.is_running:
            try:
                elapsed = datetime.now() - self.start_time
                
                if elapsed < timedelta(hours=1):
                    message = generate_short_message()
                    logger.info(f"📝 [Короткое] Отправка: {message}")
                else:
                    message = generate_long_message()
                    logger.info(f"📝 [Длинное] Отправка ({len(message)} символов): {message[:50]}...")
                
                await self.client.send_message('me', message)
                logger.info("✅ Сообщение отправлено")
                
                await asyncio.sleep(5)
                
            except FloodWaitError as e:
                logger.warning(f"⏳ FloodWait: ждем {e.seconds} секунд")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке: {e}")
                await asyncio.sleep(10)

    async def stop(self):
        """Остановка прогрева"""
        self.is_running = False
        if self.client:
            await self.client.disconnect()
            logger.info("👋 Клиент отключен")


# ============ ВЕБ-СЕРВЕР ДЛЯ RENDER (АНТИ-СЛИП) ============

warmer: AccountWarmer | None = None


async def health_check(request: web.Request) -> web.Response:
    status = "warming" if warmer and warmer.is_running else "stopped"
    elapsed = str(datetime.now() - warmer.start_time) if warmer and warmer.start_time else "N/A"
    return web.json_response({
        "status": "ok",
        "warmer": status,
        "uptime": elapsed
    })


async def keep_alive_loop() -> None:
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if not hostname:
        logger.info("ℹ️ RENDER_EXTERNAL_HOSTNAME не задан — keep-alive отключён")
        return
    url = f"https://{hostname}/health"
    await asyncio.sleep(10)
    async with aiohttp.ClientSession() as session:
        while True:
            success = False
            for attempt in range(3):
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        logger.info(f"🔄 Keep-alive: {resp.status}")
                        success = True
                        break
                except Exception as e:
                    logger.warning(f"⚠️ Keep-alive ошибка (попытка {attempt + 1}/3): {e}")
                    await asyncio.sleep(5)
            if not success:
                logger.error("❌ Keep-alive провален")
            await asyncio.sleep(150)


async def main() -> None:
    global warmer

    warmer = AccountWarmer(API_ID, API_HASH, SESSION_STRING)
    await warmer.start()

    app = web.Application()
    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)
    
    asyncio.create_task(keep_alive_loop())

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    await site.start()
    logger.info(f"🚀 Веб-сервер на порту {WEB_SERVER_PORT}")

    try:
        await asyncio.Event().wait()
    finally:
        await warmer.stop()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
