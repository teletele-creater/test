#!/usr/bin/env python3
"""
株式スクリーニング自動スキャン＆通知

1489 ETF構成48銘柄を定期スクリーニングし、
エントリーシグナル検出時にLINE/Slackへ通知する。

使い方:
    # 通常スキャン（シグナルがあれば通知）
    python scan_and_notify.py

    # テスト通知（接続確認）
    python scan_and_notify.py --test

    # ドライラン（通知せずに結果だけ表示）
    python scan_and_notify.py --dry-run

    # パラメータ指定
    python scan_and_notify.py --peg 0.75 --yield-pct 15 --per-pct 30

環境変数:
    LINE_CHANNEL_ACCESS_TOKEN  LINE Messaging API トークン
    LINE_USER_ID               LINE 送信先ユーザーID
    SLACK_WEBHOOK_URL          Slack Webhook URL
    DISCORD_WEBHOOK_URL        Discord Webhook URL
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("screener-notify")


# ============================================================
# 通知フォーマッター
# ============================================================

def format_signal_message(result) -> str:
    """エントリーシグナルの通知メッセージを生成"""
    lines = [
        f"🎯 エントリーシグナル検出",
        f"",
        f"銘柄: {result.name} ({result.symbol})",
        f"セクター: {result.sector}",
        f"ルール達成: {result.rules_passed}/{result.rules_total}",
        f"──────────────────",
    ]

    for r in result.rules:
        mark = "✅" if r.passed else "❌"
        lines.append(f"{mark} {r.rule_name}")
        lines.append(f"   {r.current_value} (基準: {r.threshold})")
        if r.detail:
            # 長すぎるdetailは短縮
            detail = r.detail if len(r.detail) < 80 else r.detail[:77] + "..."
            lines.append(f"   {detail}")
        for w in r.warnings:
            lines.append(f"   ⚠️ {w}")

    lines.append(f"──────────────────")
    lines.append(f"検出時刻: {result.timestamp.strftime('%Y-%m-%d %H:%M')}")

    return "\n".join(lines)


def format_daily_summary(results, entry_results) -> str:
    """日次サマリーメッセージを生成"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"📊 株式スクリーニング日次レポート",
        f"日時: {now}",
        f"対象: 1489 ETF構成 {len(results)}銘柄",
        f"",
    ]

    if entry_results:
        lines.append(f"🎯 エントリーシグナル: {len(entry_results)}銘柄")
        lines.append(f"──────────────────")
        for r in entry_results:
            # 各ルールの結果を1行で
            marks = "".join("✅" if rule.passed else "❌" for rule in r.rules)
            lines.append(f"  {r.name} ({r.symbol})")
            lines.append(f"  {marks} {r.rules_passed}/{r.rules_total}")
            # 主要数値を抽出して表示
            for rule in r.rules:
                if rule.passed:
                    lines.append(f"    {rule.rule_name}: {rule.current_value}")
            lines.append("")
    else:
        lines.append("シグナルなし。引き続き監視中。")
        lines.append("")

    # 条件に近い銘柄（2/3以上のルール達成）
    near_miss = [r for r in results if not r.is_entry_zone and r.rules_passed >= 2]
    if near_miss:
        lines.append(f"👀 ニアミス（{len(near_miss)}銘柄）:")
        for r in near_miss[:5]:  # 最大5つ
            marks = "".join("✅" if rule.passed else "❌" for rule in r.rules)
            lines.append(f"  {r.name} ({r.symbol}) {marks}")
        if len(near_miss) > 5:
            lines.append(f"  ...他{len(near_miss) - 5}銘柄")

    return "\n".join(lines)


# ============================================================
# 通知送信
# ============================================================

class ScreenerNotifier:
    """株スクリーナー専用通知クラス"""

    def __init__(self):
        self.line_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        self.line_user_id = os.getenv("LINE_USER_ID")
        self.slack_url = os.getenv("SLACK_WEBHOOK_URL")
        self.discord_url = os.getenv("DISCORD_WEBHOOK_URL")

        self.channels = []
        if self.line_token and self.line_user_id:
            self.channels.append("LINE")
        if self.slack_url:
            self.channels.append("Slack")
        if self.discord_url:
            self.channels.append("Discord")

        if self.channels:
            logger.info(f"通知チャネル: {', '.join(self.channels)}")
        else:
            logger.warning("通知チャネル未設定。コンソール出力のみ。")
            logger.warning("LINE: LINE_CHANNEL_ACCESS_TOKEN + LINE_USER_ID を設定")
            logger.warning("Slack: SLACK_WEBHOOK_URL を設定")

    def send(self, message: str, title: str = "") -> None:
        """全チャネルに送信"""
        print(message)

        if self.line_token and self.line_user_id:
            self._send_line(message)
        if self.slack_url:
            self._send_slack(message, title)
        if self.discord_url:
            self._send_discord(message, title)

    def _send_line(self, message: str) -> None:
        """LINE Messaging APIでプッシュ送信"""
        try:
            resp = requests.post(
                "https://api.line.me/v2/bot/message/push",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.line_token}",
                },
                json={
                    "to": self.line_user_id,
                    "messages": [{"type": "text", "text": message[:5000]}],
                },
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("LINE送信完了")
        except Exception as e:
            logger.error(f"LINE送信失敗: {e}")

    def _send_slack(self, message: str, title: str = "") -> None:
        """Slack Webhook送信"""
        try:
            header = f"*{title}*\n" if title else ""
            resp = requests.post(
                self.slack_url,
                json={
                    "text": f"{header}{message[:3000]}",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"{header}```{message[:2900]}```",
                            },
                        }
                    ],
                },
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("Slack送信完了")
        except Exception as e:
            logger.error(f"Slack送信失敗: {e}")

    def _send_discord(self, message: str, title: str = "") -> None:
        """Discord Webhook送信"""
        try:
            header = f"**{title}**\n" if title else ""
            resp = requests.post(
                self.discord_url,
                json={"content": f"{header}```\n{message[:1900]}\n```"},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("Discord送信完了")
        except Exception as e:
            logger.error(f"Discord送信失敗: {e}")

    def send_test(self) -> None:
        """テスト通知"""
        msg = (
            "🔔 株式スクリーナー通知テスト\n\n"
            "このメッセージが届いていれば通知設定は正常です。\n"
            f"チャネル: {', '.join(self.channels) or 'なし'}\n"
            f"送信時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.send(msg, title="通知テスト")


# ============================================================
# スキャン実行
# ============================================================

def run_scan(rules, dry_run: bool = False) -> int:
    """スクリーニング実行＆通知"""
    from screener_config import SCREENING_WATCHLIST
    from stock_screener import print_screening_report, screen_stocks

    notifier = ScreenerNotifier()

    logger.info(f"スキャン開始: {len(SCREENING_WATCHLIST)}銘柄")

    results = screen_stocks(SCREENING_WATCHLIST, rules)
    entry_results = [r for r in results if r.is_entry_zone]

    # コンソールにレポート表示
    print_screening_report(results)

    if dry_run:
        logger.info("ドライランモード: 通知はスキップ")
        if entry_results:
            print(f"\n[ドライラン] {len(entry_results)}件のシグナルを検出（通知なし）")
        return 0

    # シグナルがあれば個別通知
    if entry_results:
        logger.info(f"🎯 {len(entry_results)}件のエントリーシグナル検出！")
        for result in entry_results:
            msg = format_signal_message(result)
            notifier.send(msg, title=f"🎯 {result.name} ({result.symbol}) エントリーシグナル")

    # 日次サマリー（シグナルの有無に関わらず送信）
    summary = format_daily_summary(results, entry_results)
    notifier.send(summary, title="📊 日次スクリーニングレポート")

    logger.info(f"スキャン完了: {len(entry_results)}/{len(results)}銘柄がシグナル")
    return len(entry_results)


# ============================================================
# メイン
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="株式スクリーニング自動スキャン＆通知（1489 ETF構成銘柄）",
    )
    parser.add_argument("--test", action="store_true", help="テスト通知を送信")
    parser.add_argument("--dry-run", action="store_true", help="通知せずに結果だけ表示")
    parser.add_argument("--peg", type=float, default=1.0, help="PEGしきい値 (default: 1.0)")
    parser.add_argument("--yield-pct", type=float, default=20.0, help="利回り上位%% (default: 20)")
    parser.add_argument("--per-pct", type=float, default=30.0, help="PER下位%% (default: 30)")
    args = parser.parse_args()

    if args.test:
        notifier = ScreenerNotifier()
        notifier.send_test()
        return 0

    from screener_config import ScreeningRules

    rules = ScreeningRules(
        peg_threshold=args.peg,
        yield_top_percentile=args.yield_pct,
        per_bottom_percentile=args.per_pct,
    )

    signal_count = run_scan(rules, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
