"""
事件驱动回测引擎 (Event-Driven Backtest Engine)
===============================================

专业级事件驱动量化回测框架，支持：
- 多策略并行回测（均线交叉/RSI/布林带）
- 真实滑点与手续费建模
- A股T+1交易规则
- Brinson绩效归因分析
- HTML可视化报告

作者: backtest-engine
许可证: MIT
"""

from .events import EventType, Event, MarketEvent, SignalEvent, OrderEvent, FillEvent
from .data import DataHandler, HistoricalDataHandler
from .strategy import (
    Strategy,
    MovingAverageCrossStrategy,
    RSIStrategy,
    BollingerBandStrategy,
)
from .portfolio import Portfolio
from .broker import SimulatedBroker
from .metrics import PerformanceMetrics
from .report import HTMLReport

__version__ = "1.0.0"
__all__ = [
    "EventType",
    "Event",
    "MarketEvent",
    "SignalEvent",
    "OrderEvent",
    "FillEvent",
    "DataHandler",
    "HistoricalDataHandler",
    "Strategy",
    "MovingAverageCrossStrategy",
    "RSIStrategy",
    "BollingerBandStrategy",
    "Portfolio",
    "SimulatedBroker",
    "PerformanceMetrics",
    "HTMLReport",
]
