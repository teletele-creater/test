#!/usr/bin/env python3
"""
オプション取引アラートシステム - メインエントリーポイント

レポート分析に基づく最も再現性の高い戦略（SPYブルプットスプレッド）を中心に、
IV Rank・VIX等の指標ドリブン条件を監視し、エントリーチャンスが来たら通知する。

使い方:
    # 1回スキャン（即時実行）
    python main.py scan

    # 定期スキャン（30分間隔）
    python main.py watch

    # 現在の市場データを表示
    python main.py status

    # テスト通知を送信
    python main.py test-notify
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime

import schedule
from dotenv import load_dotenv

from config import WATCHLIST
from market_data import get_market_snapshot
from notifier import Notifier
from strategy_checker import get_triggered_signals, scan_all_strategies

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("options-alert")


def run_scan(notifier: Notifier, symbols: list[str] | None = None) -> None:
    """全銘柄をスキャンしてシグナルをチェック"""
    if symbols is None:
        symbols = WATCHLIST["us_etfs"]

    logger.info(f"Starting scan at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n{'#'*60}")
    print(f"  Options Alert Scan - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}\n")

    all_signals = []

    for symbol in symbols:
        try:
            snapshot = get_market_snapshot(symbol)
            signals = scan_all_strategies(snapshot)
            all_signals.extend(signals)
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")
            continue

    notifier.send_status_report(all_signals)

    triggered = [s for s in all_signals if s.is_triggered]
    if triggered:
        print(f"\n*** {len(triggered)} ENTRY SIGNAL(S) DETECTED ***\n")
    else:
        print("\nNo entry signals at this time. Monitoring continues...\n")


def run_status(symbols: list[str] | None = None) -> None:
    """現在の市場データとインジケーター値を表示"""
    if symbols is None:
        symbols = WATCHLIST["us_etfs"]

    print(f"\n{'='*60}")
    print(f"  Market Status - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    for symbol in symbols:
        try:
            snapshot = get_market_snapshot(symbol)
            print(f"--- {symbol} ---")
            print(f"  Price:      ${snapshot.price:.2f}")
            print(f"  VIX:        {snapshot.vix:.1f}")
            print(f"  IV (est):   {snapshot.iv_current:.1f}%")
            print(f"  IV Rank:    {snapshot.iv_rank:.1f}%")
            print(f"  IV %ile:    {snapshot.iv_percentile:.1f}%")
            print(f"  HV(20):     {snapshot.hv_20:.1f}%")
            print(f"  IV/HV:      {snapshot.iv_hv_ratio:.2f}")
            print(f"  RSI(14):    {snapshot.rsi:.1f}")
            print(f"  50-day MA:  ${snapshot.ma_50:.2f} {'<-- near' if snapshot.near_50ma else ''}")
            print(f"  200-day MA: ${snapshot.ma_200:.2f} {'<-- near' if snapshot.near_200ma else ''}")
            print(f"  VIX declining: {'Yes' if snapshot.vix_declining else 'No'}")
            if snapshot.put_call_ratio_sma is not None:
                print(f"  P/C Ratio (est): {snapshot.put_call_ratio_sma:.2f}")
            print()
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")


def run_watch(notifier: Notifier, interval_minutes: int = 30) -> None:
    """定期的にスキャンを実行"""
    logger.info(f"Starting watch mode. Scanning every {interval_minutes} minutes.")
    print(f"\nOptions Alert System - Watch Mode")
    print(f"Scan interval: {interval_minutes} minutes")
    print(f"Monitoring: {', '.join(WATCHLIST['us_etfs'])}")
    print(f"Press Ctrl+C to stop.\n")

    # 初回は即座に実行
    run_scan(notifier)

    # 定期実行をスケジュール
    schedule.every(interval_minutes).minutes.do(run_scan, notifier=notifier)

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nWatch mode stopped.")
        logger.info("Watch mode stopped by user.")


def main():
    parser = argparse.ArgumentParser(
        description="Options Trading Alert System - IV Rank driven entry signals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py scan              # Run one-time scan
  python main.py watch             # Watch mode (default: 30min interval)
  python main.py watch -i 15       # Watch mode with 15min interval
  python main.py status            # Show current market data
  python main.py status -s SPY QQQ # Status for specific symbols
  python main.py test-notify       # Send test notification
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Run one-time scan for entry signals")
    scan_parser.add_argument("-s", "--symbols", nargs="+", help="Symbols to scan (default: SPY, IWM, QQQ)")

    # watch
    watch_parser = subparsers.add_parser("watch", help="Continuous monitoring mode")
    watch_parser.add_argument(
        "-i", "--interval",
        type=int,
        default=int(os.getenv("SCAN_INTERVAL_MINUTES", "30")),
        help="Scan interval in minutes (default: 30)",
    )

    # status
    status_parser = subparsers.add_parser("status", help="Show current market indicators")
    status_parser.add_argument("-s", "--symbols", nargs="+", help="Symbols to check")

    # test-notify
    subparsers.add_parser("test-notify", help="Send test notification to all channels")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    notifier = Notifier()

    if args.command == "scan":
        run_scan(notifier, args.symbols)
    elif args.command == "watch":
        run_watch(notifier, args.interval)
    elif args.command == "status":
        run_status(args.symbols)
    elif args.command == "test-notify":
        notifier.send_test()


if __name__ == "__main__":
    main()
