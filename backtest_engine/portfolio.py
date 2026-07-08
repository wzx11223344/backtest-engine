"""
组合管理模块 (Portfolio)
=========================

负责管理回测过程中的持仓、现金流和净值计算。

核心功能：
1. 持仓追踪：记录每只股票的持仓数量
2. 现金流管理：跟踪可用资金
3. 净值计算（Mark-to-Market）：每日按收盘价计算组合总市值
4. 交易记录日志：记录所有成交信息
5. 信号转订单：将 SignalEvent 转换为 OrderEvent
6. A股T+1规则：当天买入的股票不能在当天卖出

组合净值计算公式：
    总市值 = 现金 + Σ(持仓数量 × 最新收盘价)
"""

from datetime import datetime
from typing import Dict, List, Any, Optional
from queue import Queue

from .events import Event, EventType, MarketEvent, SignalEvent, OrderEvent, FillEvent
from .data import DataHandler


class Portfolio:
    """
    投资组合管理器

    参数:
        data_handler: 数据处理器（提供最新价格查询）
        events_queue: 事件队列
        start_date: 回测开始日期
        initial_capital: 初始资金（默认100万）

    属性:
        current_positions: 当前持仓 {symbol: quantity}
        current_holdings: 当前市值 {symbol: market_value, cash, commission, total}
        all_positions: 历史持仓记录 [(date, {symbol: quantity})]
        all_holdings: 历史市值记录 [(date, {symbol: mv, cash, commission, total})]
        trades: 交易记录列表 [FillEvent]
    """

    def __init__(self, data_handler: DataHandler, events_queue: Queue,
                 start_date: str, initial_capital: float = 1000000.0):
        self.data_handler = data_handler
        self.events_queue = events_queue
        self.start_date = start_date
        self.initial_capital = initial_capital

        # 当前持仓：{symbol: quantity（正数表示多头）}
        self.current_positions: Dict[str, int] = {
            ticker: 0 for ticker in data_handler.tickers
        }

        # 当前市值快照
        self.current_holdings: Dict[str, float] = {
            ticker: 0.0 for ticker in data_handler.tickers
        }
        self.current_holdings['cash'] = initial_capital
        self.current_holdings['commission'] = 0.0
        self.current_holdings['total'] = initial_capital

        # 历史记录（用于回测后分析和报告生成）
        self.all_positions: List[tuple] = []  # [(date, {symbol: qty})]
        self.all_holdings: List[tuple] = []   # [(date, {symbol: mv, cash, ...})]

        # 交易记录
        self.trades: List[FillEvent] = []

        # 记录每只股票最近一次买入的日期（用于T+1规则检查）
        self.last_buy_date: Dict[str, Optional[datetime]] = {
            ticker: None for ticker in data_handler.tickers
        }

    def update_timeindex(self, event: MarketEvent) -> None:
        """
        更新时间索引：在每个 MarketEvent 到达时计算当前组合市值

        1. 记录当前持仓快照
        2. 按最新收盘价计算每只股票的市值
        3. 计算组合总市值 = 现金 + 各股票市值

        参数:
            event: MarketEvent
        """
        # 记录当前持仓快照
        positions_snapshot = dict(self.current_positions)
        self.all_positions.append((event.timestamp, positions_snapshot))

        # 复制当前市值快照并更新
        holdings = dict(self.current_holdings)

        # 按最新收盘价更新每只股票的市值
        for ticker in self.data_handler.tickers:
            bar_data = event.symbols_data.get(ticker)
            if bar_data is not None:
                # 正常交易：按收盘价计算市值
                price = bar_data['close']
                market_value = self.current_positions.get(ticker, 0) * price
                holdings[ticker] = market_value
            else:
                # 停牌：保持上一次的市值（不变）
                # holdings[ticker] 保持上次的值
                pass

        # 计算组合总市值
        total = holdings.get('cash', 0.0)
        for ticker in self.data_handler.tickers:
            total += holdings.get(ticker, 0.0)
        holdings['total'] = total

        # 更新当前市值和历史记录
        self.current_holdings = holdings
        self.all_holdings.append((event.timestamp, dict(holdings)))

    def update_positions_from_fill(self, fill: FillEvent) -> None:
        """
        根据成交回报更新持仓数量

        买入：持仓数量增加
        卖出：持仓数量减少

        参数:
            fill: FillEvent 成交回报
        """
        ticker = fill.symbol
        if fill.direction == 'BUY':
            self.current_positions[ticker] = self.current_positions.get(ticker, 0) + fill.quantity
            # 记录买入日期（用于T+1检查）
            self.last_buy_date[ticker] = fill.timestamp
        elif fill.direction == 'SELL':
            self.current_positions[ticker] = self.current_positions.get(ticker, 0) - fill.quantity

    def update_holdings_from_fill(self, fill: FillEvent) -> None:
        """
        根据成交回报更新现金流

        买入：现金减少（扣除成交金额 + 手续费）
        卖出：现金增加（成交金额 - 手续费）

        参数:
            fill: FillEvent 成交回报
        """
        ticker = fill.symbol
        cost = fill.fill_price * fill.quantity

        if fill.direction == 'BUY':
            # 买入：现金减少 = 成交金额 + 手续费
            self.current_holdings['cash'] -= (cost + fill.commission)
        elif fill.direction == 'SELL':
            # 卖出：现金增加 = 成交金额 - 手续费
            self.current_holdings['cash'] += (cost - fill.commission)

        # 累计手续费
        self.current_holdings['commission'] += fill.commission

    def update_fill(self, event: FillEvent) -> None:
        """
        处理 FillEvent：更新持仓和现金流，记录交易

        参数:
            event: FillEvent
        """
        if event.type != EventType.FILL:
            return

        self.update_positions_from_fill(event)
        self.update_holdings_from_fill(event)
        self.trades.append(event)

    def create_order_from_signal(self, signal: SignalEvent) -> None:
        """
        根据策略信号创建订单

        信号方向 -> 订单方向：
            LONG  -> BUY  （买入开仓）
            EXIT  -> SELL （卖出平仓）

        A股交易规则：
        - 买入：100股整数倍，使用可用资金的95%（留5%缓冲应对滑点和手续费）
        - 卖出：清仓全部持仓，但须遵守T+1规则
        - T+1：当天买入的股票不能在当天卖出

        参数:
            signal: SignalEvent
        """
        ticker = signal.symbol

        if signal.direction == 'LONG':
            # 买入信号：用可用资金的95%买入
            available_cash = self.current_holdings.get('cash', 0.0)
            price = self.data_handler.get_latest_bar_value(ticker, 'close')

            if price is None or price <= 0:
                return

            # 计算可买数量（100股整数倍）
            target_value = available_cash * 0.95
            raw_quantity = int(target_value / price)
            quantity = (raw_quantity // 100) * 100  # 向下取整到100的倍数

            if quantity < 100:
                return  # 资金不足，至少需要买100股

            # 检查是否已有持仓（避免重复买入）
            if self.current_positions.get(ticker, 0) > 0:
                return

            # 创建买入订单
            order = OrderEvent(ticker, 'MKT', quantity, 'BUY', signal.timestamp)
            self.events_queue.put(order)

        elif signal.direction == 'EXIT':
            # 卖出信号：清仓全部持仓
            current_position = self.current_positions.get(ticker, 0)
            if current_position <= 0:
                return  # 没有持仓可卖

            # T+1规则检查：当天买入的股票不能在当天卖出
            last_buy = self.last_buy_date.get(ticker)
            if last_buy is not None and last_buy == signal.timestamp:
                return  # T+1限制：当天买入不能卖出

            # 确保100股整数倍
            quantity = (current_position // 100) * 100
            if quantity < 100:
                return

            # 创建卖出订单
            order = OrderEvent(ticker, 'MKT', quantity, 'SELL', signal.timestamp)
            self.events_queue.put(order)

    def update_signal(self, event: SignalEvent) -> None:
        """
        处理 SignalEvent：将信号转换为订单

        参数:
            event: SignalEvent
        """
        if event.type != EventType.SIGNAL:
            return
        self.create_order_from_signal(event)

    def get_equity_curve(self):
        """
        获取净值曲线

        返回:
            (dates, equity_values) 元组
            dates: datetime 列表
            equity_values: 总市值列表
        """
        dates = [h[0] for h in self.all_holdings]
        equity = [h[1]['total'] for h in self.all_holdings]
        return dates, equity

    def get_positions_df(self):
        """
        获取历史持仓记录（用于报告）

        返回:
            DataFrame，索引为日期，列为各股票持仓数量
        """
        import pandas as pd
        if not self.all_positions:
            return pd.DataFrame()
        dates = [p[0] for p in self.all_positions]
        data = [p[1] for p in self.all_positions]
        df = pd.DataFrame(data, index=dates)
        return df

    def get_holdings_df(self):
        """
        获取历史市值记录（用于报告）

        返回:
            DataFrame，索引为日期，包含各股票市值、现金、总市值等列
        """
        import pandas as pd
        if not self.all_holdings:
            return pd.DataFrame()
        dates = [h[0] for h in self.all_holdings]
        data = [h[1] for h in self.all_holdings]
        df = pd.DataFrame(data, index=dates)
        return df
