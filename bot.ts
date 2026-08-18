import "dotenv/config";
import { Bot, session, type Context, type SessionFlavor } from "grammy";
import { TelegramClient, Api } from "telegram";
import { StringSession } from "telegram/sessions/index.js";

/* ---------- CONFIG ---------- */

function env(name: string, required = true): string {
  const val = process.env[name] ?? "";
  if (required && !val) throw new Error(`Переменная окружения ${name} не задана`);
  return val;
}

const BOT_TOKEN = env("BOT_TOKEN");
const API_ID = Number(env("API_ID"));
const API_HASH = env("API_HASH");
const SESSION_STRING = env("SESSION_STRING");
const EMOJI_STAR = env("EMOJI_STAR", false) || "⭐";
const EMOJI_SCAN = env("EMOJI_SCAN", false) || "🔍";
const EMOJI_BACK = env("EMOJI_BACK", false) || "◀️";
const EMOJI_TON = env("EMOJI_TON", false) || "💎";
const EMOJI_OK = env("EMOJI_OK", false) || "✨";
const TON_TO_STARS = 250; // примерный курс, актуализируй перед запуском

/* ---------- RAW BOT API (цветные кнопки) ---------- */

const API_ROOT = `https://api.telegram.org/bot${BOT_TOKEN}`;

interface RawButton {
  text: string;
  callback_data: string;
  style?: "primary" | "success" | "danger";
}

function button(text: string, callback_data: string, style?: RawButton["style"]): RawButton {
  return style ? { text, callback_data, style } : { text, callback_data };
}

function keyboard(rows: RawButton[][]) {
  return { inline_keyboard: rows };
}

async function apiPost(method: string, payload: Record<string, unknown>) {
  const res = await fetch(`${API_ROOT}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!data.ok) throw new Error(`Telegram API error on ${method}: ${JSON.stringify(data)}`);
  return data.result;
}

async function sendMessage(chatId: number, text: string, replyMarkup?: ReturnType<typeof keyboard>) {
  return apiPost("sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    ...(replyMarkup ? { reply_markup: replyMarkup } : {}),
  });
}

async function editMessageText(
  chatId: number,
  messageId: number,
  text: string,
  replyMarkup?: ReturnType<typeof keyboard>
) {
  return apiPost("editMessageText", {
    chat_id: chatId,
    message_id: messageId,
    text,
    parse_mode: "HTML",
    ...(replyMarkup ? { reply_markup: replyMarkup } : {}),
  });
}

/* ---------- USERBOT (MTProto, атрибуты подарка) ---------- */

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

interface GiftAttributes {
  slug: string;
  title: string;
  modelName: string;
  modelRarityPermille: number | null;
  backdropName: string;
  backdropRarityPermille: number | null;
  patternName: string;
  patternRarityPermille: number | null;
  number: number | null;
}

const LINK_RE = /(?:https?:\/\/)?t\.me\/nft\/([A-Za-z0-9_-]+)/;

function parseSlug(linkOrSlug: string): string {
  const trimmed = linkOrSlug.trim();
  const m = trimmed.match(LINK_RE);
  if (m) return m[1];
  if (/^[A-Za-z0-9_-]+$/.test(trimmed)) return trimmed;
  throw new Error("Не похоже на ссылку/slug NFT-подарка");
}

async function getGiftAttributes(linkOrSlug: string): Promise<GiftAttributes> {
  const slug = parseSlug(linkOrSlug);
  await userbotStart();

  // ЗАГЛУШКА под реальный MTProto-вызов — сверь точное имя метода
  // в твоей версии GramJS (node_modules/telegram/tl/api.d.ts, ищи "Gift").
  const result: any = await tgClient.invoke(new (Api as any).payments.GetUniqueStarGift({ slug }));
  const gift = result.gift;

  let model: any, backdrop: any, pattern: any;
  for (const attr of gift.attributes ?? []) {
    const cname = attr.className as string;
    if (cname.includes("Model")) model = attr;
    else if (cname.includes("Backdrop")) backdrop = attr;
    else if (cname.includes("Pattern") || cname.includes("Symbol")) pattern = attr;
  }
  const rarity = (a: any) => (a?.rarityPermille ?? null) as number | null;

  return {
    slug,
    title: gift.title ?? slug,
    modelName: model?.name ?? "неизвестно",
    modelRarityPermille: rarity(model),
    backdropName: backdrop?.name ?? "неизвестно",
    backdropRarityPermille: rarity(backdrop),
    patternName: pattern?.name ?? "неизвестно",
    patternRarityPermille: rarity(pattern),
    number: gift.num ?? null,
  };
}

/* ---------- PRICING ---------- */

interface AttributeFloor {
  tonFloor: number | null;
}

// Заглушка: нет подтверждённых актуальных эндпоинтов Portals/Tonnel/getgems,
// поэтому не выдумываю их. Подставь реальные HTTP-запросы сюда.
async function modelFloor(_collection: string, _modelName: string): Promise<AttributeFloor> {
  return { tonFloor: null };
}
async function backdropFloor(_collection: string, _backdropName: string): Promise<AttributeFloor> {
  return { tonFloor: null };
}

interface PriceEstimate {
  tonPrice: number | null;
  starsPrice: number | null;
  confidence: "low" | "medium" | "high";
  breakdown: Record<string, string>;
}

function rarityMultiplier(permille: number | null): number {
  if (!permille) return 1.0;
  if (permille <= 5) return 2.5;
  if (permille <= 20) return 1.8;
  if (permille <= 50) return 1.4;
  if (permille <= 100) return 1.15;
  return 1.0;
}

async function estimatePrice(gift: GiftAttributes, collection: string, monochrome: boolean): Promise<PriceEstimate> {
  const mf = await modelFloor(collection, gift.modelName);
  const bf = await backdropFloor(collection, gift.backdropName);

  const candidates: number[] = [];
  const breakdown: Record<string, string> = {};

  if (bf.tonFloor) {
    candidates.push(bf.tonFloor);
    breakdown["фон"] = `${bf.tonFloor.toFixed(2)} TON`;
  } else {
    breakdown["фон"] = "нет данных по этому фону — не влияет на цену";
  }

  if (mf.tonFloor) {
    const m = mf.tonFloor * rarityMultiplier(gift.modelRarityPermille);
    candidates.push(m);
    breakdown["модель"] = `${m.toFixed(2)} TON (floor ${mf.tonFloor.toFixed(2)} × редкость)`;
  } else {
    breakdown["модель"] = "нет данных по этой модели";
  }

  if (candidates.length === 0) {
    return { tonPrice: null, starsPrice: null, confidence: "low", breakdown: { ...breakdown, итог: "недостаточно рыночных данных" } };
  }

  let base = candidates.reduce((a, b) => a + b, 0) / candidates.length;
  if (monochrome) {
    base *= 1.15;
    breakdown["монохром"] = "+15% (фон в цвет подарка)";
  }

  return {
    tonPrice: Math.round(base * 100) / 100,
    starsPrice: Math.round(base * TON_TO_STARS),
    confidence: candidates.length === 2 ? "high" : "medium",
    breakdown,
  };
}

/* ---------- ANIMATION ---------- */

class ScanAnimation {
  private stopped = false;
  private loop: Promise<void> | null = null;
  constructor(private chatId: number, private messageId: number, private intervalMs = 600) {}

  start() {
    this.loop = this.run();
  }
  private async run() {
    const frames = [`Сканирую NFT ${EMOJI_SCAN}`, `Сканирую NFT ${EMOJI_SCAN}.`, `Сканирую NFT ${EMOJI_SCAN}..`, `Сканирую NFT ${EMOJI_SCAN}...`];
    let i = 0;
    while (!this.stopped) {
      try {
        await editMessageText(this.chatId, this.messageId, frames[i % frames.length]);
      } catch {
        /* дубль текста — не критично */
      }
      i++;
      await new Promise((r) => setTimeout(r, this.intervalMs));
    }
  }
  async stop() {
    this.stopped = true;
    if (this.loop) await this.loop;
  }
}

/* ---------- BOT ---------- */

interface SessionData {
  waitingLink: boolean;
  promptMessageId?: number;
}
type MyContext = Context & SessionFlavor<SessionData>;

const bot = new Bot<MyContext>(BOT_TOKEN);
bot.use(session({ initial: (): SessionData => ({ waitingLink: false }) }));

const WELCOME_TEXT = `Привет ${EMOJI_OK}\n\nПришли ссылку на свой NFT-подарок — я гляну фон, узор и модель и посчитаю честную рыночную цену.`;
const START_KB = keyboard([[button("Оценить свой NFT", "appraise", "success")]]);
const ASK_LINK_TEXT = "Скинь ссылку на NFT-подарок (t.me/nft/...)";
const BACK_KB = keyboard([[button(`${EMOJI_BACK} Назад`, "appraise", "primary")]]);

function pct(permille: number | null): string {
  return permille ? `${(permille / 10).toFixed(1)}%` : "редкость неизвестна";
}

bot.command("start", async (ctx) => {
  if (!ctx.chat) return;
  await sendMessage(ctx.chat.id, WELCOME_TEXT, START_KB);
});

bot.callbackQuery("appraise", async (ctx) => {
  if (!ctx.chat || !ctx.callbackQuery.message) return;
  ctx.session.waitingLink = true;
  ctx.session.promptMessageId = ctx.callbackQuery.message.message_id;
  await editMessageText(ctx.chat.id, ctx.callbackQuery.message.message_id, ASK_LINK_TEXT);
  await ctx.answerCallbackQuery();
});

bot.on("message:text", async (ctx) => {
  if (!ctx.session.waitingLink || !ctx.session.promptMessageId) return;
  const chatId = ctx.chat.id;
  const targetMessageId = ctx.session.promptMessageId;
  ctx.session.waitingLink = false;

  try {
    await ctx.api.deleteMessage(chatId, ctx.message.message_id);
  } catch {
    /* нет прав удалить — не критично */
  }

  const anim = new ScanAnimation(chatId, targetMessageId);
  anim.start();

  try {
    const gift = await getGiftAttributes(ctx.message.text);
    const collection = gift.title.includes("-") ? gift.title.split("-")[0] : gift.title;
    const monochrome = gift.backdropName.toLowerCase() === gift.title.toLowerCase();
    const estimate = await estimatePrice(gift, collection, monochrome);
    await anim.stop();

    const lines = [
      `<b>${gift.title}</b> #${gift.number ?? "?"}`,
      "",
      `Модель: ${gift.modelName} (${pct(gift.modelRarityPermille)})`,
      `Фон: ${gift.backdropName} (${pct(gift.backdropRarityPermille)})`,
      `Узор: ${gift.patternName} (${pct(gift.patternRarityPermille)})`,
      "",
    ];

    if (estimate.tonPrice) {
      lines.push(`Цена: ~${estimate.tonPrice} TON ${EMOJI_TON}`);
      lines.push(`В звёздах: ~${estimate.starsPrice} ${EMOJI_STAR}`);
      lines.push(`Уверенность оценки: ${estimate.confidence}`);
    } else {
      lines.push("Рыночных данных по этим атрибутам пока нет — точную цену не посчитать.");
    }

    lines.push("");
    for (const [k, v] of Object.entries(estimate.breakdown)) lines.push(`· ${k}: ${v}`);

    await editMessageText(chatId, targetMessageId, lines.join("\n"), BACK_KB);
  } catch (err) {
    await anim.stop();
    await editMessageText(chatId, targetMessageId, `Не получилось разобрать эту ссылку ${EMOJI_SCAN}\n${String(err)}`, BACK_KB);
  }
});

async function main() {
  await userbotStart();
  await bot.start();
}

main().catch(async (err) => {
  console.error(err);
  await userbotStop();
  process.exit(1);
});
