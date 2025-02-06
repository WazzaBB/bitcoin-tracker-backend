import os
import requests
import pandas as pd
import numpy as np
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from binance.client import Client
import logging

# Load environment variables
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Ensure Binance credentials exist
if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
    raise ValueError("Missing Binance API credentials. Set BINANCE_API_KEY and BINANCE_SECRET_KEY.")

client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
app = FastAPI()

# Logger setup
logging.basicConfig(level=logging.INFO)

@app.get("/")
def home():
    return {"message": "Bitcoin Tracker API is running with aggressive strategy!"}

# Fetch historical data
def get_historical_data(symbol="BTCUSDT", interval="1h", limit=100):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Binance API error: {e}")
    
    df = pd.DataFrame(klines, columns=[
        "timestamp", "open", "high", "low", "close", "volume", "close_time", 
        "qav", "num_trades", "taker_base", "taker_quote", "ignore"
    ])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df

# Compute RSI
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Compute MACD
def compute_macd(series, short_period=12, long_period=26, signal_period=9):
    short_ema = series.ewm(span=short_period, adjust=False).mean()
    long_ema = series.ewm(span=long_period, adjust=False).mean()
    macd = short_ema - long_ema
    signal = macd.ewm(span=signal_period, adjust=False).mean()
    return macd, signal

# Compute Bollinger Bands
def compute_bollinger_bands(series, period=20, std_dev=2):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper_band = sma + (std_dev * std)
    lower_band = sma - (std_dev * std)
    return upper_band, lower_band

# Compute Stochastic RSI
def compute_stoch_rsi(series, period=14):
    min_val = series.rolling(window=period).min()
    max_val = series.rolling(window=period).max()
    stoch_rsi = 100 * ((series - min_val) / (max_val - min_val))
    return stoch_rsi

# Compute Exponential Moving Averages
def compute_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

# Apply indicators
def calculate_indicators(df):
    df["SMA_10"] = df["close"].rolling(window=10).mean()
    df["SMA_50"] = df["close"].rolling(window=50).mean()
    df["RSI"] = compute_rsi(df["close"], 14)
    df["MACD"], df["Signal"] = compute_macd(df["close"])
    df["BB_Upper"], df["BB_Lower"] = compute_bollinger_bands(df["close"])
    df["Stoch_RSI"] = compute_stoch_rsi(df["close"])
    df["EMA_5"] = compute_ema(df["close"], 5)
    df["EMA_20"] = compute_ema(df["close"], 20)
    return df

# Generate buy/sell signals
def get_signals(df):
    latest = df.iloc[-1]
    signals = []
    
    if latest["SMA_10"] > latest["SMA_50"]:
        signals.append("BUY: SMA Crossover")
    if latest["RSI"] < 40:
        signals.append("BUY: RSI Oversold")
    if latest["MACD"] > latest["Signal"]:
        signals.append("BUY: MACD Trend")
    if latest["close"] < latest["BB_Lower"]:
        signals.append("BUY: Bollinger Band")
    if latest["EMA_5"] > latest["EMA_20"]:
        signals.append("BUY: EMA Crossover")
    
    if latest["SMA_10"] < latest["SMA_50"]:
        signals.append("SELL: SMA Crossover")
    if latest["RSI"] > 60:
        signals.append("SELL: RSI Overbought")
    if latest["MACD"] < latest["Signal"]:
        signals.append("SELL: MACD Trend")
    if latest["close"] > latest["BB_Upper"]:
        signals.append("SELL: Bollinger Band")
    if latest["EMA_5"] < latest["EMA_20"]:
        signals.append("SELL: EMA Crossover")
    
    return signals

# Send Telegram alert
def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram credentials are missing. Cannot send alerts.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, data=data)

# Bitcoin price tracking API
@app.get("/bitcoin")
def track_price(background_tasks: BackgroundTasks):
    df = get_historical_data()
    df = calculate_indicators(df)
    signals = get_signals(df)
    price = df.iloc[-1]["close"]
    
    if signals:
        message = f"Bitcoin Price: ${price:.2f}\nSignals: {', '.join(signals)}"
        background_tasks.add_task(send_telegram_alert, message)
    
    return JSONResponse(content={"price": price, "signals": signals})