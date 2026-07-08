#!/usr/bin/env python3
"""
事件驱动回测引擎 - CLI入口
============================

使用方法:
    python backtest.py --tickers 600519,000858 --strategy ma_cross --start 20230101 --end 20250101

参数说明:
    --tickers    股票代码，逗号分隔（必填）
    --strategy   策略类型: ma_cross, rsi, bollinger（默认 ma_cross）
    --start      开始日期，YYYYMMDD 格式（必填）
    --end        结束日期，YYYYMMDD 格式（必填）
    --capital    初始资金，默认 1000000
    --slippage   滑点比例，默认 0.001
    --commission 佣金费率，默认 0.0003
    --output     输出目录，默认 output

示例:
    # 均线交叉策略回测贵州茅台和五粮液
    python backtest.py --tickers 600519,000858 --strategy ma_cross --start 20230101 --end 20250101

    # RSI策略回测
    python backtest.py --tickers 600519 --strategy rsi --start 20230101 --end 20250101 --capital 500000

    # 布林带策略回测
    python backtest.py --tickers 000858 --strategy bollinger --start 20230101 --end 20250101
"""

import argparse
import os
import sys
from queue import Queue

# 使用 rich 库显示进度和美化输出
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.table import Table

# 导入回测引擎组件
from backtest_engine import (
    EventType, MarketEvent, SignalEvent, OrderEvent, FillEvent,
    HistoricalDataHandler, Portfolio, SimulatedBroker,
    PerformanceMetrics, HTMLReport,
)
from backtest_engine.strategy import (
    MovingAverageCrossStrategy, RSIStrategy, BollingerBandStrategy,
)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='事件驱动回测引擎 - 专业级量化回测框架',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python backtest.py --tickers 600519,000858 --strategy ma_cross --start 20230101 --end 20250101
  python backtest.py --tickers 600519 --strategy rsi --start 20230101 --end 20250101 --capital 500000
  python backtest.py --tickers 000858 --strategy bollinger --start 20230101 --end 20250101
        """,
    )
    parser.add_argument(
        '--tickers', type=str, required=True,
        help='股票代码，逗号分隔（如 600519,000858）',
    )
    parser.add_argument(
        '--strategy', type=str, default='ma_cross',
        choices=['ma_cross', 'rsi', 'bollinger'],
        help='策略类型: ma_cross(均线交叉), rsi(RSI), bollinger(布林带)',
    )
    parser.add_argument(
        '--start', type=str, required=True,
        help='开始日期，YYYYMMDD 格式',
    )
    parser.add_argument(
        '--end', type=str, required=True,
        help='结束日期，YYYYMMDD 格式',
    )
    parser.add_argument(
        '--capital', type=float, default=1000000.0,
        help='初始资金（默认 1000000）',
    )
    parser.add_argument(
        '--slippage', type=float, default=0.001,
        help='滑点比例（默认 0.001 即 0.1%）',
    )
    parser.add_argument(
        '--commission', type=float, default=0.0003,
        help='佣金费率（默认 0.0003 即万三）',
    )
    parser.add_argument(
        '--output', type=str, default='output',
        help='输出目录（默认 output）',
    )
    return parser.parse_args()


def create_strategy(strategy_name, data_handler, events_queue):
    """
    根据策略名称创建策略实例

    参数:
        strategy_name: 策略名称 (ma_cross / rsi / bollinger)
        data_handler: 数据处理器
        events_queue: 事件队列

    返回:
        策略实例
    """
    if strategy_name == 'ma_cross':
        return MovingAverageCrossStrategy(
            data_handler, events_queue,
            short_window=5, long_window=20,
        )
    elif strategy_name == 'rsi':
        return RSIStrategy(
            data_handler, events_queue,
            rsi_period=14, oversold=30, overbought=70,
        )
    elif strategy_name == 'bollinger':
        return BollingerBandStrategy(
            data_handler, events_queue,
            window=20, num_std=2.0,
        )
    else:
        raise ValueError(f"未知策略: {strategy_name}")


def run_backtest(args, console: Console):
    """
    执行回测

    参数:
        args: 命令行参数
        console: rich Console 实例

    返回:
        (metrics, portfolio, strategy, data_handler) 元组
    """
    # 解析股票代码
    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]

    # 策略名称映射
    strategy_display = {
        'ma_cross': '均线交叉 (MA Cross)',
        'rsi': 'RSI超买超卖 (RSI)',
        'bollinger': '布林带突破 (Bollinger Band)',
    }

    # 显示回测参数
    param_table = Table(title="回测参数", show_header=True, header_style="bold blue")
    param_table.add_column("参数", style="cyan")
    param_table.add_column("值", style="green")
    param_table.add_row("股票代码", ', '.join(tickers))
    param_table.add_row("策略", strategy_display.get(args.strategy, args.strategy))
    param_table.add_row("回测区间", f"{args.start} ~ {args.end}")
    param_table.add_row("初始资金", f"{args.capital:,.2f}")
    param_table.add_row("滑点比例", f"{args.slippage:.4%}")
    param_table.add_row("佣金费率", f"{args.commission:.4%}")
    console.print(param_table)

    # ========== 初始化事件驱动组件 ==========
    console.print("\n[bold cyan]初始化回测引擎...[/bold cyan]")

    # 创建事件队列
    events_queue = Queue()

    # 创建数据处理器（从akshare加载历史数据）
    console.print("[yellow]正在从 akshare 加载历史数据...[/yellow]")
    data_handler = HistoricalDataHandler(
        events_queue=events_queue,
        tickers=tickers,
        start_date=args.start,
        end_date=args.end,
        adjust="qfq",  # 前复权
    )

    # 创建策略
    strategy = create_strategy(args.strategy, data_handler, events_queue)
    console.print(f"[green]策略已加载: {strategy.name}[/green]")

    # 创建组合管理器
    portfolio = Portfolio(
        data_handler=data_handler,
        events_queue=events_queue,
        start_date=args.start,
        initial_capital=args.capital,
    )

    # 创建模拟券商
    broker = SimulatedBroker(
        events_queue=events_queue,
        data_handler=data_handler,
        slippage=args.slippage,
        commission_rate=args.commission,
    )

    # ========== 运行事件驱动回测循环 ==========
    total_bars = data_handler.get_data_count()
    console.print(f"\n[bold cyan]开始回测（共 {total_bars} 个交易日）...[/bold cyan]")

    processed_bars = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("回测进度", total=total_bars)

        # 事件驱动主循环
        while data_handler.continue_backtest:
            # 1. 推送下一根K线数据（生成 MarketEvent）
            data_handler.update_bars()

            # 2. 处理事件队列中的所有事件
            while not events_queue.empty():
                event = events_queue.get()

                if event.type == EventType.MARKET:
                    # 市场数据到达：策略计算信号 + 组合更新市值
                    strategy.calculate_signals(event)
                    portfolio.update_timeindex(event)
                    processed_bars += 1
                    progress.update(task, completed=processed_bars)

                elif event.type == EventType.SIGNAL:
                    # 策略信号：组合生成订单
                    portfolio.update_signal(event)

                elif event.type == EventType.ORDER:
                    # 订单：券商执行
                    broker.execute_order(event)

                elif event.type == EventType.FILL:
                    # 成交回报：组合更新持仓和现金流
                    portfolio.update_fill(event)

    console.print("[bold green]回测完成！[/bold green]")

    # ========== 计算绩效指标 ==========
    console.print("\n[bold cyan]计算绩效指标...[/bold cyan]")

    # 获取基准数据（使用第一只股票作为简单基准）
    benchmark_data = None
    if tickers:
        benchmark_df = data_handler.get_ticker_data(tickers[0])
        if benchmark_df is not None and not benchmark_df.empty:
            benchmark_data = benchmark_df[['close']].copy()
            benchmark_data.columns = [tickers[0]]

    # 创建绩效指标计算器
    metrics = PerformanceMetrics(
        all_holdings=portfolio.all_holdings,
        trades=portfolio.trades,
        benchmark_data=benchmark_data,
        initial_capital=args.capital,
    )
    metrics.calculate_all()

    # 显示绩效指标
    console.print(Panel(metrics.format_results(), title="绩效指标"))

    # 显示券商统计
    broker_stats = broker.get_stats()
    stats_table = Table(title="交易成本统计", show_header=True, header_style="bold magenta")
    stats_table.add_column("项目", style="cyan")
    stats_table.add_column("金额 (元)", style="yellow", justify="right")
    stats_table.add_row("累计手续费", f"{broker_stats['total_commission']:,.2f}")
    stats_table.add_row("累计滑点成本", f"{broker_stats['total_slippage_cost']:,.2f}")
    console.print(stats_table)

    return metrics, portfolio, strategy, data_handler


def generate_report(metrics, portfolio, strategy, data_handler, args, console: Console):
    """
    生成HTML回测报告

    参数:
        metrics: 绩效指标
        portfolio: 组合管理器
        strategy: 策略实例
        data_handler: 数据处理器
        args: 命令行参数
        console: rich Console
    """
    console.print("\n[bold cyan]生成HTML报告...[/bold cyan]")

    # 创建报告生成器
    report = HTMLReport(
        metrics=metrics,
        portfolio=portfolio,
        strategy_name=strategy.name,
        tickers=[t.strip() for t in args.tickers.split(',')],
        start_date=args.start,
        end_date=args.end,
    )

    # 确保输出目录存在
    os.makedirs(args.output, exist_ok=True)

    # 生成报告
    report_filename = f"backtest_report_{strategy.name}_{args.start}_{args.end}.html"
    report_path = os.path.join(args.output, report_filename)
    report.generate(report_path)

    console.print(f"\n[bold green]报告已生成: {os.path.abspath(report_path)}[/bold green]")


def main():
    """主函数"""
    console = Console()

    # 打印标题
    console.print(Panel.fit(
        "[bold blue]事件驱动回测引擎[/bold blue]\n"
        "[dim]Event-Driven Backtest Engine v1.0.0[/dim]\n"
        "[dim]数据来源: akshare | 仅供学习研究使用[/dim]",
        border_style="blue",
    ))

    # 解析命令行参数
    args = parse_args()

    try:
        # 运行回测
        metrics, portfolio, strategy, data_handler = run_backtest(args, console)

        # 生成报告
        generate_report(metrics, portfolio, strategy, data_handler, args, console)

        console.print("\n[bold green]回测全部完成！[/bold green]")

    except KeyboardInterrupt:
        console.print("\n[bold red]用户中断回测[/bold red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]回测出错: {e}[/bold red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    main()
