"""
绩效指标模块 (Performance Metrics)
===================================

计算回测的各种绩效指标，包括：

收益率指标：
- 总收益率
- 年化收益率
- 年化波动率

风险调整收益：
- 夏普比率 (Sharpe Ratio)
- Sortino 比率 (仅考虑下行波动)
- Calmar 比率 (年化收益 / 最大回撤)

风险指标：
- 最大回撤 (Max Drawdown)

交易统计：
- 胜率 (Win Rate)
- 盈亏比 (Profit/Loss Ratio)
- 平均持仓天数
- 总交易次数

归因分析：
- Brinson 归因（配置效应 + 选择效应 + 交互效应）

可视化数据：
- 月度收益率热力图数据
- 净值曲线数据
- 回撤曲线数据
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

from .events import FillEvent


class PerformanceMetrics:
    """
    绩效指标计算器

    参数:
        all_holdings: 历史市值记录 [(date, {symbol: mv, cash, commission, total})]
        trades: 交易记录列表 [FillEvent]
        benchmark_data: 基准数据（可选），DataFrame 或 None
        initial_capital: 初始资金
        risk_free_rate: 无风险利率（年化，默认3%）
    """

    # 年化交易日数（A股约252个交易日）
    TRADING_DAYS = 252

    def __init__(self, all_holdings: List[tuple], trades: List[FillEvent],
                 benchmark_data: Optional[pd.DataFrame] = None,
                 initial_capital: float = 1000000.0,
                 risk_free_rate: float = 0.03):
        self.all_holdings = all_holdings
        self.trades = trades
        self.benchmark_data = benchmark_data
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate

        # 提取净值曲线
        self.dates: List[datetime] = [h[0] for h in all_holdings]
        self.equity: List[float] = [h[1]['total'] for h in all_holdings]

        # 转为 pandas Series 便于计算
        self.equity_series: pd.Series = pd.Series(
            self.equity, index=self.dates, name='equity'
        )

        # 计算日收益率
        self.returns: pd.Series = self.equity_series.pct_change().dropna()

        # 计算结果
        self.results: Dict[str, Any] = {}

    def calculate_all(self) -> Dict[str, Any]:
        """
        计算所有绩效指标

        返回:
            包含所有指标结果的字典
        """
        self.results['initial_capital'] = self.initial_capital
        self.results['final_equity'] = self.equity[-1] if self.equity else self.initial_capital
        self.results['total_return'] = self._total_return()
        self.results['annual_return'] = self._annual_return()
        self.results['annual_volatility'] = self._annual_volatility()
        self.results['sharpe_ratio'] = self._sharpe_ratio()
        self.results['sortino_ratio'] = self._sortino_ratio()
        self.results['max_drawdown'] = self._max_drawdown()
        self.results['max_drawdown_duration'] = self._max_drawdown_duration()
        self.results['calmar_ratio'] = self._calmar_ratio()
        self.results['total_trades'] = len(self.trades)

        # 交易统计
        trade_pairs = self._calculate_trade_pairs()
        self.results['win_rate'] = self._win_rate(trade_pairs)
        self.results['profit_loss_ratio'] = self._profit_loss_ratio(trade_pairs)
        self.results['avg_holding_days'] = self._avg_holding_days(trade_pairs)
        self.results['avg_profit'] = self._avg_profit(trade_pairs)
        self.results['avg_loss'] = self._avg_loss(trade_pairs)
        self.results['max_profit'] = self._max_profit(trade_pairs)
        self.results['max_loss'] = self._max_loss(trade_pairs)

        # 月度收益率
        self.results['monthly_returns'] = self._monthly_returns()

        # 回撤序列
        self.results['drawdown_series'] = self._drawdown_series()

        # Brinson 归因（如果有基准数据）
        if self.benchmark_data is not None:
            self.results['brinson_attribution'] = self._brinson_attribution()
        else:
            self.results['brinson_attribution'] = None

        return self.results

    # ===================== 收益率指标 =====================

    def _total_return(self) -> float:
        """计算总收益率 = (期末净值 / 期初净值) - 1"""
        if len(self.equity) < 2:
            return 0.0
        return (self.equity[-1] / self.equity[0]) - 1.0

    def _annual_return(self) -> float:
        """
        计算年化收益率

        年化收益率 = (1 + 总收益率) ^ (365 / 实际天数) - 1
        """
        if len(self.equity) < 2 or len(self.dates) < 2:
            return 0.0
        total_days = (self.dates[-1] - self.dates[0]).days
        if total_days <= 0:
            return 0.0
        total_return = self._total_return()
        return (1.0 + total_return) ** (365.0 / total_days) - 1.0

    def _annual_volatility(self) -> float:
        """
        计算年化波动率

        年化波动率 = 日收益率标准差 × sqrt(252)
        """
        if len(self.returns) < 2:
            return 0.0
        return float(self.returns.std() * np.sqrt(self.TRADING_DAYS))

    # ===================== 风险调整收益指标 =====================

    def _sharpe_ratio(self) -> float:
        """
        计算夏普比率

        夏普比率 = (年化收益率 - 无风险利率) / 年化波动率
        """
        vol = self._annual_volatility()
        if vol == 0:
            return 0.0
        annual_return = self._annual_return()
        return (annual_return - self.risk_free_rate) / vol

    def _sortino_ratio(self) -> float:
        """
        计算 Sortino 比率

        Sortino 比率 = (年化收益率 - 无风险利率) / 年化下行波动率
        下行波动率仅计算负收益的标准差
        """
        if len(self.returns) < 2:
            return 0.0
        downside_returns = self.returns[self.returns < 0]
        if len(downside_returns) == 0:
            return float('inf') if self._annual_return() > self.risk_free_rate else 0.0
        downside_std = float(downside_returns.std() * np.sqrt(self.TRADING_DAYS))
        if downside_std == 0:
            return 0.0
        return (self._annual_return() - self.risk_free_rate) / downside_std

    # ===================== 风险指标 =====================

    def _max_drawdown(self) -> float:
        """
        计算最大回撤

        最大回撤 = max((峰值 - 谷值) / 峰值)
        遍历净值曲线，记录历史最高点，计算每个时点的回撤
        """
        if len(self.equity) < 2:
            return 0.0
        peak = self.equity[0]
        max_dd = 0.0
        for value in self.equity:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _drawdown_series(self) -> pd.Series:
        """
        计算回撤序列（用于绘制回撤曲线）

        返回:
            pd.Series，每个时点的回撤比例（负数或0）
        """
        if len(self.equity) < 2:
            return pd.Series(dtype=float)
        equity = self.equity_series
        peak = equity.expanding().max()
        drawdown = (equity - peak) / peak
        return drawdown

    def _max_drawdown_duration(self) -> int:
        """
        计算最大回撤持续天数

        从峰值到恢复到峰值的天数
        """
        if len(self.equity) < 2:
            return 0
        peak = self.equity[0]
        max_dd_date_index = 0
        peak_date_index = 0
        max_dd = 0.0
        current_peak_index = 0

        for i, value in enumerate(self.equity):
            if value > peak:
                peak = value
                current_peak_index = i
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
                max_dd_date_index = i
                peak_date_index = current_peak_index

        return max_dd_date_index - peak_date_index

    def _calmar_ratio(self) -> float:
        """
        计算 Calmar 比率

        Calmar 比率 = 年化收益率 / 最大回撤
        """
        mdd = self._max_drawdown()
        if mdd == 0:
            return 0.0
        return self._annual_return() / mdd

    # ===================== 交易统计 =====================

    def _calculate_trade_pairs(self) -> List[Dict[str, Any]]:
        """
        配对买卖交易，计算每笔完整交易的盈亏

        配对逻辑：按时间顺序，将每次买入与后续的卖出配对
        采用 FIFO（先进先出）原则

        返回:
            交易对列表，每个元素包含：
            {
                'symbol': 股票代码,
                'buy_date': 买入日期,
                'sell_date': 卖出日期,
                'buy_price': 买入价格,
                'sell_price': 卖出价格,
                'quantity': 成交数量,
                'pnl': 盈亏金额（扣除手续费）,
                'return_pct': 盈亏百分比,
                'holding_days': 持仓天数
            }
        """
        # 按股票分组
        ticker_trades: Dict[str, List[FillEvent]] = {}
        for trade in self.trades:
            if trade.symbol not in ticker_trades:
                ticker_trades[trade.symbol] = []
            ticker_trades[trade.symbol].append(trade)

        trade_pairs: List[Dict[str, Any]] = []

        for ticker, trades in ticker_trades.items():
            # 按时间排序
            trades_sorted = sorted(trades, key=lambda x: x.timestamp)

            # 买入队列（FIFO）
            buy_queue: List[FillEvent] = []

            for trade in trades_sorted:
                if trade.direction == 'BUY':
                    buy_queue.append(trade)
                elif trade.direction == 'SELL':
                    # 与最早的买入配对
                    if buy_queue:
                        buy_trade = buy_queue.pop(0)

                        # 计算盈亏（扣除双边手续费）
                        gross_pnl = (trade.fill_price - buy_trade.fill_price) * trade.quantity
                        net_pnl = gross_pnl - buy_trade.commission - trade.commission

                        # 计算持仓天数
                        holding_days = (trade.timestamp - buy_trade.timestamp).days

                        # 计算盈亏百分比
                        cost = buy_trade.fill_price * trade.quantity + buy_trade.commission
                        return_pct = net_pnl / cost if cost > 0 else 0.0

                        trade_pairs.append({
                            'symbol': ticker,
                            'buy_date': buy_trade.timestamp,
                            'sell_date': trade.timestamp,
                            'buy_price': buy_trade.fill_price,
                            'sell_price': trade.fill_price,
                            'quantity': trade.quantity,
                            'pnl': net_pnl,
                            'return_pct': return_pct,
                            'holding_days': holding_days,
                        })

        return trade_pairs

    def _win_rate(self, trade_pairs: List[Dict[str, Any]]) -> float:
        """
        计算胜率

        胜率 = 盈利交易次数 / 总交易次数
        """
        if not trade_pairs:
            return 0.0
        wins = sum(1 for t in trade_pairs if t['pnl'] > 0)
        return wins / len(trade_pairs)

    def _profit_loss_ratio(self, trade_pairs: List[Dict[str, Any]]) -> float:
        """
        计算盈亏比

        盈亏比 = 平均盈利金额 / 平均亏损金额
        """
        if not trade_pairs:
            return 0.0
        profits = [t['pnl'] for t in trade_pairs if t['pnl'] > 0]
        losses = [t['pnl'] for t in trade_pairs if t['pnl'] < 0]

        if not profits or not losses:
            return float('inf') if profits else 0.0

        avg_profit = np.mean(profits)
        avg_loss = abs(np.mean(losses))

        if avg_loss == 0:
            return float('inf')

        return avg_profit / avg_loss

    def _avg_holding_days(self, trade_pairs: List[Dict[str, Any]]) -> float:
        """计算平均持仓天数"""
        if not trade_pairs:
            return 0.0
        return float(np.mean([t['holding_days'] for t in trade_pairs]))

    def _avg_profit(self, trade_pairs: List[Dict[str, Any]]) -> float:
        """计算平均盈利金额（仅盈利交易）"""
        profits = [t['pnl'] for t in trade_pairs if t['pnl'] > 0]
        if not profits:
            return 0.0
        return float(np.mean(profits))

    def _avg_loss(self, trade_pairs: List[Dict[str, Any]]) -> float:
        """计算平均亏损金额（仅亏损交易，返回负数）"""
        losses = [t['pnl'] for t in trade_pairs if t['pnl'] < 0]
        if not losses:
            return 0.0
        return float(np.mean(losses))

    def _max_profit(self, trade_pairs: List[Dict[str, Any]]) -> float:
        """计算最大单笔盈利"""
        if not trade_pairs:
            return 0.0
        return max(t['pnl'] for t in trade_pairs)

    def _max_loss(self, trade_pairs: List[Dict[str, Any]]) -> float:
        """计算最大单笔亏损"""
        if not trade_pairs:
            return 0.0
        return min(t['pnl'] for t in trade_pairs)

    # ===================== 月度收益率 =====================

    def _monthly_returns(self) -> pd.DataFrame:
        """
        计算月度收益率

        将日净值曲线重采样为月频，计算每月收益率
        用于生成月度收益率热力图

        返回:
            DataFrame，行为年份，列为月份（1~12），值为月收益率
        """
        if len(self.equity_series) < 2:
            return pd.DataFrame()

        # 重采样为月频（取每月最后一个交易日的净值）
        monthly_equity = self.equity_series.resample('ME').last()

        # 计算月收益率
        monthly_returns = monthly_equity.pct_change().dropna()

        # 转换为热力图格式（行为年份，列为月份）
        if monthly_returns.empty:
            return pd.DataFrame()

        # 提取年份和月份
        df = pd.DataFrame({
            'year': monthly_returns.index.year,
            'month': monthly_returns.index.month,
            'return': monthly_returns.values,
        })

        # 透视表：行为年份，列为月份
        heatmap_data = df.pivot_table(
            index='year', columns='month', values='return', aggfunc='first'
        )

        # 确保列包含1~12月
        for m in range(1, 13):
            if m not in heatmap_data.columns:
                heatmap_data[m] = np.nan
        heatmap_data = heatmap_data[sorted(heatmap_data.columns)]

        return heatmap_data

    # ===================== Brinson 归因分析 =====================

    def _brinson_attribution(self) -> Optional[Dict[str, Any]]:
        """
        Brinson 归因分析

        将超额收益分解为：
        1. 配置效应 (Allocation Effect)：衡量资产配置选择的贡献
           配置效应 = Σ (wp_i - wb_i) × (rb_i - Rb)
        2. 选择效应 (Selection Effect)：衡量个股选择的贡献
           选择效应 = Σ wb_i × (rp_i - rb_i)
        3. 交互效应 (Interaction Effect)
           交互效应 = Σ (wp_i - wb_i) × (rp_i - rb_i)

        其中：
        - wp_i: 投资组合中第 i 类资产的权重
        - wb_i: 基准中第 i 类资产的权重
        - rp_i: 投资组合中第 i 类资产的收益率
        - rb_i: 基准中第 i 类资产的收益率
        - Rb: 基准总收益率

        返回:
            包含归因分析结果的字典，或 None（如果无基准数据）
        """
        if self.benchmark_data is None or self.benchmark_data.empty:
            return None

        # 获取投资组合中各标的的权重和收益率
        # 使用 all_holdings 中的持仓数据计算各标的的权重
        portfolio_weights: Dict[str, float] = {}
        portfolio_returns: Dict[str, float] = {}

        # 计算投资组合各标的的平均权重和收益率
        for ticker in self._get_all_tickers():
            # 计算该标的在组合中的平均权重
            total_value = sum(h[1].get(ticker, 0) for h in self.all_holdings)
            total_equity = sum(h[1]['total'] for h in self.all_holdings)
            if total_equity > 0:
                portfolio_weights[ticker] = total_value / total_equity
            else:
                portfolio_weights[ticker] = 0.0

            # 从 holdings 数据计算该标的的收益率
            values = [h[1].get(ticker, 0) for h in self.all_holdings]
            if len(values) >= 2 and values[0] > 0:
                portfolio_returns[ticker] = (values[-1] / values[0]) - 1.0
            else:
                portfolio_returns[ticker] = 0.0

        # 获取基准数据中各标的的权重和收益率
        benchmark_weights: Dict[str, float] = {}
        benchmark_returns: Dict[str, float] = {}

        if isinstance(self.benchmark_data, pd.DataFrame):
            # 如果 benchmark_data 是 DataFrame，假设索引为日期，列为各标的收盘价
            for ticker in self._get_all_tickers():
                if ticker in self.benchmark_data.columns:
                    prices = self.benchmark_data[ticker].dropna()
                    if len(prices) >= 2:
                        benchmark_returns[ticker] = (prices.iloc[-1] / prices.iloc[0]) - 1.0
                    else:
                        benchmark_returns[ticker] = 0.0
                    # 基准权重设为等权重
                    benchmark_weights[ticker] = 1.0 / len(self._get_all_tickers())
                else:
                    benchmark_returns[ticker] = 0.0
                    benchmark_weights[ticker] = 1.0 / len(self._get_all_tickers())

        # 计算基准总收益率
        Rb = sum(
            benchmark_weights.get(t, 0) * benchmark_returns.get(t, 0)
            for t in self._get_all_tickers()
        )

        # 计算归因效应
        allocation_effect = 0.0  # 配置效应
        selection_effect = 0.0   # 选择效应
        interaction_effect = 0.0  # 交互效应

        detail: List[Dict[str, Any]] = []

        for ticker in self._get_all_tickers():
            wp = portfolio_weights.get(ticker, 0.0)
            wb = benchmark_weights.get(ticker, 0.0)
            rp = portfolio_returns.get(ticker, 0.0)
            rb = benchmark_returns.get(ticker, 0.0)

            # 配置效应 = (wp - wb) × (rb - Rb)
            alloc = (wp - wb) * (rb - Rb)

            # 选择效应 = wb × (rp - rb)
            select = wb * (rp - rb)

            # 交互效应 = (wp - wb) × (rp - rb)
            interact = (wp - wb) * (rp - rb)

            allocation_effect += alloc
            selection_effect += select
            interaction_effect += interact

            detail.append({
                'symbol': ticker,
                'portfolio_weight': wp,
                'benchmark_weight': wb,
                'portfolio_return': rp,
                'benchmark_return': rb,
                'allocation_effect': alloc,
                'selection_effect': select,
                'interaction_effect': interact,
            })

        # 超额收益 = 配置效应 + 选择效应 + 交互效应
        excess_return = allocation_effect + selection_effect + interaction_effect

        # 组合总收益率
        Rp = sum(
            portfolio_weights.get(t, 0) * portfolio_returns.get(t, 0)
            for t in self._get_all_tickers()
        )

        return {
            'portfolio_return': Rp,
            'benchmark_return': Rb,
            'excess_return': excess_return,
            'allocation_effect': allocation_effect,
            'selection_effect': selection_effect,
            'interaction_effect': interaction_effect,
            'detail': detail,
        }

    def _get_all_tickers(self) -> List[str]:
        """获取所有涉及的标的代码"""
        if not self.all_holdings:
            return []
        # 从第一个 holdings 快照中获取标的列表
        first_holdings = self.all_holdings[0][1]
        return [k for k in first_holdings.keys() if k not in ('cash', 'commission', 'total')]

    # ===================== 辅助方法 =====================

    def get_equity_curve_normalized(self) -> pd.Series:
        """
        获取归一化净值曲线（初始净值为1.0）

        用于与基准比较
        """
        if len(self.equity_series) < 2:
            return pd.Series(dtype=float)
        return self.equity_series / self.equity_series.iloc[0]

    def get_benchmark_curve_normalized(self) -> Optional[pd.Series]:
        """
        获取归一化基准曲线（初始净值为1.0）

        如果没有基准数据则返回 None
        """
        if self.benchmark_data is None or self.benchmark_data.empty:
            return None

        if isinstance(self.benchmark_data, pd.DataFrame):
            # 取所有列的平均作为基准
            benchmark = self.benchmark_data.mean(axis=1).dropna()
            if len(benchmark) < 2:
                return None
            return benchmark / benchmark.iloc[0]

        return None

    def format_results(self) -> str:
        """
        格式化绩效指标为可读字符串

        返回:
            格式化的绩效指标文本
        """
        r = self.results
        lines = [
            "=" * 60,
            "                    绩效指标汇总",
            "=" * 60,
            f"  初始资金:       {r.get('initial_capital', 0):>15,.2f}",
            f"  期末净值:       {r.get('final_equity', 0):>15,.2f}",
            f"  总收益率:       {r.get('total_return', 0):>15.2%}",
            f"  年化收益率:     {r.get('annual_return', 0):>15.2%}",
            f"  年化波动率:     {r.get('annual_volatility', 0):>15.2%}",
            f"  夏普比率:       {r.get('sharpe_ratio', 0):>15.4f}",
            f"  Sortino比率:    {r.get('sortino_ratio', 0):>15.4f}",
            f"  最大回撤:       {r.get('max_drawdown', 0):>15.2%}",
            f"  Calmar比率:     {r.get('calmar_ratio', 0):>15.4f}",
            "-" * 60,
            f"  总交易次数:     {r.get('total_trades', 0):>15d}",
            f"  胜率:           {r.get('win_rate', 0):>15.2%}",
            f"  盈亏比:         {r.get('profit_loss_ratio', 0):>15.4f}",
            f"  平均持仓天数:   {r.get('avg_holding_days', 0):>15.1f}",
            f"  平均盈利:       {r.get('avg_profit', 0):>15,.2f}",
            f"  平均亏损:       {r.get('avg_loss', 0):>15,.2f}",
            f"  最大单笔盈利:   {r.get('max_profit', 0):>15,.2f}",
            f"  最大单笔亏损:   {r.get('max_loss', 0):>15,.2f}",
        ]

        # Brinson 归因
        brinson = r.get('brinson_attribution')
        if brinson:
            lines.extend([
                "-" * 60,
                "  Brinson 归因分析:",
                f"    组合收益率:     {brinson['portfolio_return']:>12.4%}",
                f"    基准收益率:     {brinson['benchmark_return']:>12.4%}",
                f"    超额收益:       {brinson['excess_return']:>12.4%}",
                f"    配置效应:       {brinson['allocation_effect']:>12.4%}",
                f"    选择效应:       {brinson['selection_effect']:>12.4%}",
                f"    交互效应:       {brinson['interaction_effect']:>12.4%}",
            ])

        lines.append("=" * 60)
        return "\n".join(lines)
