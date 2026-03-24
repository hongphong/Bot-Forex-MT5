import asyncio
from logging import getLogger
from typing import Dict, Any, List
from datetime import datetime, time
from aiomql import Trader, OrderType, OrderCheckResult, TradePosition, Positions, Order, History
from utils.logger import logger
from config.sonting_config import config
import sys


class SonTinhTrader(Trader):
    """
    Trader class for SonTinh Bot.
    Handles Martingale lot sizing, partial SL/TP, trailing SL, and Trade placement.
    """
    history: History
    positions: Positions

    def __init__(self, *, symbol):
        super().__init__(symbol=symbol)

        self.history = History(date_from=datetime(2026, 1, 1),
                               date_to=datetime.now())
        self.positions = Positions()
        # Track partially closed positions to avoid multiple partial closures
        self._partially_closed_tickets: List[int] = []

    async def _calculate_next_lot(self, open_positions: tuple = None) -> float:
        """Calculate the next lot size based on OPEN positions (DCA logic)."""
        try:
            if not open_positions:
                return config.lot_start

            # Find the most recently opened position
            last_position = max(open_positions, key=lambda x: x.ticket)
            last_volume = last_position.volume

            for i, lot in enumerate(config.lot_progression):
                if abs(last_volume - lot) < 0.001:
                    if i + 1 < len(config.lot_progression):
                        return config.lot_progression[i + 1]
                    else:
                        # Reached max martingale level, keep max
                        return config.lot_progression[-1]
            return config.lot_start
        except Exception as e:
            logger.error(f"Error calculating next lot: {e}")
            return config.lot_start

    async def manage_dca(self):
        """Checks for 50 pips drawdown on the last position to add a new DCA order."""
        logger.info(
            "[MANAGE DCA] -------- Checking for DCA trigger ---------------")
        try:
            open_positions = await self.positions.get_positions(symbol=self.symbol.name)
            if not open_positions:
                return
            if len(open_positions) >= config.max_concurrent_orders:
                logger.info(
                    f"[MANAGE DCA] Max concurrent orders reached: {config.max_concurrent_orders}")
                return

            tick = await self.symbol.info_tick()
            last_position = max(open_positions, key=lambda x: x.ticket)

            current_price = tick.ask if last_position.type.is_short else tick.bid

            pips_loss = 0
            if last_position.type.is_long:
                pips_loss = (last_position.price_open -
                             current_price) / self.symbol.pip
            else:
                pips_loss = (current_price -
                             last_position.price_open) / self.symbol.pip
            logger.info(
                f"[MANAGE DCA] Pips loss: {pips_loss} - Current price: {current_price} - Last price: {last_position.price_open}")
            if pips_loss >= config.martingale_loss_trigger_pips:
                logger.info(
                    f"[MANAGE DCA] DCA TRIGGERED! Previous position {last_position.ticket} is down {pips_loss:.1f} pips.")
                # We place a new trade in the same direction
                await self.place_trade(order_type=last_position.type, atr=None)
            else:
                logger.info(
                    f"[MANAGE DCA] DCA NOT TRIGGERED! Previous position {last_position.ticket} is down {pips_loss:.1f} pips.")

        except Exception as e:
            logger.error(f"[MANAGE DCA] Error managing DCA: {e}")
        logger.info(
            "[MANAGE DCA] -------- End Checking for DCA trigger ---------------")

    async def place_trade(self, *, order_type: OrderType, parameters: Dict[str, Any] = None, atr: float = None):
        """Places a new trade with the appropriate lot size."""
        try:
            # Check maximum concurrent orders
            open_positions = await self.positions.get_positions(symbol=self.symbol.name)
            if open_positions and len(open_positions) >= config.max_concurrent_orders:
                logger.info(
                    f"[PLACE TRADE] Maximum concurrent orders reached: {config.max_concurrent_orders}. Skipping trade.")
                return
            else:
                if open_positions:
                    logger.info(
                        f"[PLACE TRADE] Number open positions: {len(open_positions)}")

            lot_size = await self._calculate_next_lot(open_positions)

            sl = config.initial_sl_pips / (config.lot_start * 1000)
            tp = (config.tp_target_usd / self.symbol.pip) / (config.lot_start * 1000)
            # Use aiomql Trader to compute SL and set volume
            tick = await self.symbol.info_tick()
            price = tick.ask if order_type.is_long else tick.bid

            # SL price
            if order_type.is_long:
                sl_price = price - sl
                tp_value = price + tp
            else:
                sl_price = price + sl
                tp_value = price - tp
            # We create an order without stops first, to use custom volume
            await self.create_order_no_stops(order_type=order_type, volume=lot_size)
            sl_value = round(sl_price, self.symbol.digits)

            logger.info(f""" [PLACE TRADE]
                Start Order: {self.order}
                Order Type: {"BUY" if order_type.is_long else "SELL"}
                Price: {price}
                Volume: {lot_size}
                SL: {sl_value} (Price - Initial SL * Lot: {price} - {sl}*{lot_size})
                TP: {tp_value} (Price + Target Profit * Lot: {price} + {config.tp_target_usd}*{lot_size})
                Ask price: {tick.ask}
                Bid price: {tick.bid}
            """)
            self.order.set_attributes(
                sl=sl_value, tp=tp_value, volume=lot_size, price=price)
            res = await self.send_order()
            if res and res.retcode == 10009:
                logger.info(
                    f"[PLACE TRADE] Opened {'BUY' if order_type.is_long else 'SELL'} trade on {self.symbol.name} at {price} with Lot: {lot_size}")
                await self.record_trade(result=res, parameters=parameters)
            else:
                logger.warning(
                    f"[PLACE TRADE] Failed to place trade: {res.comment if res else 'Unknown error'}")

            self.reset_order()

        except Exception as e:
            logger.error(f"[PLACE TRADE] Error placing trade: {e}")
            self.reset_order()

    async def manage_open_positions(self, current_atr: float = None):
        """
        Periodically checks open positions to apply:
        - Drawdown limit
        - DCA Grid Order Trigger
        - Partial TP / SL
        - Trailing Stop
        """
        try:
            account_info = await self.order.mt5.account_info()
            if account_info:
                # Max Drawdown check
                logger.info(
                    f"[MANAGE OPEN POSITIONS] ------------ Checking Drawdown ------------")
                equity = account_info.equity
                balance = account_info.balance
                logger.info(
                    f"[MANAGE OPEN POSITIONS] Equity: {equity} - Balance: {balance}")
                drawdown_pct = ((balance - equity) / balance) * \
                    100 if balance > 0 else 0
                logger.info(
                    f"[MANAGE OPEN POSITIONS] Current drawdown percentage: {drawdown_pct} %")
                if drawdown_pct >= config.max_drawdown_percent:
                    logger.critical(
                        f"[MANAGE OPEN POSITIONS] MAX DRAWDOWN REACHED ({drawdown_pct:.2f} %). Closing all positions.")
                    await self.positions.close_all_positions()
                    logger.info("Exiting the bot...")
                    sys.exit(0)
                logger.info(
                    f"[MANAGE OPEN POSITIONS] ------------ End Checking Drawdown ------------")

            # Important: First check DCA to add positions if needed
            await self.manage_dca()

            open_positions = await self.positions.get_positions(symbol=self.symbol.name)
            if not open_positions:
                logger.info(
                    "[MANAGE OPEN POSITIONS] No opening positions found. Exit manage opening positions")
                self._partially_closed_tickets.clear()
                return

            tick = await self.symbol.info_tick()

            for pos in open_positions:
                profit = pos.profit
                logger.info(
                    f"[MANAGE OPEN POSITIONS] ------------------- Checking Position {pos.ticket} profit: {profit} Target TP: {config.tp_target_usd} --------------------")

                # Check for fixed TP (TP target USD)
                if profit >= config.tp_target_usd:
                    logger.info(
                        f"[MANAGE OPEN POSITIONS] Take Profit reached for ticket {pos.ticket} (Profit: {profit:.2f} USD). Closing.")
                    await self.positions.close_position(position=pos)
                    if pos.ticket in self._partially_closed_tickets:
                        self._partially_closed_tickets.remove(pos.ticket)
                    continue

                # 1. Partial TP check
                if profit >= config.partial_tp_trigger_usd and pos.ticket not in self._partially_closed_tickets:
                    close_vol = pos.volume * config.partial_tp_percent
                    close_vol = max(self.symbol.volume_min, round(
                        close_vol / self.symbol.volume_step) * self.symbol.volume_step)
                    logger.info(
                        f"[MANAGE OPEN POSITIONS] Check Partial TP - Position [{pos.ticket}] - volume: {pos.volume} - profit: {profit} USD - Target close volume: {close_vol}")
                    if close_vol < pos.volume:
                        logger.info(
                            f"[MANAGE OPEN POSITIONS] Check Partial TP: Partial TP trigger hit for ticket {pos.ticket}. Closing {close_vol} volume.")
                        await self.positions.close(ticket=pos.ticket, symbol=pos.symbol, price=tick.bid if pos.type.is_long else tick.ask, volume=close_vol, order_type=pos.type)
                        self._partially_closed_tickets.append(pos.ticket)
                    continue

                # 2. Partial SL check (Tỉa lệnh khi âm)
                if profit <= config.partial_sl_trigger_usd and pos.ticket not in self._partially_closed_tickets:
                    close_vol = pos.volume * config.partial_sl_percent
                    close_vol = max(self.symbol.volume_min, round(
                        close_vol / self.symbol.volume_step) * self.symbol.volume_step)
                    logger.info(
                        f"[MANAGE OPEN POSITIONS] Check Partial SL - Position [{pos.ticket}] - volume: {pos.volume} - profit: {profit} USD - Target close volume: {close_vol}")
                    if close_vol < pos.volume:
                        logger.info(
                            f"[MANAGE OPEN POSITIONS] Check Partial SL: Partial SL trigger hit for ticket {pos.ticket}. Closing {close_vol} volume.")
                        await self.positions.close(ticket=pos.ticket, symbol=pos.symbol, price=tick.bid if pos.type.is_long else tick.ask, volume=close_vol, order_type=pos.type)
                        self._partially_closed_tickets.append(pos.ticket)
                    continue

                # 3. Trailing SL Logic (Trailing theo ATR/2)
                if profit >= config.trailing_sl_trigger_usd and current_atr is not None:
                    trail_dist = current_atr / config.trailing_sl_atr_divisor
                    new_sl = pos.price_current - \
                        trail_dist if pos.type.is_long else pos.price_current + trail_dist
                    new_sl = round(new_sl, self.symbol.digits)

                    # Only modify if it improves the SL towards our side
                    if pos.type.is_long and new_sl > pos.sl:
                        req = {
                            "action": 2,  # TradeAction.SLTP
                            "position": pos.ticket,
                            "symbol": pos.symbol,
                            "sl": new_sl,
                            "tp": pos.tp
                        }
                        res = await Order.send_order(request=req)
                        if res and res.retcode == 10009:
                            logger.info(
                                f"[MANAGE OPEN POSITIONS] Modified Trailing SL for long position {pos.ticket} to {new_sl}")

                    elif pos.type.is_short and (pos.sl == 0.0 or new_sl < pos.sl):
                        req = {
                            "action": 2,  # TradeAction.SLTP
                            "position": pos.ticket,
                            "symbol": pos.symbol,
                            "sl": new_sl,
                            "tp": pos.tp
                        }
                        res = await Order.send_order(request=req)
                        if res and res.retcode == 10009:
                            logger.info(
                                f"[MANAGE OPEN POSITIONS] Modified Trailing SL for short position {pos.ticket} to {new_sl}")
                logger.info(
                    f"[MANAGE OPEN POSITIONS] ------------------- End checking Position {pos.ticket} --------------------")

        except Exception as e:
            logger.error(
                f"[MANAGE OPEN POSITIONS] Error managing positions: {e}")
