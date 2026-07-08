---
slug: backtest-engine
displayName: 事件驱动回测引擎
version: 1.0.0
summary: 专业级事件驱动量化回测框架，支持多策略并行回测、真实滑点与手续费建模、A股T+1交易规则、Brinson绩效归因分析，内置均线交叉/RSI/布林带三大经典策略。
tags:
  - finance
  - backtesting
  - event-driven
  - quantitative-trading
  - strategy-evaluation
  - performance-attribution
license: MIT
---

# 事件驱动回测引擎 (Event-Driven Backtest Engine)

## 概述

专业级事件驱动量化回测框架，基于 Python 实现。采用经典的事件驱动架构（Event-Driven Architecture），通过事件队列（Queue）驱动整个回测流程，真实模拟交易过程中的信息流转。

## 核心特性

- **事件驱动架构**：MarketEvent -> SignalEvent -> OrderEvent -> FillEvent 完整事件链
- **真实数据源**：使用 akshare 获取A股真实历史行情数据（前复权）
- **三大经典策略**：均线交叉、RSI超买超卖、布林带突破
- **A股交易规则**：T+1交收、100股整数倍、印花税、佣金、过户费
- **真实成本建模**：固定/比例滑点模型，完整A股手续费体系
- **专业绩效分析**：夏普比率、Sortino比率、最大回撤、Calmar比率、胜率、盈亏比
- **Brinson归因**：配置效应 + 选择效应 + 交互效应分解
- **可视化报告**：净值曲线、回撤曲线、月度收益率热力图，HTML单文件输出

## 架构说明

```
┌──────────────┐     MarketEvent     ┌──────────────┐
│ DataHandler  │ ──────────────────> │  Strategy    │
│ (数据处理器)  │                     │ (策略引擎)    │
└──────────────┘                     └──────────────┘
                                           │
                                    SignalEvent
                                           │
                                           ▼
┌──────────────┐     FillEvent        ┌──────────────┐
│   Broker     │ <──────────────────  │  Portfolio   │
│ (模拟券商)    │     OrderEvent      │ (组合管理)    │
└──────────────┘ ──────────────────>  └──────────────┘
```

## 安装使用

### 1. 安装依赖

```bash
cd backtest-engine
pip install -r requirements.txt
```

### 2. 运行回测

```bash
# 均线交叉策略回测贵州茅台和五粮液
python backtest.py --tickers 600519,000858 --strategy ma_cross --start 20230101 --end 20250101

# RSI策略回测
python backtest.py --tickers 600519 --strategy rsi --start 20230101 --end 20250101

# 布林带策略回测
python backtest.py --tickers 000858 --strategy bollinger --start 20230101 --end 20250101 --capital 500000
```

### 3. 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| --tickers | 股票代码，逗号分隔 | （必填） |
| --strategy | 策略: ma_cross / rsi / bollinger | ma_cross |
| --start | 开始日期 YYYYMMDD | （必填） |
| --end | 结束日期 YYYYMMDD | （必填） |
| --capital | 初始资金 | 1000000 |
| --slippage | 滑点比例 | 0.001 |
| --commission | 佣金费率 | 0.0003 |
| --output | 输出目录 | output |

## 输出示例

回测完成后在 output/ 目录生成 HTML 报告，包含：

```
output/
└── backtest_report_MA_Cross_20230101_20250101.html
```

报告内容：
1. **绩效指标汇总**：总收益率、年化收益率、夏普比率、最大回撤等
2. **净值曲线图**：策略净值 vs 基准净值（归一化对比）
3. **回撤曲线图**：直观展示回撤区间和幅度
4. **月度收益率热力图**：按年-月展示每月收益率
5. **Brinson归因分析**：超额收益分解（配置效应/选择效应/交互效应）
6. **交易明细表**：每笔交易的时间、价格、数量、手续费

### 绩效指标输出示例

```
============================================================
                    绩效指标汇总
============================================================
  初始资金:             1,000,000.00
  期末净值:             1,234,567.89
  总收益率:                   23.46%
  年化收益率:                 11.23%
  年化波动率:                 18.56%
  夏普比率:                  0.4432
  Sortino比率:               0.6123
  最大回撤:                   -8.34%
  Calmar比率:                1.3466
------------------------------------------------------------
  总交易次数:                      42
  胜率:                         52.38%
  盈亏比:                       1.5678
  平均持仓天数:                  12.3
============================================================
```

## 能力边界

### 能做到

- 使用 akshare 获取A股真实历史日线数据进行回测
- 模拟A股完整交易成本（佣金+印花税+过户费+滑点）
- 正确执行T+1交易规则（当天买入不能当天卖出）
- 计算专业级绩效指标（夏普、Sortino、Calmar、最大回撤等）
- Brinson归因分析（需要基准数据）
- 生成包含图表的HTML可视化报告
- 支持多股票同时回测

### 不能做到

- 不支持实时行情交易（仅历史回测）
- 不支持做空（A股融券规则复杂，当前仅支持做多）
- 不模拟涨跌停板限制
- 不模拟分笔成交和盘口深度（使用日K线收盘价成交）
- 不支持分钟级/Tick级回测（当前为日线级别）
- 不提供投资建议（仅供学习研究）

## FAQ

### Q1: 运行时提示 "No module named 'akshare'" 怎么办？

**A:** 需要先安装依赖包。在项目根目录执行 `pip install -r requirements.txt`。akshare 是一个免费的A股数据接口库，无需注册 API Key。

### Q2: 回测结果中交易次数为0是什么原因？

**A:** 可能的原因：
1. 回测区间太短，策略参数所需的历史数据不足（如均线交叉策略需要至少21个交易日）
2. 股票在整个回测期间停牌
3. 初始资金不足以买入100股（A股最小交易单位）
4. 策略参数设置不合理（如RSI的超买/超卖阈值过极端）

### Q3: 为什么有些股票在某些日期没有数据？

**A:** 这表示该股票在当天停牌。引擎会自动处理停牌情况：停牌日不生成该股票的交易信号，持仓市值保持上一交易日的值。多股票回测时，交易日取所有股票交易日的并集。

### Q4: 滑点和手续费参数应该如何设置？

**A:** 参考值：
- **滑点**：0.001（0.1%）适用于流动性较好的大盘股，小盘股建议设为 0.002~0.003
- **佣金**：0.0003（万三）是大多数券商的散户佣金费率
- 印花税和过户费已按A股规则内置（卖出0.1%印花税，沪市0.002%过户费），无需手动设置

### Q5: 如何添加自定义策略？

**A:** 继承 `Strategy` 基类，实现 `calculate_signals` 方法：

```python
from backtest_engine import Strategy, SignalEvent, EventType

class MyStrategy(Strategy):
    def __init__(self, data_handler, events_queue):
        super().__init__(data_handler, events_queue)
        self.name = "MyStrategy"
        self.bought = {t: 'OUT' for t in data_handler.tickers}

    def calculate_signals(self, event):
        if event.type != EventType.MARKET:
            return
        for ticker in self.data_handler.tickers:
            if event.symbols_data.get(ticker) is None:
                continue
            bars = self.data_handler.get_latest_bars(ticker, 10)
            if len(bars) < 10:
                continue
            # 你的策略逻辑...
            # signal = SignalEvent(ticker, event.timestamp, 'LONG')
            # self.events_queue.put(signal)
```

### Q6: Brinson归因分析的基准是什么？

**A:** 当前版本默认使用回测标的中的第一只股票作为简单基准。如需使用自定义基准（如沪深300指数），可修改 `backtest.py` 中的基准数据获取逻辑，传入对应的 DataFrame。Brinson归因将超额收益分解为配置效应（资产配置贡献）和选择效应（个股选择贡献）。

### Q7: 报告中的中文字体显示为方框怎么办？

**A:** 这是 matplotlib 中文字体缺失的问题。代码已配置使用 SimHei 和 Microsoft YaHei 字体。如果仍然有问题，请安装中文字体或修改 `report.py` 中的字体配置：
```python
plt.rcParams['font.sans-serif'] = ['你的中文字体名称']
```

## 项目结构

```
backtest-engine/
├── backtest.py              # CLI入口（命令行参数解析、事件循环、报告生成）
├── backtest_engine/
│   ├── __init__.py          # 包初始化和导出
│   ├── events.py            # 事件系统（MarketEvent/SignalEvent/OrderEvent/FillEvent）
│   ├── data.py              # 数据处理器（akshare历史数据加载、日期迭代）
│   ├── strategy.py          # 策略基类+三大内置策略
│   ├── portfolio.py         # 组合管理（持仓追踪、现金流、T+1检查）
│   ├── broker.py            # 模拟券商（滑点、手续费、A股交易规则）
│   ├── metrics.py           # 绩效指标+Brinson归因分析
│   └── report.py            # HTML回测报告生成
├── requirements.txt         # Python依赖
├── SKILL.md                 # 本文件
└── README.md                # 项目说明
```

## 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| akshare | A股数据接口 | 获取真实历史行情数据 |
| numpy | 数值计算 | 技术指标计算 |
| pandas | 数据处理 | 时间序列分析 |
| scipy | 科学计算 | 统计分析 |
| matplotlib | 图表绘制 | 净值曲线、热力图 |
| rich | 终端美化 | 进度条、表格输出 |

## 许可证

MIT License - 仅供学习研究使用，不构成投资建议。
