import "dotenv/config";
import http from "http";
import https from "https";
import crypto from "crypto";
import { Bot, session, webhookCallback } from "grammy";
import { TelegramClient, Api } from "telegram";
import { StringSession } from "telegram/sessions/index.js";

/* ---------- CONFIG ---------- */

function env(name, required = true) {
  const val = process.env[name] ?? "";
  if (required && !val) throw new Error(`Переменная окружения ${name} не задана`);
  return val;
}

const BOT_TOKEN = env("BOT_TOKEN");
const API_ID = Number(env("API_ID"));
const API_HASH = env("API_HASH");
const SESSION_STRING = env("SESSION_STRING");
const POLL_INTERVAL_MS = Number(env("POLL_INTERVAL_MS", false) || "3000"); // раз в сколько проверять
const MAX_DURATION_MS = Number(env("MAX_DURATION_MS", false) || String(60 * 60 * 1000)); // максимум 1 час

// Вебхук/анти-слип — по желанию, см. README. Без переменных ниже бот работает через polling.
const PORT = Number(process.env.PORT || 10000);
const EXTERNAL_URL = process.env.RENDER_EXTERNAL_URL || process.env.WEBHOOK_URL || "";
const USE_WEBHOOK = Boolean(EXTERNAL_URL);
const WEBHOOK_PATH = `/bot${BOT_TOKEN}`;
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || crypto.randomBytes(24).toString("hex");

/* ---------- USERBOT (MTProto, проверка живости аккаунта) ---------- */

const tgClient = new TelegramClient(new StringSession(SESSION_STRING), API_ID, API_HASH, {
  connectionRetries: 5,
});
let tgStarted = false;

async function userbotStart() {
  if (!tgStarted) {
    await tgClient.connect();
    tgStarted = true;
  }
}

async function userbotStop() {
  if (tgStarted) {
    await tgClient.disconnect();
    tgStarted = false;
  }
}

/**
 * Проверяет, жив ли аккаунт по юзернейму.
 *
 * Нюанс: и самоудаление, и бан за нарушение TOS выглядят для стороннего
 * наблюдателя одинаково — резолв юзернейма либо перестаёт находить
 * аккаунт (USERNAME_NOT_OCCUPIED — юзернейм освободился), либо
 * возвращает пользователя с флагом deleted=true. Достоверно отличить
 * "сам удалился" от "забанен модерацией" средствами клиентского API
 * нельзя — это ограничение, а не баг бота.
 *
 * Возвращает одно из: "alive" | "banned_or_deleted" | "unknown"
 */
async function checkByUsername(username) {
  try {
    const result = await tgClient.invoke(new Api.contacts.ResolveUsername({ username }));
    const user = result.users?.[0];
    if (!user) return "banned_or_deleted";
    if (user.deleted) return "banned_or_deleted";
    return "alive";
  } catch (e) {
    const msg = String(e?.errorMessage || e?.message || e);
    if (msg.includes("USERNAME_NOT_OCCUPIED") || msg.includes("USERNAME_INVALID")) {
      return "banned_or_deleted";
    }
    console.warn(`⚠️ Ошибка проверки @${username}: ${msg}`);
    return "unknown";
  }
}

/**
 * Проверяет аккаунт по числовому ID.
 *
 * ОГРАНИЧЕНИЕ (честно): чтобы обратиться к пользователю по ID, MTProto
 * требует access_hash, который есть только если наша сессия уже
 * "видела" этот аккаунт — в общем чате, контактах, переписке и т.п.
 * Для полностью незнакомого ID (с которым сессия никогда не
 * пересекалась) резолв упадёт с самого начала — это не баг, а то,
 * как работает Telegram API. Юзернейм в этом смысле надёжнее: он
 * резолвится без предварительного знакомства.
 */
async function checkById(id) {
  try {
    const entity = await tgClient.getEntity(id);
    if (!entity) return "banned_or_deleted";
    if (entity.deleted) return "banned_or_deleted";
    return "alive";
  } catch (e) {
    const msg = String(e?.errorMessage || e?.message || e);
    if (msg.includes("Cannot find any entity") || msg.includes("No user has") || msg.includes("PEER_ID_INVALID")) {
      return "unknown"; // не факт, что забанен — может, сессия просто не может его найти
    }
    console.warn(`⚠️ Ошибка проверки id ${id}: ${msg}`);
    return "unknown";
  }
}

function parseTarget(input) {
  const trimmed = input.trim().replace(/^@/, "");
  if (/^\d+$/.test(trimmed)) {
    return { type: "id", value: Number(trimmed), display: trimmed };
  }
  return { type: "username", value: trimmed, display: `@${trimmed}` };
}

async function checkAccountStatus(type, value) {
  return type === "username" ? checkByUsername(value) : checkById(value);
}

/** Достаёт имя/юзернейм/id для стартового сообщения. null, если не удалось найти. */
async function getAccountInfo(type, value) {
  try {
    let user;
    if (type === "username") {
      const result = await tgClient.invoke(new Api.contacts.ResolveUsername({ username: value }));
      user = result.users?.[0];
    } else {
      user = await tgClient.getEntity(value);
    }
    if (!user) return null;
    const fullName = [user.firstName, user.lastName].filter(Boolean).join(" ") || "(без имени)";
    return {
      fullName,
      username: user.username ? `@${user.username}` : null,
      id: String(user.id),
    };
  } catch {
    return null;
  }
}

/* ---------- RAW BOT API (цветные кнопки) ---------- */

const API_ROOT = `https://api.telegram.org/bot${BOT_TOKEN}`;

function button(text, callback_data, style) {
  return style ? { text, callback_data, style } : { text, callback_data };
}

function keyboard(rows) {
  return { inline_keyboard: rows };
}

async function apiPost(method, payload) {
  const res = await fetch(`${API_ROOT}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!data.ok) throw new Error(`Telegram API error on ${method}: ${JSON.stringify(data)}`);
  return data.result;
}

async function sendMessage(chatId, text, replyMarkup) {
  return apiPost("sendMessage", {
    chat_id: chatId,
    text,
    ...(replyMarkup ? { reply_markup: replyMarkup } : {}),
  });
}

async function editMessageText(chatId, messageId, text, replyMarkup) {
  return apiPost("editMessageText", {
    chat_id: chatId,
    message_id: messageId,
    text,
    ...(replyMarkup ? { reply_markup: replyMarkup } : {}),
  });
}

/* ---------- ФОРМАТИРОВАНИЕ ВРЕМЕНИ ---------- */

function formatDuration(ms) {
  const totalSec = Math.floor(ms / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min} мин ${sec} сек`;
}

/* ---------- BOT ---------- */

const bot = new Bot(BOT_TOKEN);
bot.use(session({ initial: () => ({ waitingUsername: false }) }));

// Открыт для всех (стресс-тест с разных аккаунтов)

// Для стресс-теста бот открыт для всех — каждый чат мониторится
// независимо, ключ — chatId. Один чат = один активный мониторинг за раз.
const activeMonitors = new Map();

const WELCOME_TEXT =
  "Добро пожаловать.\n\n" +
  "Пришлите юзернейм или ID пользователя/бота для мониторинга. " +
  "Когда указанный аккаунт будет заблокирован, мы вам сообщим.";

function monitoringKeyboard() {
  return keyboard([[button("Остановить", "stop_monitor", "danger")]]);
}

bot.command("start", async (ctx) => {
  ctx.session.waitingUsername = true;
  await sendMessage(ctx.chat.id, WELCOME_TEXT);
});

function stopMonitor(chatId) {
  const m = activeMonitors.get(chatId);
  if (m) {
    clearInterval(m.timer);
    clearTimeout(m.timeout);
    activeMonitors.delete(chatId);
  }
}

bot.on("message:text", async (ctx) => {
  if (!ctx.session.waitingUsername) return;
  if (ctx.message.text.startsWith("/")) return;

  const chatId = ctx.chat.id;

  if (activeMonitors.has(chatId)) {
    await sendMessage(chatId, "Уже идёт мониторинг другого аккаунта в этом чате — сначала остановите его кнопкой ниже.", monitoringKeyboard());
    return;
  }

  const target = parseTarget(ctx.message.text);
  ctx.session.waitingUsername = false;

  // Для обоих типов ввода сразу тянем полную инфо об аккаунте — заодно
  // это и есть проверка, что сессия вообще способна его найти (особенно
  // важно для ID, см. ограничение выше).
  const info = await getAccountInfo(target.type, target.value);
  if (!info) {
    await sendMessage(
      chatId,
      target.type === "id"
        ? `Не получилось найти аккаунт с ID ${target.display}. Для мониторинга по ID нужно, чтобы наша сессия уже "видела" этот аккаунт (общий чат, переписка, контакты). Попробуй юзернейм вместо ID, если он есть.`
        : `Не получилось найти аккаунт ${target.display}. Проверь юзернейм и попробуй снова.`
    );
    return;
  }

  const sent = await sendMessage(
    chatId,
    `Мониторинг запущен на:\n\n` +
      `Имя: ${info.fullName}\n` +
      `Юзернейм: ${info.username ?? "отсутствует"}\n` +
      `ID: ${info.id}\n\n` +
      `Проверяю каждые ${Math.round(POLL_INTERVAL_MS / 1000)} сек, максимум час.\n` +
      `При окончании мониторинга вы получите уведомление.`,
    monitoringKeyboard()
  );

  const messageId = sent.message_id;
  const startedAt = Date.now();

  const timer = setInterval(async () => {
    const status = await checkAccountStatus(target.type, target.value);
    if (status === "banned_or_deleted") {
      const elapsed = Date.now() - startedAt;
      stopMonitor(chatId);
      await editMessageText(
        chatId,
        messageId,
        `Мониторинг завершён\n\nПоддержка отреагировала на нарушителя ${target.display} за ${formatDuration(elapsed)}.`
      );
    }
    // status === "alive" или "unknown" — просто ждём следующей проверки
  }, POLL_INTERVAL_MS);

  const timeout = setTimeout(async () => {
    stopMonitor(chatId);
    await editMessageText(chatId, messageId, `Мониторинг завершён\n\nИзменений нет. Аккаунт ${target.display} цел.`);
  }, MAX_DURATION_MS);

  activeMonitors.set(chatId, { display: target.display, messageId, startedAt, timer, timeout });
});

bot.callbackQuery("stop_monitor", async (ctx) => {
  const chatId = ctx.chat.id;
  const m = activeMonitors.get(chatId);
  if (!m) {
    await ctx.answerCallbackQuery({ text: "Мониторинг уже не идёт" });
    return;
  }
  const { display, messageId, startedAt } = m;
  const elapsed = Date.now() - startedAt;
  stopMonitor(chatId);
  await editMessageText(chatId, messageId, `Мониторинг остановлен вручную\n\n${display}, длительность: ${formatDuration(elapsed)}.`);
  await ctx.answerCallbackQuery();
});

/* ---------- ЗАПУСК: webhook или polling + анти-слип ---------- */

async function keepAliveLoop() {
  const url = `${EXTERNAL_URL}/health`;
  await new Promise((r) => setTimeout(r, 10000));
  while (true) {
    let success = false;
    for (let attempt = 1; attempt <= 3 && !success; attempt++) {
      try {
        const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
        console.log(`🔄 Keep-alive пинг: ${res.status}`);
        success = true;
      } catch (e) {
        console.warn(`⚠️ Keep-alive пинг не удался (попытка ${attempt}/3): ${e.message}`);
        await new Promise((r) => setTimeout(r, 5000));
      }
    }
    if (!success) console.error("❌ Keep-alive: все попытки пинга провалились в этом цикле");
    await new Promise((r) => setTimeout(r, 150000));
  }
}

function heartbeatLoop() {
  setInterval(() => {
    try {
      const mod = EXTERNAL_URL.startsWith("https") ? https : http;
      const req = mod.get(`${EXTERNAL_URL}/health`, { timeout: 10000 }, (res) => {
        console.log(`💓 Heartbeat пинг: ${res.statusCode}`);
        res.resume();
      });
      req.on("timeout", () => req.destroy());
      req.on("error", (e) => console.warn(`⚠️ Heartbeat пинг не удался: ${e.message}`));
    } catch (e) {
      console.warn(`⚠️ Heartbeat ошибка: ${e.message}`);
    }
  }, 240000);
}

async function startWebhook() {
  const handleUpdate = webhookCallback(bot, "http");
  const server = http.createServer((req, res) => {
    if (req.method === "POST" && req.url === WEBHOOK_PATH) {
      if (req.headers["x-telegram-bot-api-secret-token"] !== WEBHOOK_SECRET) {
        res.writeHead(401, { "Content-Type": "application/json" });
        res.end('{"ok":false}');
        req.destroy();
        return;
      }
      handleUpdate(req, res);
      return;
    }
    if (req.method === "GET" && req.url === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "ok", uptime: process.uptime() }));
      return;
    }
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("OK");
  });

  server.listen(PORT, async () => {
    console.log(`✅ Сервер на порту ${PORT}`);
    try {
      await bot.api.setWebhook(`${EXTERNAL_URL}${WEBHOOK_PATH}`, { secret_token: WEBHOOK_SECRET });
      console.log("✅ Webhook установлен");
    } catch (e) {
      console.error("❌ Webhook error:", e);
    }
    keepAliveLoop();
    heartbeatLoop();
  });
}

async function main() {
  await userbotStart();
  if (USE_WEBHOOK) {
    console.log("🚀 Бот запущен в режиме webhook");
    await startWebhook();
  } else {
    console.log("🚀 Бот запущен в режиме long polling");
    await bot.start();
  }
}

main().catch(async (err) => {
  console.error(err);
  await userbotStop();
  process.exit(1);
});
    
