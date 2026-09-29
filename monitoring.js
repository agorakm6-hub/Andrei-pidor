import "dotenv/config";
import http from "http";
import https from "https";
import crypto from "crypto";
import fs from "fs";
import { Bot, session, webhookCallback, InputFile } from "grammy";
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
const POLL_INTERVAL_MS = Number(env("POLL_INTERVAL_MS", false) || "3000");
const MAX_DURATION_MS = Number(env("MAX_DURATION_MS", false) || String(60 * 60 * 1000)); // максимум 1 час

// Граница "быстрой" блокировки для топ-3 в /stats: от 6 сек (короче —
// считаем шумом/ошибкой проверки) и до 10 минут (дольше — не "быстрая").
const FAST_MIN_MS = 6000;
const FAST_MAX_MS = 10 * 60 * 1000;

// Порог, после которого полный список в сообщении не поместится
// (лимит Telegram на текст сообщения — 4096 символов) и вместо списка
// нужно отдавать .txt файл.
const LIST_INLINE_LIMIT = 50;

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
 * Проверяет, свободен ли юзернейм для регистрации ПРЯМО СЕЙЧАС — тот же
 * дозвон, что делают клиенты Telegram, когда ты вводишь новый юзернейм
 * в настройках и видишь галочку/крестик. Ничего не меняет, только читает.
 */
async function isUsernameFree(username) {
  try {
    const free = await tgClient.invoke(new Api.account.CheckUsername({ username }));
    return Boolean(free);
  } catch (e) {
    const msg = String(e?.errorMessage || e?.message || e);
    if (msg.includes("USERNAME_OCCUPIED")) return false;
    throw e;
  }
}

/**
 * Аккаунт помечен как "удалённый" — отличаем самоудаление от бана по
 * судьбе юзернейма: свободен для регистрации → самоудаление; всё ещё
 * занят (хотя владельца уже нет) → Telegram удерживает его за
 * забаненным аккаунтом, это и есть бан. Без юзернейма отличить нечем.
 */
async function classifyDeletedAccount(username) {
  if (!username) return "unknown_deleted";
  try {
    const free = await isUsernameFree(username);
    return free ? "self_deleted" : "banned";
  } catch (e) {
    console.warn(`⚠️ Не удалось проверить занятость @${username}: ${e?.message || e}`);
    return "unknown_deleted";
  }
}

/** Возвращает: "alive" | "banned" | "self_deleted" | "unknown_deleted" | "unknown" */
async function checkByUsername(username) {
  try {
    const result = await tgClient.invoke(new Api.contacts.ResolveUsername({ username }));
    const user = result.users?.[0];
    if (!user) return "unknown";
    if (user.deleted) return await classifyDeletedAccount(username);
    return "alive";
  } catch (e) {
    const msg = String(e?.errorMessage || e?.message || e);
    if (msg.includes("USERNAME_NOT_OCCUPIED")) return "self_deleted";
    if (msg.includes("USERNAME_INVALID")) return "unknown";
    console.warn(`⚠️ Ошибка проверки @${username}: ${msg}`);
    return "unknown";
  }
}

/**
 * Проверка по числовому ID. ОГРАНИЧЕНИЕ: чтобы обратиться к пользователю
 * по ID, MTProto требует access_hash, который есть только если наша
 * сессия уже "видела" этот аккаунт (общий чат, переписка, контакты).
 */
async function checkById(id) {
  try {
    const entity = await tgClient.getEntity(id);
    if (!entity) return "unknown";
    if (entity.deleted) return await classifyDeletedAccount(entity.username);
    return "alive";
  } catch (e) {
    const msg = String(e?.errorMessage || e?.message || e);
    if (msg.includes("Cannot find any entity") || msg.includes("No user has") || msg.includes("PEER_ID_INVALID")) {
      return "unknown";
    }
    console.warn(`⚠️ Ошибка проверки id ${id}: ${msg}`);
    return "unknown";
  }
}

function parseTarget(input) {
  const trimmed = input.trim().replace(/^@/, "");
  if (/^\d+$/.test(trimmed)) return { type: "id", value: Number(trimmed), display: trimmed };
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
    ...(replyMarkup ? { reply_markup: replyMarkup } : { reply_markup: { inline_keyboard: [] } }),
  });
}

/* ---------- ФОРМАТИРОВАНИЕ ВРЕМЕНИ ---------- */

function formatDuration(ms) {
  const totalSec = Math.floor(ms / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min} мин ${sec} сек`;
}

function formatDate(ts) {
  return new Date(ts).toISOString().slice(0, 16).replace("T", " ");
}

/* ---------- СТАТИСТИКА (JSON-файл рядом с ботом) ---------- */

// На бесплатном Render диск стирается при каждом рестарте/деплое — тогда
// статистика обнулится. Для постоянного хранения нужна внешняя БД.
const STATS_FILE = process.env.STATS_FILE || "stats.json";

let stats = { started: 0, selfDeleted: 0, aliveTimeout: 0, stoppedManually: 0, banned: [] };
try {
  const loaded = JSON.parse(fs.readFileSync(STATS_FILE, "utf8"));
  stats = { ...stats, ...loaded, banned: Array.isArray(loaded.banned) ? loaded.banned : [] };
} catch {
  /* файла ещё нет — начинаем с нуля */
}

function saveStats() {
  try {
    fs.writeFileSync(STATS_FILE, JSON.stringify(stats));
  } catch (e) {
    console.warn(`⚠️ Не удалось сохранить статистику: ${e.message}`);
  }
}

function recordOutcome(outcome, elapsedMs, display) {
  if (outcome === "banned") {
    stats.banned.push({ display, elapsedMs, ts: Date.now() });
  } else if (outcome === "self_deleted") {
    stats.selfDeleted++;
  } else if (outcome === "alive") {
    stats.aliveTimeout++;
  } else if (outcome === "stopped") {
    stats.stoppedManually++;
  }
  saveStats();
}

function buildStatsText() {
  const banned = stats.banned;
  const lines = [
    "Статистика мониторинга",
    "",
    `Всего проверено аккаунтов: ${stats.started}`,
    `Заблокировано: ${banned.length}`,
    `Удалили аккаунт сами: ${stats.selfDeleted}`,
    `Дожили до конца часа: ${stats.aliveTimeout}`,
    `Остановлено вручную: ${stats.stoppedManually}`,
    "",
  ];

  if (banned.length === 0) {
    lines.push("Блокировок пока не зафиксировано.");
  } else {
    const avg = banned.reduce((a, b) => a + b.elapsedMs, 0) / banned.length;
    lines.push(`Среднее время до блокировки: ${formatDuration(avg)}`);

    const fastest = banned
      .filter((b) => b.elapsedMs >= FAST_MIN_MS && b.elapsedMs <= FAST_MAX_MS)
      .sort((a, b) => a.elapsedMs - b.elapsedMs)
      .slice(0, 3);

    if (fastest.length > 0) {
      lines.push("");
      lines.push("Самые быстрые блокировки:");
      fastest.forEach((b, i) => {
        lines.push(`${i + 1}. ${b.display} — ${formatDuration(b.elapsedMs)}`);
      });
    }
  }

  if (banned.length > 0) {
    lines.push("");
    lines.push("Полный список заблокированных — по кнопке ниже.");
  }

  return lines.join("\n");
}

function buildListText() {
  const banned = stats.banned;
  if (banned.length === 0) return "Список пока пуст — заблокированных аккаунтов не зафиксировано.";
  const lines = [`Заблокированные аккаунты (всего: ${banned.length})`, ""];
  banned.forEach((b, i) => {
    lines.push(`${i + 1}. ${b.display} — ${formatDuration(b.elapsedMs)}`);
  });
  return lines.join("\n");
}

function buildListFile() {
  const banned = stats.banned;
  const lines = banned.map((b, i) => `${i + 1}. ${b.display} — ${formatDuration(b.elapsedMs)} (${formatDate(b.ts)})`);
  return lines.join("\n");
}

function statsKeyboard() {
  return keyboard([[button("Список", "show_list", "success")]]);
}

function listKeyboard(tooBig) {
  const row = [button("Назад", "show_stats", "primary")];
  if (tooBig) row.push(button("Получить полный список", "get_full_list", "success"));
  return keyboard([row]);
}

/* ---------- BOT ---------- */

const bot = new Bot(BOT_TOKEN);
bot.use(session({ initial: () => ({ waitingUsername: false }) }));

// Открыт для всех (стресс-тест с разных аккаунтов): каждый чат мониторится
// независимо, ключ — chatId. Один чат = один активный мониторинг за раз.
const activeMonitors = new Map();

const WELCOME_TEXT =
  "Добро пожаловать.\n\n" +
  "Пришлите юзернейм или ID пользователя/бота для мониторинга. " +
  "Когда указанный аккаунт будет заблокирован, мы вам сообщим.\n\n" +
  "Общая статистика: /stats";

function monitoringKeyboard() {
  return keyboard([[button("Остановить", "stop_monitor", "danger")]]);
}

bot.command("start", async (ctx) => {
  ctx.session.waitingUsername = true;
  await sendMessage(ctx.chat.id, WELCOME_TEXT);
});

bot.command("stats", async (ctx) => {
  await sendMessage(ctx.chat.id, buildStatsText(), stats.banned.length > 0 ? statsKeyboard() : undefined);
});

bot.callbackQuery("show_list", async (ctx) => {
  const chatId = ctx.chat.id;
  const messageId = ctx.callbackQuery.message.message_id;
  const tooBig = stats.banned.length > LIST_INLINE_LIMIT;
  const text = tooBig
    ? `Заблокированных аккаунтов слишком много (${stats.banned.length}), чтобы поместить в сообщение.\n\nПолучите полный список текстовым файлом по кнопке ниже.`
    : buildListText();
  await editMessageText(chatId, messageId, text, listKeyboard(tooBig));
  await ctx.answerCallbackQuery();
});

bot.callbackQuery("show_stats", async (ctx) => {
  const chatId = ctx.chat.id;
  const messageId = ctx.callbackQuery.message.message_id;
  await editMessageText(chatId, messageId, buildStatsText(), stats.banned.length > 0 ? statsKeyboard() : undefined);
  await ctx.answerCallbackQuery();
});

bot.callbackQuery("get_full_list", async (ctx) => {
  const text = buildListFile();
  await bot.api.sendDocument(ctx.chat.id, new InputFile(Buffer.from(text, "utf8"), "banned_accounts.txt"));
  await ctx.answerCallbackQuery();
});

function stopMonitor(chatId) {
  const m = activeMonitors.get(chatId);
  if (m) {
    clearInterval(m.timer);
    clearTimeout(m.timeout);
    activeMonitors.delete(chatId);
  }
}

// Завершает мониторинг ровно один раз: если проверка ещё "в полёте", когда
// сработал таймаут или кнопка, второй вызов вернёт null и ничего не задвоит.
function finishMonitor(chatId, outcome) {
  const m = activeMonitors.get(chatId);
  if (!m) return null;
  const elapsed = Date.now() - m.startedAt;
  stopMonitor(chatId);
  recordOutcome(outcome, elapsed, m.display);
  return { m, elapsed };
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

    if (status === "banned") {
      const done = finishMonitor(chatId, "banned");
      if (!done) return;
      await editMessageText(
        chatId,
        messageId,
        `Мониторинг завершён\n\nПользователь ${target.display} был заблокирован за ${formatDuration(done.elapsed)}.`
      );
      return;
    }

    if (status === "self_deleted") {
      const done = finishMonitor(chatId, "self_deleted");
      if (!done) return;
      await editMessageText(
        chatId,
        messageId,
        `Мониторинг завершён\n\nПользователь ${target.display} удалил свой аккаунт до блокировки.`
      );
      return;
    }

    if (status === "unknown_deleted") {
      const done = finishMonitor(chatId, "self_deleted");
      if (!done) return;
      await editMessageText(
        chatId,
        messageId,
        `Мониторинг завершён\n\nАккаунт ${target.display} пропал (помечен как удалённый), но у него нет юзернейма — отличить самоудаление от блокировки не получилось.`
      );
      return;
    }

    // "alive" или "unknown" — просто ждём следующей проверки
  }, POLL_INTERVAL_MS);

  const timeout = setTimeout(async () => {
    const done = finishMonitor(chatId, "alive");
    if (!done) return;
    await editMessageText(chatId, messageId, `Мониторинг завершён\n\nИзменений нет. Аккаунт ${target.display} цел.`);
  }, MAX_DURATION_MS);

  activeMonitors.set(chatId, { display: target.display, messageId, startedAt, timer, timeout });
  stats.started++;
  saveStats();
});

bot.callbackQuery("stop_monitor", async (ctx) => {
  const chatId = ctx.chat.id;
  const done = finishMonitor(chatId, "stopped");
  if (!done) {
    await ctx.answerCallbackQuery({ text: "Мониторинг уже не идёт" });
    return;
  }
  await editMessageText(
    chatId,
    done.m.messageId,
    `Мониторинг остановлен вручную\n\n${done.m.display}, длительность: ${formatDuration(done.elapsed)}.`
  );
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

async function setupCommandMenu() {
  try {
    await bot.api.setMyCommands([
      { command: "start", description: "Начать мониторинг аккаунта" },
      { command: "stats", description: "Общая статистика бота" },
    ]);
  } catch (e) {
    console.warn(`⚠️ Не удалось задать меню команд: ${e.message}`);
  }
}

async function main() {
  await userbotStart();
  await setupCommandMenu();
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
