# 事件驱动回测引擎 (Event-Driven Backtest Engine)

专业级事件驱动量化回测框架，使用真实A股数据（akshare），支持多策略回测、真实滑点与手续费建模、A股T+1交易规则、Brinson绩效归因分析。

## 特性

- **事件驱动架构**：基于 Queue 的事件循环，MarketEvent -> SignalEvent -> OrderEvent -> FillEvent
- **真实数据**：akshare 获取A股历史日线数据（前复权）
- **三大策略**：均线交叉（MA Cross）、RSI超买超卖、布林带突破
- **A股规则**：T+1交收、100股整数倍、印花税（卖出0.1%）、佣金（万三）、过户费（沪市万二）
- **滑点模型**：固定比例滑点，买入价格上移、卖出价格下移
- **绩效分析**：夏普比率、Sortino比率、最大回撤、Calmar比率、胜率、盈亏比
- **Brinson归因**：配置效应 + 选择效应 + 交互效应
- **HTML报告**：净值曲线、回撤曲线、月度收益率热力图，图片base64嵌入

## 快速开始

### 安装

```bash
cd backtest-engine
pip install -r requirements.txt
```

### 运行回测

```bash
# 均线交叉策略 - 贵州茅台 + 五粮液
python backtest.py --tickers 600519,000858 --strategy ma_cross --start 20230101 --end 20250101

# RSI策略 - 贵州茅台
python backtest.py --tickers 600519 --strategy rsi --start 20230101 --end 20250101

# 布林带策略 - 五粮液，初始资金50万
python backtest.py --tickers 000858 --strategy bollinger --start 20230101 --end 20250101 --capital 500000
```

### 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--tickers` | 股票代码，逗号分隔 | 必填 |
| `--strategy` | 策略: `ma_cross` / `rsi` / `bollinger` | `ma_cross` |
| `--start` | 开始日期 `YYYYMMDD` | 必填 |
| `--end` | 结束日期 `YYYYMMDD` | 必填 |
| `--capital` | 初始资金 | `1000000` |
| `--slippage` | 滑点比例 | `0.001` |
| `--commission` | 佣金费率 | `0.0003` |
| `--output` | 输出目录 | `output` |

## 内置策略

### 1. 均线交叉策略 (ma_cross)

短期均线上穿长期均线（金叉）买入，下穿（死叉）卖出。

- 短期均线：5日
- 长期均线：20日

### 2. RSI策略 (rsi)

RSI低于超卖线买入，高于超买线卖出。

- RSI周期：14日
- 超卖阈值：30
- 超买阈值：70

### 3. 布林带策略 (bollinger)

收盘价跌破下轨后回升买入，突破上轨后回落卖出（均值回归）。

- 计算周期：20日
- 标准差倍数：2.0

## 自定义策略

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
            bars = self.data_handler.get_latest_bars(ticker, 20)
            if len(bars) < 20:
                continue
            # 你的策略逻辑
            closes = [bar['close'] for bar in bars]
            # ... 计算指标 ...
            # signal = SignalEvent(ticker, event.timestamp, 'LONG')
            # self.events_queue.put(signal)
```

## 项目结构

```
backtest-engine/
├── backtest.py                # CLI入口
├── backtest_engine/
│   ├── __init__.py            # 包导出
│   ├── events.py              # 事件系统
│   ├── data.py                # 数据处理器
│   ├── strategy.py            # 策略模块
│   ├── portfolio.py           # 组合管理
│   ├── broker.py              # 模拟券商
│   ├── metrics.py             # 绩效指标
│   └── report.py              # HTML报告
├── requirements.txt
├── SKILL.md
└── README.md
```

## 事件驱动流程

```
DataHandler.update_bars()
        │
        ▼
   MarketEvent ──────────> Strategy.calculate_signals()
        │                          │
        │                    SignalEvent
        │                          │
        │                          ▼
        │                  Portfolio.update_signal()
        │                          │
        │                    OrderEvent
        │                          │
        │                          ▼
        │                  Broker.execute_order()
        │                          │
        │                    FillEvent
        │                          │
        ▼                          ▼
Portfolio.update_timeindex()  Portfolio.update_fill()
```

## A股交易规则

| 规则 | 说明 |
|------|------|
| T+1 | 当天买入的股票不能在当天卖出 |
| 最小单位 | 100股整数倍 |
| 佣金 | 双向，万三（最低5元） |
| 印花税 | 仅卖出，千一 |
| 过户费 | 仅沪市（6开头），双向，万二 |

## 依赖

- akshare >= 1.12.0
- numpy >= 1.24.0
- pandas >= 2.0.0
- scipy >= 1.10.0
- matplotlib >= 3.7.0
- rich >= 13.0.0

## 许可证

MIT License

## 免责声明

本项目仅供学习研究使用，不构成任何投资建议。回测结果不代表未来收益。投资有风险，入市需谨慎。
