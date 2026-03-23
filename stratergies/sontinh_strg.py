from aiomql import Strategy, ForexSymbol, TimeFrame, OrderType, Tracker, Sessions, Session
from traders.sontinh_trader import SonTinhTrader
from utils.logger import logger
from config.sonting_config import config
from datetime import datetime, time


class SonTinhStrategy(Strategy):
    """
    SonTinh Strategy for XAUUSD M5
    - EMA 50 & 200 for Trend
    - Pullback to EMA 50 with RSI oversold/overbought check
    - ATR filter and Spread filter
    - Trades only during London and NY sessions
    """
    ema_fast: int = config.ema_fast
    ema_slow: int = config.ema_slow
    rsi_period: int = config.rsi_period
    atr_period: int = config.atr_period
    time_frame: TimeFrame = config.timeframe
    candles_count: int = 500  # Enough for EMA 200 and ATR baseline

    def __init__(self, *, trader=None, name="SonTinhBot"):
        symbol = ForexSymbol(name=config.symbol)
        list_sessions = [Session(
            name=s['name'], start=s['start'], end=s['end']) for s in config.sessions]
        sessions_mgr = Sessions(sessions=list_sessions)

        super().__init__(symbol=symbol, sessions=sessions_mgr, name=name)

        # Interval matches timeframe M5 = 300 seconds
        self.tracker = Tracker(snooze=self.time_frame.seconds)
        self.trader = trader or SonTinhTrader(symbol=self.symbol)

        # Keep track of latest ATR for the trader to use for trailing SL
        self.current_atr: float = 0.0

    async def _check_filters(self, tick, atr_current: float, atr_avg: float) -> bool:
        """Check Market Constraints (Time, Spread, Volatility)"""
        # Dont run on weekend and monday morning
        weekday = datetime.now().weekday()
        current_hour = datetime.now().hour
        if weekday >= 5:  # Saturday, Sunday
            logger.warning(
                f"Market is closed on weekend. Skipping.")
            return False
        if weekday == 0 and current_hour < 2:  # Monday morning
            logger.warning(
                f"Market is closed on monday morning. Skipping.")
            return False
        # 1. Spread Check
        spread_pips = (tick.ask - tick.bid)
        logger.info(
            f"Start check filter with tick: {tick} - spread: {spread_pips} - atr_current: {atr_current} - atr_avg: {atr_avg}")
        if spread_pips > config.max_spread_pips:
            logger.warning(
                f"Spread {spread_pips:.1f} too high (target: {config.max_spread_pips}). Skipping.")
            return False

        if atr_current > atr_avg * config.compare_atr_avg_percent:
            logger.warning(
                f"ATR {atr_current:.1f} too high (target: {atr_avg * config.compare_atr_avg_percent}). Skipping.")
            return False

        return True

    async def find_entry(self):
        """Analyze market condition and search for entry signals."""
        # start find new entry
        rates = await self.symbol.copy_rates_from_pos(timeframe=self.time_frame, count=self.candles_count)
        if rates is None or len(rates) < self.ema_slow + 2:
            logger.warning(
                f"Not enough data for {self.symbol.name} {len(rates)}")
            self.tracker.update(order_type=None, snooze=self.tracker.snooze)
            return
        # Calculate Indicators
        rates.ta.ema(length=self.ema_fast, append=True)
        rates.ta.ema(length=self.ema_slow, append=True)
        rates.ta.rsi(length=self.rsi_period, append=True)
        rates.ta.atr(length=self.atr_period, append=True)
        current_price = rates['close'].iloc[-1]
        logger.info(f"""
            SYMBOL INFO:
                Name: {self.symbol.name}
                Point: {self.symbol.point}
                Pip: {self.symbol.pip}
                Min Volume: {self.symbol.volume_min}
                Max Volume: {self.symbol.volume_max}
                Step Volume: {self.symbol.volume_step}
                Current Price: {current_price}
        """)
        # test order
        # self.tracker.update(order_type=OrderType.SELL,
        #                     snooze=self.tracker.snooze)
        # return
        rates.rename(**{
            f"EMA_{self.ema_fast}": "ema50",
            f"EMA_{self.ema_slow}": "ema200",
            f"RSI_{self.rsi_period}": "rsi",
            f"ATRr_{self.atr_period}": "atr"
        }, inplace=True)

        logger.info(f"Rate info: \n {rates}")

        # Calculate a longer term average ATR for spike detection
        atr_avg = rates['atr'].mean()
        self.current_atr = rates['atr'].iloc[-1]

        # Grab tick for filters and spread
        tick = await self.symbol.info_tick()
        logger.info(f"Tick info: \n{tick}")

        if not await self._check_filters(tick, self.current_atr, atr_avg):
            self.tracker.update(order_type=None, snooze=self.tracker.snooze)
            return
        else:
            logger.info("Filter passed, continue to next step")

        # Trend conditions based on last 2 candles
        # Increase: EMA 50 > EMA 200 (On last 2 candles)
        uptrend = (rates['ema50'].iloc[-1] > rates['ema200'].iloc[-1]) and \
                  (rates['ema50'].iloc[-2] > rates['ema200'].iloc[-2])
        downtrend = (rates['ema50'].iloc[-1] < rates['ema200'].iloc[-1]) and \
                    (rates['ema50'].iloc[-2] < rates['ema200'].iloc[-2])
        # Current Candle values
        current_close = rates['close'].iloc[-1]
        current_ema50 = rates['ema50'].iloc[-1]
        current_rsi = rates['rsi'].iloc[-1]
        # Candle direction

        # Pullback closeness calculation: price touches/near EMA 50 (±0.1%)
        distance_pct = abs(current_close - current_ema50) / current_ema50 * 100

        signal = None
        logger.info(f"""\n
        Current Price: {current_close} - EMA50: {current_ema50} -> Distance percentage: {distance_pct}% - Target {config.ema_pullback_buffer_percent}%
        Trend: {'Up' if uptrend else 'Down'}
        RSI: {current_rsi} - Target RSI Buy: {config.rsi_buy_threshold} - Target RSI Sell: {config.rsi_sell_threshold}
        """)
        if uptrend and current_rsi < config.rsi_buy_threshold and distance_pct <= config.ema_pullback_buffer_percent:
            signal = OrderType.BUY

        elif downtrend and current_rsi > config.rsi_sell_threshold and distance_pct <= config.ema_pullback_buffer_percent:
            signal = OrderType.SELL

        if signal is not None:
            logger.info(f"Signal: {signal} Found...")
            self.tracker.update(order_type=signal, snooze=self.tracker.snooze)
        else:
            logger.warning(
                f"Cannot find any signals: [{signal}] to make an order. Continue to next candle")
            self.tracker.update(order_type=None, snooze=self.tracker.snooze)

    async def trade(self):
        """Execute bot logic per tick"""

        try:
            # 1. Manage existing open positions (Trailing SL / Partial Closes)
            if hasattr(self.trader, 'manage_open_positions'):
                await self.trader.manage_open_positions(current_atr=self.current_atr)

            # 2. Look for new entries
            await self.find_entry()

            # 3. Place Trade if Signal exists
            if self.tracker.order_type is not None:
                await self.trader.place_trade(
                    order_type=self.tracker.order_type,
                    atr=self.current_atr
                )

            # 4. Sleep until next timeframe or tick condition
            logger.info(
                f"Sleep for {self.tracker.snooze} seconds to wait next candle")
            await self.sleep(secs=self.tracker.snooze)

        except Exception as e:
            logger.error(f"Error in {self.name} trade loop: {e}")
            await self.sleep(secs=self.tracker.snooze)
