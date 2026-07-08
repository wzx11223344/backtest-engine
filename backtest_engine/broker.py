"""
模拟券商模块 (Simulated Broker)
================================

模拟A股券商的订单执行过程，包括滑点模型和手续费模型。

滑点模型：
    成交价 = 最新收盘价 × (1 ± 滑点比例)
    买入时价格上移（成交价更高），卖出时价格下移（成交价更低）

A股手续费模型：
    1. 佣金：双向收取，费率通常为 0.03%（万三），最低5元
    2. 印花税：仅卖出收取，费率 0.1%（千一）
    3. 过户费：仅沪市股票（6开头）双向收取，费率 0.002%（万二）

A股交易规则：
    - T+1：当天买入的股票不能在当天卖出（在 Portfolio 层面检查）
    - 100股整数倍：买入和卖出数量必须是100的整数倍（在 Portfolio 层面处理）
    - 涨跌停限制：当前版本暂不模拟涨跌停（简化处理）
"""

from queue import Queue
from typing import Optional

from .events import Event, EventType, OrderEvent, FillEvent
from .data import DataHandler


class SimulatedBroker:
    """
    模拟券商执行器

    参数:
        events_queue: 事件队列（用于放入 FillEvent）
        data_handler: 数据处理器（提供最新价格查询）
        slippage: 滑点比例（默认0.001即0.1%）
        commission_rate: 佣金费率（默认0.0003即万三）
        stamp_duty_rate: 印花税率（默认0.001即千一，仅卖出）
        transfer_fee_rate: 过户费率（默认0.00002即万二，仅沪市）
        min_commission: 最低佣金（默认5元）

    属性:
        total_commission: 累计手续费
        total_slippage_cost: 累计滑点成本
    """

    def __init__(self, events_queue: Queue, data_handler: DataHandler,
                 slippage: float = 0.001,
                 commission_rate: float = 0.0003,
                 stamp_duty_rate: float = 0.001,
                 transfer_fee_rate: float = 0.00002,
                 min_commission: float = 5.0):
        self.events_queue = events_queue
        self.data_handler = data_handler

        # 滑点参数
        self.slippage = slippage

        # 手续费参数
        self.commission_rate = commission_rate
        self.stamp_duty_rate = stamp_duty_rate
        self.transfer_fee_rate = transfer_fee_rate
        self.min_commission = min_commission

        # 累计统计
        self.total_commission: float = 0.0
        self.total_slippage_cost: float = 0.0

    def _calculate_slippage(self, price: float, direction: str) -> float:
        """
        计算滑点后的成交价格

        买入：成交价 = 原价 × (1 + 滑点比例)，价格上移
        卖出：成交价 = 原价 × (1 - 滑点比例)，价格下移

        参数:
            price: 原始价格（最新收盘价）
            direction: 'BUY' 或 'SELL'

        返回:
            滑点后的成交价格
        """
        if direction == 'BUY':
            fill_price = price * (1.0 + self.slippage)
        else:  # SELL
            fill_price = price * (1.0 - self.slippage)

        # 确保成交价格为正数
        return max(fill_price, 0.01)

    def _calculate_commission(self, trade_value: float, direction: str,
                              ticker: str) -> float:
        """
        计算A股交易手续费

        手续费组成：
        1. 佣金 = max(成交金额 × 佣金费率, 最低佣金5元)
        2. 印花税 = 成交金额 × 印花税率（仅卖出）
        3. 过户费 = 成交金额 × 过户费率（仅沪市6开头股票，双向）

        参数:
            trade_value: 成交金额（成交价 × 成交数量）
            direction: 'BUY' 或 'SELL'
            ticker: 股票代码（用于判断是否为沪市）

        返回:
            总手续费（元）
        """
        # 1. 佣金（双向，最低5元）
        commission = trade_value * self.commission_rate
        commission = max(commission, self.min_commission)

        # 2. 印花税（仅卖出）
        stamp_duty = 0.0
        if direction == 'SELL':
            stamp_duty = trade_value * self.stamp_duty_rate

        # 3. 过户费（仅沪市股票，代码以6开头）
        transfer_fee = 0.0
        if ticker.startswith('6'):
            transfer_fee = trade_value * self.transfer_fee_rate

        # 总手续费
        total = commission + stamp_duty + transfer_fee
        return total

    def _is_sh_stock(self, ticker: str) -> bool:
        """判断是否为沪市股票（代码以6开头）"""
        return ticker.startswith('6')

    def execute_order(self, event: OrderEvent) -> None:
        """
        执行订单

        1. 获取最新收盘价
        2. 计算滑点后的成交价
        3. 计算手续费
        4. 生成 FillEvent 放入事件队列

        参数:
            event: OrderEvent 订单事件
        """
        if event.type != EventType.ORDER:
            return

        ticker = event.symbol
        quantity = event.quantity
        direction = event.direction

        # 获取最新收盘价作为基准价格
        price = self.data_handler.get_latest_bar_value(ticker, 'close')
        if price is None or price <= 0:
            # 无法获取价格，跳过订单
            return

        # 计算滑点后的成交价
        fill_price = self._calculate_slippage(price, direction)

        # 计算成交金额
        trade_value = fill_price * quantity

        # 计算手续费
        commission = self._calculate_commission(trade_value, direction, ticker)

        # 计算滑点成本（用于统计）
        slippage_cost = abs(fill_price - price) * quantity

        # 累计统计
        self.total_commission += commission
        self.total_slippage_cost += slippage_cost

        # 生成 FillEvent
        fill_event = FillEvent(
            symbol=ticker,
            timestamp=event.timestamp,
            quantity=quantity,
            direction=direction,
            fill_price=fill_price,
            commission=commission,
            slippage_cost=slippage_cost,
        )

        # 放入事件队列
        self.events_queue.put(fill_event)

    def get_stats(self) -> dict:
        """
        获取券商执行统计

        返回:
            包含累计手续费和滑点成本的字典
        """
        return {
            'total_commission': self.total_commission,
            'total_slippage_cost': self.total_slippage_cost,
        }
