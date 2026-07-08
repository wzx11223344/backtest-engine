"""
数据处理器 (Data Handler)
==========================

负责从 akshare 加载A股历史行情数据，并按日期迭代推送 MarketEvent。

核心功能：
1. 从 akshare 获取真实A股日线数据（前复权）
2. 支持多只股票同时回测
3. 按交易日逐根推送 MarketEvent 到事件队列
4. 处理停牌（数据缺失）情况
5. 提供历史K线查询接口供策略使用

akshare 数据接口说明：
    ak.stock_zh_a_hist(symbol, period, start_date, end_date, adjust)
    - symbol: 股票代码，如 "600519"（贵州茅台）
    - period: "daily" / "weekly" / "monthly"
    - start_date / end_date: "YYYYMMDD" 格式
    - adjust: "qfq" 前复权 / "hfq" 后复权 / "" 不复权
    返回 DataFrame 列名（中文）：日期、开盘、收盘、最高、最低、成交量等
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Any
from queue import Queue

from .events import MarketEvent


class DataHandler:
    """
    数据处理器基类

    定义了数据处理器必须实现的接口：
    - update_bars: 推送下一根K线，生成 MarketEvent
    - get_latest_bars: 获取最近N根K线数据
    - get_latest_bar_value: 获取最新K线的某个字段值
    """

    def update_bars(self) -> None:
        """推送下一根K线数据，生成 MarketEvent 放入事件队列"""
        raise NotImplementedError("子类必须实现 update_bars 方法")

    def get_latest_bars(self, symbol: str, n: int = 1) -> List[Dict[str, Any]]:
        """获取指定标的最近 N 根K线数据"""
        raise NotImplementedError("子类必须实现 get_latest_bars 方法")

    def get_latest_bar_value(self, symbol: str, val_type: str = 'close') -> Optional[float]:
        """获取指定标的最新K线的某个字段值（open/close/high/low/volume）"""
        raise NotImplementedError("子类必须实现 get_latest_bar_value 方法")


class HistoricalDataHandler(DataHandler):
    """
    历史数据处理器

    从 akshare 加载A股历史日线数据，按交易日迭代推送 MarketEvent。

    参数:
        events_queue: 事件队列（Queue 实例）
        tickers: 股票代码列表，如 ["600519", "000858"]
        start_date: 开始日期，"YYYYMMDD" 格式
        end_date: 结束日期，"YYYYMMDD" 格式
        adjust: 复权方式，默认 "qfq"（前复权）

    属性:
        ticker_data: {ticker: DataFrame} 每只股票的完整历史数据
        latest_data: {ticker: list[dict]} 每只股票已推送的K线数据（用于策略查询）
        date_index: 所有交易日的排序列表（多股票交易日的并集）
        current_index: 当前推送到的日期索引
        continue_backtest: 是否还有数据需要推送
    """

    # akshare 返回的中文列名 -> 英文列名映射
    COLUMN_MAP = {
        '日期': 'datetime',
        '开盘': 'open',
        '收盘': 'close',
        '最高': 'high',
        '最低': 'low',
        '成交量': 'volume',
        '成交额': 'amount',
        '振幅': 'amplitude',
        '涨跌幅': 'pct_change',
        '涨跌额': 'change',
        '换手率': 'turnover',
    }

    def __init__(self, events_queue: Queue, tickers: List[str],
                 start_date: str, end_date: str, adjust: str = "qfq"):
        self.events_queue = events_queue
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.adjust = adjust

        # 数据存储
        self.ticker_data: Dict[str, pd.DataFrame] = {}
        self.latest_data: Dict[str, List[Dict[str, Any]]] = {}
        self.date_index: List[datetime] = []
        self.current_index: int = 0
        self.continue_backtest: bool = True

        # 加载数据
        self._load_data()

    def _load_data(self) -> None:
        """
        从 akshare 加载所有标的的历史数据

        1. 逐个获取每只股票的日线数据
        2. 重命名列为英文名
        3. 对齐所有股票的交易日（取并集）
        4. 初始化 latest_data 为空列表
        """
        all_dates = set()

        for ticker in self.tickers:
            try:
                # 调用 akshare 获取A股历史日线数据（前复权）
                df = ak.stock_zh_a_hist(
                    symbol=ticker,
                    period="daily",
                    start_date=self.start_date,
                    end_date=self.end_date,
                    adjust=self.adjust,
                )

                if df is None or df.empty:
                    print(f"[警告] 股票 {ticker} 未获取到数据，可能已退市或代码错误")
                    # 创建空的 DataFrame 以保持结构一致
                    df = pd.DataFrame(columns=list(self.COLUMN_MAP.values()))
                else:
                    # 重命名列为英文名
                    df = df.rename(columns=self.COLUMN_MAP)
                    # 转换日期列为 datetime 类型并设为索引
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    df = df.set_index('datetime')
                    df = df.sort_index()
                    # 收集所有交易日
                    all_dates.update(df.index.tolist())

                self.ticker_data[ticker] = df
                self.latest_data[ticker] = []

            except Exception as e:
                print(f"[错误] 加载股票 {ticker} 数据失败: {e}")
                self.ticker_data[ticker] = pd.DataFrame(
                    columns=list(self.COLUMN_MAP.values())
                )
                self.latest_data[ticker] = []

        # 排序所有交易日（取并集，处理不同股票交易日不一致的情况）
        self.date_index = sorted(list(all_dates))
        self.current_index = 0
        self.continue_backtest = len(self.date_index) > 0

        if self.continue_backtest:
            print(f"[数据] 共加载 {len(self.tickers)} 只股票，"
                  f"{len(self.date_index)} 个交易日 "
                  f"({self.date_index[0].strftime('%Y-%m-%d')} ~ "
                  f"{self.date_index[-1].strftime('%Y-%m-%d')})")

    def update_bars(self) -> None:
        """
        推送下一根K线数据

        1. 检查是否还有数据
        2. 获取当前日期所有股票的行情数据
        3. 更新 latest_data（供策略查询历史数据）
        4. 生成 MarketEvent 放入事件队列

        停牌处理：如果某只股票在当前日期没有数据，
        则该股票在 symbols_data 中的值为 None，策略会跳过该股票。
        """
        if self.current_index >= len(self.date_index):
            self.continue_backtest = False
            return

        current_date = self.date_index[self.current_index]
        self.current_index += 1

        # 获取当前日期所有股票的行情数据
        symbols_data: Dict[str, Optional[Dict[str, Any]]] = {}
        for ticker in self.tickers:
            df = self.ticker_data.get(ticker)
            if df is not None and not df.empty and current_date in df.index:
                # 获取该日期的行情数据
                bar = df.loc[current_date]
                # 转换为字典（包含日期信息）
                bar_dict = {
                    'datetime': current_date,
                    'open': float(bar['open']),
                    'close': float(bar['close']),
                    'high': float(bar['high']),
                    'low': float(bar['low']),
                    'volume': float(bar['volume']),
                }
                # 如果有成交额等其他字段，也加入
                if 'amount' in bar.index:
                    bar_dict['amount'] = float(bar['amount'])
                if 'pct_change' in bar.index:
                    bar_dict['pct_change'] = float(bar['pct_change'])
                if 'turnover' in bar.index:
                    bar_dict['turnover'] = float(bar['turnover'])

                symbols_data[ticker] = bar_dict
                # 更新 latest_data（追加到历史数据列表）
                self.latest_data[ticker].append(bar_dict)
            else:
                # 该股票在当前日期停牌或无数据
                symbols_data[ticker] = None

        # 生成 MarketEvent 放入事件队列
        event = MarketEvent(current_date, symbols_data)
        self.events_queue.put(event)

    def get_latest_bars(self, symbol: str, n: int = 1) -> List[Dict[str, Any]]:
        """
        获取指定标的最近 N 根K线数据

        参数:
            symbol: 股票代码
            n: K线数量

        返回:
            K线数据列表，每个元素是一个字典 {open, close, high, low, volume, ...}
            按时间正序排列（最早的在前，最新的在后）
            如果数据不足则返回所有可用数据
        """
        if symbol not in self.latest_data:
            return []
        data = self.latest_data[symbol]
        if len(data) <= n:
            return list(data)
        return list(data[-n:])

    def get_latest_bar_value(self, symbol: str, val_type: str = 'close') -> Optional[float]:
        """
        获取指定标的最新K线的某个字段值

        参数:
            symbol: 股票代码
            val_type: 字段名，如 'open', 'close', 'high', 'low', 'volume'

        返回:
            字段值（float），如果无数据则返回 None
        """
        bars = self.get_latest_bars(symbol, 1)
        if not bars:
            return None
        return bars[-1].get(val_type)

    def get_data_count(self) -> int:
        """获取总交易日数量（用于进度显示）"""
        return len(self.date_index)

    def get_ticker_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """获取指定标的的完整历史数据 DataFrame（用于报告生成）"""
        return self.ticker_data.get(symbol)
