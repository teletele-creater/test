"""
市場データ取得モジュール

yfinanceを使用してVIX、SPY、IV関連データ、テクニカル指標を取得・計算する。
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

from config import (
    IV_LOOKBACK_DAYS,
    MA_LONG,
    MA_PROXIMITY_PCT,
    MA_SHORT,
    PUT_CALL_RATIO_SMA_PERIOD,
    RSI_PERIOD,
    VIX_DECLINE_LOOKBACK,
)

logger = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    """市場データのスナップショット"""
    timestamp: datetime
    symbol: str
    price: float
    vix: float
    iv_current: float  # 現在のインプライドボラティリティ（近似値）
    iv_rank: float  # IV Rank (0-100)
    iv_percentile: float  # IV Percentile (0-100)
    hv_20: float  # 20日ヒストリカルボラティリティ
    iv_hv_ratio: float  # IV/HV比率
    rsi: float  # RSI(14)
    ma_50: float  # 50日移動平均
    ma_200: float  # 200日移動平均
    near_50ma: bool  # 50MA付近か
    near_200ma: bool  # 200MA付近か
    put_call_ratio_sma: float | None  # P/C Ratio 10日SMA
    vix_declining: bool  # VIXが直近で低下傾向か
    nikkei_vi: float | None  # 日経VI（日本市場用）


def fetch_vix() -> pd.Series:
    """VIX（CBOE Volatility Index）の過去データを取得"""
    vix = yf.Ticker("^VIX")
    hist = vix.history(period="1y")
    return hist["Close"]


def fetch_price_history(symbol: str, period: str = "1y") -> pd.DataFrame:
    """銘柄の価格履歴を取得"""
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period)
    if hist.empty:
        raise ValueError(f"No data returned for {symbol}")
    return hist


def calculate_rsi(prices: pd.Series, period: int = RSI_PERIOD) -> float:
    """RSI（相対力指数）を計算"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def calculate_historical_volatility(prices: pd.Series, window: int = 20) -> float:
    """ヒストリカルボラティリティを計算（年率換算）"""
    log_returns = np.log(prices / prices.shift(1)).dropna()
    hv = float(log_returns.rolling(window=window).std().iloc[-1]) * np.sqrt(252) * 100
    return hv


def estimate_iv_from_vix(vix_value: float, symbol: str) -> float:
    """
    VIXベースのIV近似値を取得。
    個別銘柄の場合はベータ調整を行う。
    ETF（SPY等）の場合はVIX≒IVとして使用。
    """
    # SPY/IWM/QQQなどの主要ETFはVIXと高い相関
    etf_multipliers = {
        "SPY": 1.0,
        "IWM": 1.15,  # 小型株はやや高いIV
        "QQQ": 1.05,  # テック株はやや高いIV
    }
    multiplier = etf_multipliers.get(symbol, 1.2)  # 個別株はデフォルト1.2倍
    return vix_value * multiplier


def calculate_iv_rank(iv_series: pd.Series) -> float:
    """
    IV Rank を計算
    IVR = (現在IV - 52週最低IV) / (52週最高IV - 52週最低IV) × 100
    """
    if len(iv_series) < 20:
        return 50.0  # データ不足時はニュートラル

    iv_current = float(iv_series.iloc[-1])
    iv_high = float(iv_series.max())
    iv_low = float(iv_series.min())

    if iv_high == iv_low:
        return 50.0

    ivr = (iv_current - iv_low) / (iv_high - iv_low) * 100
    return round(ivr, 1)


def calculate_iv_percentile(iv_series: pd.Series) -> float:
    """
    IV Percentile を計算
    過去1年間のうち現在のIVより低かった日の割合
    """
    if len(iv_series) < 20:
        return 50.0

    iv_current = float(iv_series.iloc[-1])
    below_count = (iv_series < iv_current).sum()
    ivp = below_count / len(iv_series) * 100
    return round(float(ivp), 1)


def is_vix_declining(vix_series: pd.Series, lookback: int = VIX_DECLINE_LOOKBACK) -> bool:
    """VIXが直近で低下傾向にあるか判定（スパイク後の沈静化）"""
    if len(vix_series) < lookback + 1:
        return False
    recent = vix_series.iloc[-lookback:]
    # 直近のVIXが期間内の最高値より低く、かつ下降トレンド
    peak = recent.max()
    current = float(recent.iloc[-1])
    return current < peak * 0.95  # ピークから5%以上低下


def fetch_put_call_ratio_sma() -> float | None:
    """
    CBOE Put/Call Ratioの10日SMAを取得。
    yfinanceではP/C Ratioの直接取得が困難なため、
    VIX関連の代替指標を使用する。
    """
    try:
        # CBOE Equity Put/Call Ratio
        # yfinanceでは直接取得できないため、VIXの水準から推定
        # VIX > 25 の場合、P/C Ratio > 1.0 と概算
        vix_hist = fetch_vix()
        current_vix = float(vix_hist.iloc[-1])
        # 簡易推定：VIXが高い時はP/C Ratioも高い
        estimated_pcr = 0.6 + (current_vix - 15) * 0.04
        return round(max(0.5, min(2.0, estimated_pcr)), 2)
    except Exception as e:
        logger.warning(f"P/C Ratio estimation failed: {e}")
        return None


def get_market_snapshot(symbol: str) -> MarketSnapshot:
    """指定銘柄の市場データスナップショットを生成"""
    logger.info(f"Fetching market data for {symbol}...")

    # 価格データ取得
    hist = fetch_price_history(symbol, period="1y")
    prices = hist["Close"]
    current_price = float(prices.iloc[-1])

    # VIXデータ
    vix_series = fetch_vix()
    current_vix = float(vix_series.iloc[-1])

    # IV推定（VIXベース）
    iv_current = estimate_iv_from_vix(current_vix, symbol)

    # VIXの履歴をIVの代替として使用しIV Rank/Percentileを計算
    iv_rank = calculate_iv_rank(vix_series)
    iv_percentile = calculate_iv_percentile(vix_series)

    # ヒストリカルボラティリティ
    hv_20 = calculate_historical_volatility(prices, window=20)

    # IV/HV比率
    iv_hv_ratio = iv_current / hv_20 if hv_20 > 0 else 1.0

    # RSI
    rsi = calculate_rsi(prices)

    # 移動平均
    ma_50 = float(prices.rolling(window=MA_SHORT).mean().iloc[-1])
    ma_200 = float(prices.rolling(window=MA_LONG).mean().iloc[-1]) if len(prices) >= MA_LONG else ma_50

    # MA付近の判定
    near_50 = abs(current_price - ma_50) / ma_50 * 100 < MA_PROXIMITY_PCT
    near_200 = abs(current_price - ma_200) / ma_200 * 100 < MA_PROXIMITY_PCT

    # P/C Ratio
    pcr_sma = fetch_put_call_ratio_sma()

    # VIX低下判定
    vix_declining_flag = is_vix_declining(vix_series)

    # 日経VI（日本市場用）
    nikkei_vi = None
    if symbol == "^N225":
        nikkei_vi = current_vix * 1.3  # 概算

    snapshot = MarketSnapshot(
        timestamp=datetime.now(),
        symbol=symbol,
        price=current_price,
        vix=current_vix,
        iv_current=iv_current,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        hv_20=hv_20,
        iv_hv_ratio=round(iv_hv_ratio, 2),
        rsi=round(rsi, 1),
        ma_50=round(ma_50, 2),
        ma_200=round(ma_200, 2),
        near_50ma=near_50,
        near_200ma=near_200,
        put_call_ratio_sma=pcr_sma,
        vix_declining=vix_declining_flag,
        nikkei_vi=nikkei_vi,
    )

    logger.info(f"Snapshot for {symbol}: VIX={current_vix:.1f}, IVR={iv_rank:.1f}%, "
                f"RSI={rsi:.1f}, IV/HV={iv_hv_ratio:.2f}")

    return snapshot
