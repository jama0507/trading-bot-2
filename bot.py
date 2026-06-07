import os
import threading
import aiohttp
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8696263544:AAEwk9AMUNI_GPh5_uhH3V18buzRSsmnrHY")

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, *args):
        pass

def run_server():
    port = int(os.getenv("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

async def get_btc_data():
    async with aiohttp.ClientSession() as s:
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=30&interval=daily"
        async with s.get(url) as r:
            data = await r.json()
    prices = [p[1] for p in data["prices"]]
    return prices

async def get_gold_data():
    try:
        async with aiohttp.ClientSession() as s:
            url = "https://data-asg.goldprice.org/dbXRates/USD"
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                return float(data["items"][0]["xauPrice"])
    except Exception:
        return None

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_macd(prices):
    def ema(data, span):
        k = 2 / (span + 1)
        result = [data[0]]
        for p in data[1:]:
            result.append(p * k + result[-1] * (1 - k))
        return result
    if len(prices) < 26:
        return None, None
    ema12 = ema(prices, 12)
    ema26 = ema(prices, 26)
    macd_line = [a - b for a, b in zip(ema12, ema26)]
    signal = ema(macd_line, 9)
    return round(macd_line[-1], 2), round(signal[-1], 2)

def calculate_sma(prices, period):
    if len(prices) < period:
        return None
    return round(sum(prices[-period:]) / period, 2)

def generate_signal(rsi, macd, macd_signal, sma20, sma50):
    signals = []
    score = 0
    if rsi:
        if rsi < 30:
            signals.append("🟢 RSI oversold (buy zone)")
            score += 2
        elif rsi > 70:
            signals.append("🔴 RSI overbought (sell zone)")
            score -= 2
        else:
            signals.append("🟡 RSI neutral")
    if macd and macd_signal:
        if macd > macd_signal:
            signals.append("🟢 MACD bullish")
            score += 1
        else:
            signals.append("🔴 MACD bearish")
            score -= 1
    if sma20 and sma50:
        if sma20 > sma50:
            signals.append("🟢 SMA20 > SMA50 (uptrend)")
            score += 1
        else:
            signals.append("🔴 SMA20 < SMA50 (downtrend)")
            score -= 1
    if score >= 2:
        verdict = "✅ SIGNAL: BUY"
    elif score <= -2:
        verdict = "🚨 SIGNAL: SELL"
    else:
        verdict = "⏳ SIGNAL: HOLD"
    return verdict, signals

def fmt(n, d=2):
    return f"{n:,.{d}f}" if n else "N/A"

def rsi_bar(rsi):
    if not rsi:
        return "░░░░░░░░░░"
    filled = int(rsi / 10)
    return "[" + "█" * filled + "░" * (10 - filled) + f"] {rsi}"

def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("₿ BTC Analysis", callback_data="btc"),
         InlineKeyboardButton("🥇 Gold Analysis", callback_data="gold")],
        [InlineKeyboardButton("📊 Both Markets", callback_data="both")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ])

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Trading Analysis Bot*\n\nАнализирую BTC и Gold в реальном времени.\nВыбери актив:",
        parse_mode="Markdown",
        reply_markup=main_menu_kb()
    )

async def btc_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("⏳ Загружаю данные BTC...")
    try:
        prices = await get_btc_data()
        price = prices[-1]
        rsi = calculate_rsi(prices)
        macd, macd_sig = calculate_macd(prices)
        sma20 = calculate_sma(prices, 20)
        sma50 = calculate_sma(prices, 50) if len(prices) >= 50 else None
        chg1d = round(((prices[-1] - prices[-2]) / prices[-2]) * 100, 2)
        chg7d = round(((prices[-1] - prices[-8]) / prices[-8]) * 100, 2)
        verdict, signals = generate_signal(rsi, macd, macd_sig, sma20, sma50)
        trend = "📈" if chg1d > 0 else "📉"
        text = (
            f"₿ *Bitcoin (BTC/USD)*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Price: `${fmt(price)}`\n"
            f"{trend} 24h: `{chg1d:+.2f}%`\n"
            f"📅 7d:  `{chg7d:+.2f}%`\n\n"
            f"📊 *Indicators*\n"
            f"RSI(14): {rsi_bar(rsi)}\n"
            f"MACD: `{fmt(macd)}`  Signal: `{fmt(macd_sig)}`\n"
            f"SMA20: `${fmt(sma20)}`\n"
            f"SMA50: `${fmt(sma50)}`\n\n"
            f"🔍 *Signals*\n" + "\n".join(signals) + f"\n\n*{verdict}*\n\n"
            f"_Updated: {datetime.now().strftime('%H:%M:%S')}_"
        )
    except Exception as e:
        text = f"❌ Ошибка BTC:\n`{e}`"
    await q.edit_message_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Refresh", callback_data="btc"),
            InlineKeyboardButton("⬅️ Menu", callback_data="menu")
        ]]))

async def gold_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("⏳ Загружаю данные Gold...")
    price = await get_gold_data()
    if price:
        text = (
            f"🥇 *Gold (XAU/USD)*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Price: `${fmt(price)}/oz`\n\n"
            f"📌 *Key Levels*\n"
            f"Support:    `${fmt(price * 0.98)}`\n"
            f"Resistance: `${fmt(price * 1.02)}`\n\n"
            f"_Updated: {datetime.now().strftime('%H:%M:%S')}_"
        )
    else:
        text = "❌ Не удалось загрузить цену Gold."
    await q.edit_message_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Refresh", callback_data="gold"),
            InlineKeyboardButton("⬅️ Menu", callback_data="menu")
        ]]))

async def both_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("⏳ Загружаю оба рынка...")
    try:
        prices = await get_btc_data()
        btc_price = prices[-1]
        btc_chg = round(((prices[-1] - prices[-2]) / prices[-2]) * 100, 2)
        rsi = calculate_rsi(prices)
        macd, macd_sig = calculate_macd(prices)
        sma20 = calculate_sma(prices, 20)
        sma50 = calculate_sma(prices, 50) if len(prices) >= 50 else None
        verdict, _ = generate_signal(rsi, macd, macd_sig, sma20, sma50)
        trend = "📈" if btc_chg > 0 else "📉"
    except Exception:
        btc_price, btc_chg, rsi, verdict, trend = None, 0, None, "N/A", "❓"
    gold_price = await get_gold_data()
    text = (
        f"📊 *Markets Overview*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"₿ *BTC/USD*\n"
        f"Price: `${fmt(btc_price)}`  {trend} `{btc_chg:+.2f}%`\n"
        f"RSI: `{rsi}`\n{verdict}\n\n"
        f"🥇 *XAU/USD (Gold)*\n"
        f"Price: `${fmt(gold_price)}/oz`\n\n"
        f"_Updated: {datetime.now().strftime('%H:%M:%S')}_"
    )
    await q.edit_message_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Refresh", callback_data="both"),
            InlineKeyboardButton("⬅️ Menu", callback_data="menu")
        ]]))

async def help_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    text = (
        "ℹ️ *Как работает бот*\n\n"
        "• BTC: CoinGecko API\n"
        "• Gold: GoldPrice API\n"
        "• RSI, MACD, SMA20/50\n\n"
        "⚠️ _Не финансовый совет!_"
    )
    await q.edit_message_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data="menu")]]))

async def menu_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "👋 *Trading Analysis Bot*\n\nВыбери актив:",
        parse_mode="Markdown",
        reply_markup=main_menu_kb()
    )

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    print("🤖 Bot started!")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(btc_handler, pattern="^btc$"))
    app.add_handler(CallbackQueryHandler(gold_handler, pattern="^gold$"))
    app.add_handler(CallbackQueryHandler(both_handler, pattern="^both$"))
    app.add_handler(CallbackQueryHandler(help_handler, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu$"))
    app.run_polling(drop_pending_updates=True)
