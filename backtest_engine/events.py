"""
事件系统 (Event System)
========================

事件驱动架构的核心模块。所有回测逻辑通过事件队列(Queue)驱动，
四种事件类型构成完整的事件循环：

    MarketEvent  ->  SignalEvent  ->  OrderEvent  ->  FillEvent
    (市场数据)      (策略信号)       (订单指令)      (成交回报)

事件流转说明：
1. DataHandler 推送 MarketEvent 到队列
2. Strategy 接收 MarketEvent，计算后产生 SignalEvent
3. Portfolio 接收 SignalEvent，生成 OrderEvent
4. Broker 接收 OrderEvent，模拟执行后产生 FillEvent
5. Portfolio 接收 FillEvent，更新持仓和现金流
"""

from enum import Enum
from datetime import datetime
from typing import Dict, Any, Optional
from queue import Queue


class EventType(Enum):
    """
    事件类型枚举

    - MARKET: 市场数据到达事件，包含当前日期所有股票的行情数据
    - SIGNAL: 策略产生的交易信号事件，包含方向（做多/做空/平仓）
    - ORDER: 订单事件，包含具体的买卖指令
    - FILL: 成交回报事件，包含实际成交价格和手续费
    """
    MARKET = "MARKET"
    SIGNAL = "SIGNAL"
    ORDER = "ORDER"
    FILL = "FILL"


class Event:
    """
    事件基类

    所有具体事件类型的父类，定义了事件类型属性。
    在事件循环中通过 event.type 判断事件类型并分发到对应处理器。
    """
    type: EventType = None

    def __repr__(self) -> str:
        """事件的可读字符串表示，便于调试"""
        return f"<{self.__class__.__name__}>"


class MarketEvent(Event):
    """
    市场数据事件

    当新的行情数据到达时由 DataHandler 生成。
    包含当前时间戳和所有标的的行情数据快照。

    参数:
        timestamp: 当前日期时间（datetime 对象）
        symbols_data: 标的行情数据字典
            {symbol: {open, close, high, low, volume, ...}} 或 None（停牌）
    """

    def __init__(self, timestamp: datetime, symbols_data: Dict[str, Optional[Dict[str, Any]]]):
        self.type = EventType.MARKET
        self.timestamp = timestamp
        self.symbols_data = symbols_data

    def __repr__(self) -> str:
        symbols = list(self.symbols_data.keys()) if self.symbols_data else []
        return f"<MarketEvent timestamp={self.timestamp} symbols={symbols}>"


class SignalEvent(Event):
    """
    策略信号事件

    由 Strategy 生成，表示策略产生了交易信号。
    Portfolio 接收后转换为具体的订单。

    参数:
        symbol: 标的代码（如 "600519"）
        timestamp: 信号产生时间
        direction: 信号方向
            - 'LONG': 开多仓（买入）
            - 'SHORT': 开空仓（卖出做空，A股暂不支持）
            - 'EXIT': 平仓（卖出已有持仓）
        strength: 信号强度（0.0~1.0），可用于仓位管理，默认1.0
    """

    def __init__(self, symbol: str, timestamp: datetime,
                 direction: str, strength: float = 1.0):
        self.type = EventType.SIGNAL
        self.symbol = symbol
        self.timestamp = timestamp
        self.direction = direction
        self.strength = strength

    def __repr__(self) -> str:
        return (f"<SignalEvent symbol={self.symbol} "
                f"direction={self.direction} strength={self.strength}>")


class OrderEvent(Event):
    """
    订单事件

    由 Portfolio 生成，发送给 Broker 执行。
    包含具体的交易指令信息。

    参数:
        symbol: 标的代码
        order_type: 订单类型
            - 'MKT': 市价单（按当前市价成交）
            - 'LMT': 限价单（按指定价格成交，当前版本暂按市价处理）
        quantity: 订单数量（股数，A股须为100的整数倍）
        direction: 交易方向 'BUY'（买入）或 'SELL'（卖出）
        timestamp: 订单时间
    """

    def __init__(self, symbol: str, order_type: str, quantity: int,
                 direction: str, timestamp: datetime):
        self.type = EventType.ORDER
        self.symbol = symbol
        self.order_type = order_type
        self.quantity = quantity
        self.direction = direction
        self.timestamp = timestamp

    def __repr__(self) -> str:
        return (f"<OrderEvent symbol={self.symbol} type={self.order_type} "
                f"qty={self.quantity} direction={self.direction}>")


class FillEvent(Event):
    """
    成交回报事件

    由 Broker 在订单执行后生成，包含实际成交信息。
    Portfolio 接收后更新持仓和现金流。

    参数:
        symbol: 标的代码
        timestamp: 成交时间
        quantity: 成交数量
        direction: 成交方向 'BUY' 或 'SELL'
        fill_price: 实际成交价格（已包含滑点影响）
        commission: 总手续费（佣金+印花税+过户费）
        slippage_cost: 滑点成本（元）
    """

    def __init__(self, symbol: str, timestamp: datetime, quantity: int,
                 direction: str, fill_price: float, commission: float,
                 slippage_cost: float = 0.0):
        self.type = EventType.FILL
        self.symbol = symbol
        self.timestamp = timestamp
        self.quantity = quantity
        self.direction = direction
        self.fill_price = fill_price
        self.commission = commission
        self.slippage_cost = slippage_cost

    @property
    def trade_value(self) -> float:
        """成交金额 = 成交价 * 成交数量"""
        return self.fill_price * self.quantity

    def __repr__(self) -> str:
        return (f"<FillEvent symbol={self.symbol} qty={self.quantity} "
                f"direction={self.direction} price={self.fill_price:.2f} "
                f"commission={self.commission:.2f}>")


def create_event_queue() -> Queue:
    """
    创建事件队列

    回测引擎的事件循环核心，所有事件通过该队列传递。
    使用标准库 queue.Queue 实现线程安全的 FIFO 队列。

    返回:
        Queue 实例，用于在整个回测过程中传递事件
    """
    return Queue()
