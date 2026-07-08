"""
HTML报告生成模块 (Report Generator)
=====================================

生成完整的HTML回测报告，包含：
1. 净值曲线图（策略 vs 基准）
2. 回撤曲线图
3. 月度收益率热力图
4. 交易明细表
5. 绩效指标汇总表
6. Brinson归因分析表（如有基准数据）

所有图表使用 matplotlib 生成，图片以 base64 编码嵌入 HTML，
生成一个独立的单文件 HTML 报告，无需额外资源文件。
"""

import base64
import io
import os
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional, List

# 使用非交互式后端，避免在无显示器环境中报错
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# 设置中文字体（支持中文显示）
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False  # 正确显示负号

from .metrics import PerformanceMetrics
from .portfolio import Portfolio
from .events import FillEvent


class HTMLReport:
    """
    HTML回测报告生成器

    参数:
        metrics: PerformanceMetrics 实例（已调用 calculate_all）
        portfolio: Portfolio 实例（提供交易记录和持仓数据）
        strategy_name: 策略名称
        tickers: 标的代码列表
        start_date: 回测开始日期
        end_date: 回测结束日期
    """

    def __init__(self, metrics: PerformanceMetrics, portfolio: Portfolio,
                 strategy_name: str, tickers: List[str],
                 start_date: str, end_date: str):
        self.metrics = metrics
        self.portfolio = portfolio
        self.strategy_name = strategy_name
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date

    def _fig_to_base64(self, fig: plt.Figure) -> str:
        """
        将 matplotlib Figure 转换为 base64 编码字符串

        参数:
            fig: matplotlib Figure 对象

        返回:
            base64 编码的 PNG 图片字符串
        """
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        return img_base64

    def _generate_equity_curve_plot(self) -> str:
        """
        生成净值曲线图（策略 vs 基准）

        返回:
            base64 编码的图片字符串
        """
        fig, ax = plt.subplots(figsize=(14, 6))

        # 策略净值曲线（归一化）
        equity = self.metrics.get_equity_curve_normalized()
        if equity is not None and len(equity) > 0:
            ax.plot(equity.index, equity.values,
                    label=f'策略 ({self.strategy_name})',
                    color='#2196F3', linewidth=1.5)

        # 基准净值曲线（归一化）
        benchmark = self.metrics.get_benchmark_curve_normalized()
        if benchmark is not None and len(benchmark) > 0:
            # 对齐日期索引
            common_idx = equity.index.intersection(benchmark.index)
            if len(common_idx) > 0:
                ax.plot(common_idx, benchmark.loc[common_idx].values,
                        label='基准', color='#FF9800',
                        linewidth=1.5, alpha=0.8)

        ax.set_title('净值曲线 (归一化)', fontsize=14, fontweight='bold')
        ax.set_xlabel('日期', fontsize=11)
        ax.set_ylabel('净值', fontsize=11)
        ax.legend(fontsize=10, loc='best')
        ax.grid(True, alpha=0.3)
        ax.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5)

        # 格式化x轴日期
        fig.autofmt_xdate(rotation=30)

        return self._fig_to_base64(fig)

    def _generate_drawdown_plot(self) -> str:
        """
        生成回撤曲线图

        返回:
            base64 编码的图片字符串
        """
        fig, ax = plt.subplots(figsize=(14, 4))

        drawdown = self.metrics.results.get('drawdown_series')
        if drawdown is not None and len(drawdown) > 0:
            # 填充回撤区域
            ax.fill_between(drawdown.index, drawdown.values * 100, 0,
                            color='#F44336', alpha=0.3)
            ax.plot(drawdown.index, drawdown.values * 100,
                    color='#F44336', linewidth=1)

        ax.set_title('回撤曲线', fontsize=14, fontweight='bold')
        ax.set_xlabel('日期', fontsize=11)
        ax.set_ylabel('回撤 (%)', fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='black', linewidth=0.5)

        fig.autofmt_xdate(rotation=30)

        return self._fig_to_base64(fig)

    def _generate_monthly_returns_heatmap(self) -> str:
        """
        生成月度收益率热力图

        返回:
            base64 编码的图片字符串
        """
        monthly = self.metrics.results.get('monthly_returns')

        fig, ax = plt.subplots(figsize=(12, max(4, len(monthly) * 0.8 + 2)))

        if monthly is not None and not monthly.empty:
            # 转换为百分比
            data = monthly.values * 100

            # 创建热力图
            im = ax.imshow(data, cmap='RdYlGn', aspect='auto',
                          vmin=-10, vmax=10, interpolation='nearest')

            # 设置坐标轴标签
            ax.set_xticks(np.arange(len(monthly.columns)))
            ax.set_xticklabels([f'{int(m)}月' for m in monthly.columns])
            ax.set_yticks(np.arange(len(monthly.index)))
            ax.set_yticklabels(monthly.index)

            # 在每个格子中添加数值标注
            for i in range(len(monthly.index)):
                for j in range(len(monthly.columns)):
                    val = data[i, j]
                    if not np.isnan(val):
                        # 根据数值大小选择文字颜色
                        text_color = 'white' if abs(val) > 6 else 'black'
                        ax.text(j, i, f'{val:.1f}%',
                               ha='center', va='center',
                               color=text_color, fontsize=9)

            ax.set_title('月度收益率热力图 (%)', fontsize=14, fontweight='bold')
            fig.colorbar(im, ax=ax, label='收益率 (%)', shrink=0.8)
        else:
            ax.text(0.5, 0.5, '无月度收益率数据',
                   ha='center', va='center', fontsize=14)
            ax.set_axis_off()

        return self._fig_to_base64(fig)

    def _generate_metrics_table_html(self) -> str:
        """
        生成绩效指标汇总表 HTML

        返回:
            HTML 表格字符串
        """
        r = self.metrics.results

        def fmt_pct(val):
            """格式化百分比"""
            if val == float('inf'):
                return '∞'
            if val == float('-inf'):
                return '-∞'
            return f'{val:.2%}'

        def fmt_num(val, decimals=4):
            """格式化数字"""
            if val == float('inf'):
                return '∞'
            if val == float('-inf'):
                return '-∞'
            return f'{val:.{decimals}f}'

        rows = [
            ('初始资金', f'{r.get("initial_capital", 0):,.2f}'),
            ('期末净值', f'{r.get("final_equity", 0):,.2f}'),
            ('总收益率', fmt_pct(r.get('total_return', 0))),
            ('年化收益率', fmt_pct(r.get('annual_return', 0))),
            ('年化波动率', fmt_pct(r.get('annual_volatility', 0))),
            ('夏普比率', fmt_num(r.get('sharpe_ratio', 0))),
            ('Sortino比率', fmt_num(r.get('sortino_ratio', 0))),
            ('最大回撤', fmt_pct(r.get('max_drawdown', 0))),
            ('Calmar比率', fmt_num(r.get('calmar_ratio', 0))),
            ('总交易次数', f'{r.get("total_trades", 0)}'),
            ('胜率', fmt_pct(r.get('win_rate', 0))),
            ('盈亏比', fmt_num(r.get('profit_loss_ratio', 0))),
            ('平均持仓天数', f'{r.get("avg_holding_days", 0):.1f}'),
            ('平均盈利', f'{r.get("avg_profit", 0):,.2f}'),
            ('平均亏损', f'{r.get("avg_loss", 0):,.2f}'),
            ('最大单笔盈利', f'{r.get("max_profit", 0):,.2f}'),
            ('最大单笔亏损', f'{r.get("max_loss", 0):,.2f}'),
        ]

        html = '<table class="metrics-table">\n'
        html += '<thead><tr><th>指标</th><th>数值</th></tr></thead>\n<tbody>\n'
        for name, value in rows:
            # 根据正负值设置颜色
            color = ''
            if '%' in value or ',' in value:
                pass
            html += f'<tr><td>{name}</td><td style="text-align:right;font-weight:bold;">{value}</td></tr>\n'
        html += '</tbody></table>\n'

        return html

    def _generate_trades_table_html(self) -> str:
        """
        生成交易明细表 HTML

        返回:
            HTML 表格字符串
        """
        trades = self.portfolio.trades
        if not trades:
            return '<p style="text-align:center;color:#888;">无交易记录</p>'

        html = '<table class="trades-table">\n'
        html += '<thead><tr>'
        html += '<th>日期</th><th>股票代码</th><th>方向</th>'
        html += '<th>数量</th><th>成交价</th><th>成交金额</th>'
        html += '<th>手续费</th><th>滑点成本</th>'
        html += '</tr></thead>\n<tbody>\n'

        for trade in trades:
            date_str = trade.timestamp.strftime('%Y-%m-%d') if hasattr(trade.timestamp, 'strftime') else str(trade.timestamp)
            direction_class = 'buy' if trade.direction == 'BUY' else 'sell'
            direction_text = '买入' if trade.direction == 'BUY' else '卖出'
            html += f'<tr>'
            html += f'<td>{date_str}</td>'
            html += f'<td>{trade.symbol}</td>'
            html += f'<td class="{direction_class}">{direction_text}</td>'
            html += f'<td>{trade.quantity:,}</td>'
            html += f'<td>{trade.fill_price:.2f}</td>'
            html += f'<td>{trade.trade_value:,.2f}</td>'
            html += f'<td>{trade.commission:.2f}</td>'
            html += f'<td>{trade.slippage_cost:.2f}</td>'
            html += '</tr>\n'

        html += '</tbody></table>\n'

        # 添加交易统计
        html += f'<p style="margin-top:10px;color:#666;">共 {len(trades)} 笔交易</p>'

        return html

    def _generate_brinson_table_html(self) -> str:
        """
        生成 Brinson 归因分析表 HTML

        返回:
            HTML 表格字符串，或空字符串（如果无基准数据）
        """
        brinson = self.metrics.results.get('brinson_attribution')
        if brinson is None:
            return ''

        html = '<h3>Brinson 归因分析</h3>\n'
        html += '<table class="metrics-table">\n'
        html += '<thead><tr><th>指标</th><th>数值</th></tr></thead>\n<tbody>\n'
        html += f'<tr><td>组合收益率</td><td style="text-align:right;">{brinson["portfolio_return"]:.4%}</td></tr>\n'
        html += f'<tr><td>基准收益率</td><td style="text-align:right;">{brinson["benchmark_return"]:.4%}</td></tr>\n'
        html += f'<tr><td>超额收益</td><td style="text-align:right;font-weight:bold;">{brinson["excess_return"]:.4%}</td></tr>\n'
        html += f'<tr><td>配置效应</td><td style="text-align:right;">{brinson["allocation_effect"]:.4%}</td></tr>\n'
        html += f'<tr><td>选择效应</td><td style="text-align:right;">{brinson["selection_effect"]:.4%}</td></tr>\n'
        html += f'<tr><td>交互效应</td><td style="text-align:right;">{brinson["interaction_effect"]:.4%}</td></tr>\n'
        html += '</tbody></table>\n'

        # 明细表
        if brinson.get('detail'):
            html += '<h4>各标的归因明细</h4>\n'
            html += '<table class="trades-table">\n'
            html += '<thead><tr>'
            html += '<th>股票代码</th><th>组合权重</th><th>基准权重</th>'
            html += '<th>组合收益率</th><th>基准收益率</th>'
            html += '<th>配置效应</th><th>选择效应</th><th>交互效应</th>'
            html += '</tr></thead>\n<tbody>\n'
            for d in brinson['detail']:
                html += f'<tr>'
                html += f'<td>{d["symbol"]}</td>'
                html += f'<td>{d["portfolio_weight"]:.2%}</td>'
                html += f'<td>{d["benchmark_weight"]:.2%}</td>'
                html += f'<td>{d["portfolio_return"]:.2%}</td>'
                html += f'<td>{d["benchmark_return"]:.2%}</td>'
                html += f'<td>{d["allocation_effect"]:.4%}</td>'
                html += f'<td>{d["selection_effect"]:.4%}</td>'
                html += f'<td>{d["interaction_effect"]:.4%}</td>'
                html += '</tr>\n'
            html += '</tbody></table>\n'

        return html

    def _generate_css(self) -> str:
        """生成 CSS 样式"""
        return """
        <style>
            body {
                font-family: 'Microsoft YaHei', 'SimHei', Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
                color: #333;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background-color: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #1a237e;
                border-bottom: 3px solid #1a237e;
                padding-bottom: 10px;
                font-size: 24px;
            }
            h2 {
                color: #283593;
                margin-top: 30px;
                font-size: 20px;
                border-left: 4px solid #3f51b5;
                padding-left: 10px;
            }
            h3 {
                color: #37474f;
                margin-top: 20px;
                font-size: 16px;
            }
            h4 {
                color: #455a64;
                margin-top: 15px;
                font-size: 14px;
            }
            .header-info {
                background-color: #e8eaf6;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
            }
            .header-info p {
                margin: 5px 0;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 15px 0;
                font-size: 13px;
            }
            .metrics-table th {
                background-color: #3f51b5;
                color: white;
                padding: 10px;
                text-align: left;
            }
            .metrics-table td {
                padding: 8px 10px;
                border-bottom: 1px solid #e0e0e0;
            }
            .metrics-table tr:nth-child(even) {
                background-color: #f5f5f5;
            }
            .trades-table th {
                background-color: #455a64;
                color: white;
                padding: 8px;
                text-align: center;
            }
            .trades-table td {
                padding: 6px 8px;
                border-bottom: 1px solid #e0e0e0;
                text-align: center;
            }
            .trades-table tr:nth-child(even) {
                background-color: #f5f5f5;
            }
            .trades-table .buy {
                color: #d32f2f;
                font-weight: bold;
            }
            .trades-table .sell {
                color: #388e3c;
                font-weight: bold;
            }
            .chart-container {
                text-align: center;
                margin: 20px 0;
            }
            .chart-container img {
                max-width: 100%;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
            }
            .footer {
                margin-top: 30px;
                padding-top: 15px;
                border-top: 1px solid #e0e0e0;
                text-align: center;
                color: #999;
                font-size: 12px;
            }
        </style>
        """

    def generate(self, output_path: str) -> str:
        """
        生成完整的 HTML 报告

        参数:
            output_path: 输出文件路径

        返回:
            报告文件路径
        """
        print("[报告] 正在生成图表...")

        # 生成图表
        equity_curve_img = self._generate_equity_curve_plot()
        drawdown_img = self._generate_drawdown_plot()
        monthly_heatmap_img = self._generate_monthly_returns_heatmap()

        print("[报告] 正在生成HTML...")

        # 生成 HTML 内容
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>回测报告 - {self.strategy_name}</title>
    {self._generate_css()}
</head>
<body>
<div class="container">
    <h1>事件驱动回测报告</h1>

    <div class="header-info">
        <p><strong>策略名称:</strong> {self.strategy_name}</p>
        <p><strong>回测标的:</strong> {', '.join(self.tickers)}</p>
        <p><strong>回测区间:</strong> {self.start_date} ~ {self.end_date}</p>
        <p><strong>报告生成时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <h2>绩效指标汇总</h2>
    {self._generate_metrics_table_html()}

    <h2>净值曲线</h2>
    <div class="chart-container">
        <img src="data:image/png;base64,{equity_curve_img}" alt="净值曲线">
    </div>

    <h2>回撤曲线</h2>
    <div class="chart-container">
        <img src="data:image/png;base64,{drawdown_img}" alt="回撤曲线">
    </div>

    <h2>月度收益率热力图</h2>
    <div class="chart-container">
        <img src="data:image/png;base64,{monthly_heatmap_img}" alt="月度收益率热力图">
    </div>

    {self._generate_brinson_table_html()}

    <h2>交易明细</h2>
    {self._generate_trades_table_html()}

    <div class="footer">
        <p>本报告由事件驱动回测引擎 (Event-Driven Backtest Engine) 自动生成</p>
        <p>数据来源: akshare | 仅供学习研究使用，不构成投资建议</p>
    </div>
</div>
</body>
</html>"""

        # 确保输出目录存在
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"[报告] 报告已保存至: {output_path}")
        return output_path
