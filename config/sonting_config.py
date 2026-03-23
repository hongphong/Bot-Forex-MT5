from dataclasses import dataclass
from aiomql import Strategy, ForexSymbol, TimeFrame
from aiomql import Sessions, Session
from datetime import time


@dataclass
class SonTinhConfig:
    # Asset settings
    symbol: str = "XAUUSD"
    timeframe: TimeFrame = TimeFrame.M5
    # Setting up London and NY Sessions (GMT based roughly)
    sessions: tuple[dict] = (
        {"name": 'London', "start": time(
            hour=8), "end": time(hour=12, minute=59)},
        {"name": 'New York', "start": time(
            hour=13), "end": time(hour=17, minute=59)}
    )

    # Filter settings
    max_spread_pips: int = 2 * 0.1  # 2 pips
    max_drawdown_percent: float = 15.0  # Stop bot if equity drops > 15%
    max_concurrent_orders: int = 5
    risk_per_order_percent: float = 1.0
    # ATR Volatility Spike Check (Avoid if current ATR is 20% > Average ATR)
    compare_atr_avg_percent: float = 1.2

    # Indicators Settings
    ema_fast: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    atr_period: int = 14

    # Entry Criteria
    # Price touches/near EMA 50 (±0.1%)
    ema_pullback_buffer_percent: float = 0.1
    rsi_buy_threshold: int = 45  # RSI < 45 for BUY
    rsi_sell_threshold: int = 55  # RSI > 55 for SELL

    # TP/SL rules
    # Initial SL: 30-50 pips. Let's default to conservative 40 pips.
    initial_sl_pips: int = 200

    # TP Target in USD
    tp_target_usd: float = 3.0

    # Partial Close Settings
    partial_tp_trigger_usd: float = 0.5
    partial_tp_percent: float = 0.50  # Close 50% at 0.5 USD profit

    partial_sl_trigger_usd: float = -2.0  # Tỉa lệnh khi âm 0.5-3 USD
    partial_sl_percent: float = 0.30  # Cut 30% of position

    # Trailing Stop
    trailing_sl_trigger_usd: float = 0.5  # Trailing SL sau khi lời 0.5 USD
    trailing_sl_atr_divisor: float = 2.0  # Trailing theo ATR/2

    # Martingale / Lot sizing
    lot_start: float = 0.01
    lot_progression: tuple = (0.01, 0.02, 0.03, 0.05)
    # Increase lot when previous loss > 50 pips
    martingale_loss_trigger_pips: int = 50


config = SonTinhConfig()
