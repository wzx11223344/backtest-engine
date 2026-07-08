"""
策略模块 (Strategy Module)
==========================

包含策略基类和三个内置经典策略：

1. MovingAverageCrossStrategy - 均线交叉策略
   短期均线上穿长期均线买入，下穿卖出

2. RSIStrategy - RSI超买超卖策略
   RSI低于超卖线买入，高于超买线卖出

3. BollingerBandStrategy - 布林带突破策略
   价格跌破下轨买入（均值回归），突破上轨卖出

所有策略继承 Strategy 基类，实现 calculate_signals 方法。
策略通过 DataHandler 获取历史K线数据，计算技术指标后生成 SignalEvent。
"""

import numpy as np
from typing import Dict, List
from queue import Queue

from .events import Event, EventType, MarketEvent, SignalEvent
from .data import DataHandler


class Strategy:
    """
    策略基类

    所有策略必须继承此类并实现 calculate_signals 方法。
    策略接收 MarketEvent，通过 DataHandler 查询历史数据，
    计算技术指标后生成 SignalEvent 放入事件队列。

    参数:
        data_handler: 数据处理器实例（提供历史K线查询）
        events_queue: 事件队列（用于放入 SignalEvent）
    """

    def __init__(self, data_handler: DataHandler, events_queue: Queue):
        self.data_handler = data_handler
        self.events_queue = events_queue
        self.name: str = "Base"

    def calculate_signals(self, event: Event) -> None:
        """
        计算交易信号

        参数:
            event: 事件对象（通常为 MarketEvent）
        """
        raise NotImplementedError("子类必须实现 calculate_signals 方法")


class MovingAverageCrossStrategy(Strategy):
    """
    均线交叉策略 (Moving Average Crossover)

    经典的趋势跟踪策略：
    - 当短期均线上穿长期均线（金叉）时产生买入信号
    - 当短期均线下穿长期均线（死叉）时产生卖出信号

    参数:
        data_handler: 数据处理器
        events_queue: 事件队列
        short_window: 短期均线周期（默认5日）
        long_window: 长期均线周期（默认20日）

    信号逻辑:
        金叉: 前一日 short_ma <= long_ma 且 今日 short_ma > long_ma -> LONG
        死叉: 前一日 short_ma >= long_ma 且 今日 short_ma < long_ma -> EXIT
    """

    def __init__(self, data_handler: DataHandler, events_queue: Queue,
                 short_window: int = 5, long_window: int = 20):
        super().__init__(data_handler, events_queue)
        self.short_window = short_window
        self.long_window = long_window
        self.name = "MA_Cross"

        # 记录每只股票的持仓状态：'OUT'（空仓）或 'LONG'（持仓）
        self.bought: Dict[str, str] = {}
        for ticker in data_handler.tickers:
            self.bought[ticker] = 'OUT'

    def calculate_signals(self, event: Event) -> None:
        """
        计算均线交叉信号

        需要 long_window + 1 根K线来计算前一日和今日的均线交叉
        """
        if event.type != EventType.MARKET:
            return

        # 遍历所有标的
        for ticker in self.data_handler.tickers:
            # 跳过停牌的股票
            if event.symbols_data.get(ticker) is None:
                continue

            # 获取足够的历史K线数据（long_window + 1 根）
            bars = self.data_handler.get_latest_bars(ticker, self.long_window + 1)
            if len(bars) < self.long_window + 1:
                continue  # 数据不足，跳过

            # 提取收盘价数组
            closes = np.array([bar['close'] for bar in bars])

            # 计算今日均线
            short_ma_today = np.mean(closes[-self.short_window:])
            long_ma_today = np.mean(closes[-self.long_window:])

            # 计算昨日均线（用于判断交叉）
            short_ma_yesterday = np.mean(closes[-self.short_window - 1:-1])
            long_ma_yesterday = np.mean(closes[-self.long_window - 1:-1])

            # 金叉：短期均线上穿长期均线
            if (short_ma_yesterday <= long_ma_yesterday and
                    short_ma_today > long_ma_today):
                if self.bought[ticker] == 'OUT':
                    # 产生买入信号
                    signal = SignalEvent(ticker, event.timestamp, 'LONG')
                    self.events_queue.put(signal)
                    self.bought[ticker] = 'LONG'

            # 死叉：短期均线下穿长期均线
            elif (short_ma_yesterday >= long_ma_yesterday and
                  short_ma_today < long_ma_today):
                if self.bought[ticker] == 'LONG':
                    # 产生卖出信号
                    signal = SignalEvent(ticker, event.timestamp, 'EXIT')
                    self.events_queue.put(signal)
                    self.bought[ticker] = 'OUT'


class RSIStrategy(Strategy):
    """
    RSI超买超卖策略 (Relative Strength Index)

    基于RSI指标的均值回归策略：
    - RSI低于超卖线（如30）时，认为超卖，产生买入信号
    - RSI高于超买线（如70）时，认为超买，产生卖出信号

    RSI计算公式：
        RS = N日内平均涨幅 / N日内平均跌幅
        RSI = 100 - 100 / (1 + RS)

    参数:
        data_handler: 数据处理器
        events_queue: 事件队列
        rsi_period: RSI计算周期（默认14日）
        oversold: 超卖阈值（默认30，低于此值买入）
        overbought: 超买阈值（默认70，高于此值卖出）
    """

    def __init__(self, data_handler: DataHandler, events_queue: Queue,
                 rsi_period: int = 14, oversold: float = 30.0,
                 overbought: float = 70.0):
        super().__init__(data_handler, events_queue)
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.name = "RSI"

        # 记录每只股票的持仓状态
        self.bought: Dict[str, str] = {}
        for ticker in data_handler.tickers:
            self.bought[ticker] = 'OUT'

    def _calculate_rsi(self, closes: np.ndarray) -> float:
        """
        计算RSI指标值

        参数:
            closes: 收盘价数组（至少需要 rsi_period + 1 个数据点）

        返回:
            RSI值（0~100）
        """
        if len(closes) < self.rsi_period + 1:
            return 50.0  # 数据不足时返回中性值

        # 计算价格变化
        deltas = np.diff(closes)

        # 分离涨幅和跌幅
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        # 计算最近 rsi_period 日的平均涨幅和跌幅
        avg_gain = np.mean(gains[-self.rsi_period:])
        avg_loss = np.mean(losses[-self.rsi_period:])

        # 如果平均跌幅为0，RSI为100（极端超买）
        if avg_loss == 0:
            return 100.0

        # 计算 RS 和 RSI
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi

    def calculate_signals(self, event: Event) -> None:
        """计算RSI超买超卖信号"""
        if event.type != EventType.MARKET:
            return

        for ticker in self.data_handler.tickers:
            # 跳过停牌的股票
            if event.symbols_data.get(ticker) is None:
                continue

            # 获取足够的历史K线数据
            bars = self.data_handler.get_latest_bars(ticker, self.rsi_period + 2)
            if len(bars) < self.rsi_period + 1:
                continue

            # 提取收盘价并计算RSI
            closes = np.array([bar['close'] for bar in bars])
            rsi = self._calculate_rsi(closes)

            # 超卖：RSI低于超卖线，产生买入信号
            if rsi < self.oversold:
                if self.bought[ticker] == 'OUT':
                    signal = SignalEvent(ticker, event.timestamp, 'LONG')
                    self.events_queue.put(signal)
                    self.bought[ticker] = 'LONG'

            # 超买：RSI高于超买线，产生卖出信号
            elif rsi > self.overbought:
                if self.bought[ticker] == 'LONG':
                    signal = SignalEvent(ticker, event.timestamp, 'EXIT')
                    self.events_queue.put(signal)
                    self.bought[ticker] = 'OUT'


class BollingerBandStrategy(Strategy):
    """
    布林带突破策略 (Bollinger Band)

    基于布林带的均值回归策略：
    - 收盘价跌破下轨时买入（认为价格过度偏离，预期回归均值）
    - 收盘价突破上轨时卖出（认为价格过度偏高，预期回落）

    布林带计算：
        中轨 = N日移动平均线
        上轨 = 中轨 + num_std * N日标准差
        下轨 = 中轨 - num_std * N日标准差

    参数:
        data_handler: 数据处理器
        events_queue: 事件队列
        window: 布林带计算周期（默认20日）
        num_std: 标准差倍数（默认2.0）
    """

    def __init__(self, data_handler: DataHandler, events_queue: Queue,
                 window: int = 20, num_std: float = 2.0):
        super().__init__(data_handler, events_queue)
        self.window = window
        self.num_std = num_std
        self.name = "Bollinger"

        # 记录每只股票的持仓状态
        self.bought: Dict[str, str] = {}
        for ticker in data_handler.tickers:
            self.bought[ticker] = 'OUT'

    def _calculate_bands(self, closes: np.ndarray):
        """
        计算布林带的上轨、中轨、下轨

        参数:
            closes: 最近 window 根K线的收盘价数组

        返回:
            (upper, middle, lower) 三元组
        """
        middle = np.mean(closes)
        std = np.std(closes, ddof=0)  # 总体标准差
        upper = middle + self.num_std * std
        lower = middle - self.num_std * std
        return upper, middle, lower

    def calculate_signals(self, event: Event) -> None:
        """计算布林带突破信号"""
        if event.type != EventType.MARKET:
            return

        for ticker in self.data_handler.tickers:
            # 跳过停牌的股票
            if event.symbols_data.get(ticker) is None:
                continue

            # 获取足够的历史K线数据（window + 1 根用于判断前一日布林带）
            bars = self.data_handler.get_latest_bars(ticker, self.window + 1)
            if len(bars) < self.window + 1:
                continue

            closes = np.array([bar['close'] for bar in bars])

            # 今日布林带（使用最近 window 根K线）
            upper_today, middle_today, lower_today = self._calculate_bands(
                closes[-self.window:]
            )

            # 昨日布林带（使用倒数第2到第 window+1 根K线）
            upper_yesterday, middle_yesterday, lower_yesterday = self._calculate_bands(
                closes[-self.window - 1:-1]
            )

            current_close = closes[-1]
            yesterday_close = closes[-2]

            # 买入信号：昨日收盘价在下轨下方（或触及下轨），今日收盘价回到下轨上方
            # 表示价格从超卖区域回升，预期均值回归
            if yesterday_close <= lower_yesterday and current_close > lower_today:
                if self.bought[ticker] == 'OUT':
                    signal = SignalEvent(ticker, event.timestamp, 'LONG')
                    self.events_queue.put(signal)
                    self.bought[ticker] = 'LONG'

            # 卖出信号：昨日收盘价在上轨上方（或触及上轨），今日收盘价回到上轨下方
            # 表示价格从超买区域回落
            elif yesterday_close >= upper_yesterday and current_close < upper_today:
                if self.bought[ticker] == 'LONG':
                    signal = SignalEvent(ticker, event.timestamp, 'EXIT')
                    self.events_queue.put(signal)
                    self.bought[ticker] = 'OUT'
