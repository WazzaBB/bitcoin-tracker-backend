import os
import requests
import pandas as pd
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
from binance.client import Client

# Load environment variables
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
app = FastAPI()

# Fetch historical data
def get_historical_data(symbol="BTCUSDT", interval="1h", limit=100):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=["timestamp", "open", "high", "low", "close", "volume", "close_time", "qav", "num_trades", "taker_base", "taker_quote", "ignore"])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df["close"] = df["close"].astype(float)
    return df

# Apply technical indicators manually
def calculate_indicators(df):
    df["SMA_10"] = df["close"].rolling(window=10).mean()
    df["SMA_50"] = df["close"].rolling(window=50).mean()
    df["RSI"] = compute_rsi(df["close"], 14)
    df["MACD"], df["Signal"] = compute_macd(df["close"])
    return df

# Compute RSI manually
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Compute MACD manually
def compute_macd(series, short_period=12, long_period=26, signal_period=9):
    short_ema = series.ewm(span=short_period, adjust=False).mean()
    long_ema = series.ewm(span=long_period, adjust=False).mean()
    macd = short_ema - long_ema
    signal = macd.ewm(span=signal_period, adjust=False).mean()
    return macd, signal

# Generate buy/sell signals
def get_signals(df):
    latest = df.iloc[-1]
    signals = []
    if latest["SMA_10"] > latest["SMA_50"]:
        signals.append("BUY: SMA Crossover")
    if latest["RSI"] < 30:
        signals.append("BUY: RSI Oversold")
    if latest["MACD"] > latest["Signal"]:
        signals.append("BUY: MACD Trend")
    if latest["SMA_10"] < latest["SMA_50"]:
        signals.append("SELL: SMA Crossover")
    if latest["RSI"] > 70:
        signals.append("SELL: RSI Overbought")
    if latest["MACD"] < latest["Signal"]:
        signals.append("SELL: MACD Trend")
    return signals

# Send Telegram alert
def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, data=data)

# API endpoint to fetch Bitcoin price and indicators
@app.get("/track")
def track_price(background_tasks: BackgroundTasks):
    df = get_historical_data()
    df = calculate_indicators(df)
    signals = get_signals(df)
    price = df.iloc[-1]["close"]
    
    if signals:
        message = f"Bitcoin Price: ${price:.2f}\nSignals: {', '.join(signals)}"
        background_tasks.add_task(send_telegram_alert, message)
    
    return JSONResponse(content={"price": price, "signals": signals})

# Run the server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
