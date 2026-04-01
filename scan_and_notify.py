#!/usr/bin/env python3
"""
株式スクリーニング自動スキャン＆通知

1489 ETF構成48銘柄を定期スクリーニングし、
エントリーシグナル検出時にLINE/Slackへ通知する。

通知レベル:
  🎯 シグナル確定 — 全ルール達成。買い検討。
  👀 ニアミス     — あと1条件。毎日監視。
  📊 週次サマリー — 全銘柄の状況俯瞰。

使い方:
    python scan_and_notify.py              # 日次スキャン（確定+ニアミス通知）
    python scan_and_notify.py --weekly     # 週次サマリー
    python scan_and_notify.py --test       # 接続テスト
    python scan_and_notify.py --dry-run    # 通知なしで結果表示

環境変数:
    SLACK_WEBHOOK_URL          Slack Webhook URL
    LINE_CHANNEL_ACCESS_TOKEN  LINE Messaging API トークン（任意）
    LINE_USER_ID               LINE 送信先ユーザーID（任意）
    DISCORD_WEBHOOK_URL        Discord Webhook URL（任意）
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
# 「あと何が足りないか」の解析
# ============================================================

RULE_SHORT_NAMES = {
    "①": "利回り",
    "②": "成長/PEG",
    "③": "PER割安",
    "④": "底打ち",
}


def _rule_short_name(rule_name: str) -> str:
    """ルール名から短縮名を取得"""
    for key, short in RULE_SHORT_NAMES.items():
        if key in rule_name:
            return short
    return rule_name[:10]


def analyze_missing_conditions(result) -> list[str]:
    """
    未達ルールごとに「あと何が起きれば達成するか」を日本語で返す。
    通知メッセージ内で「確定までの条件」として表示する。
    """
    hints = []
    for r in result.rules:
        if r.passed:
            continue

        short = _rule_short_name(r.rule_name)

        if "①" in r.rule_name:
            # 利回りルール — 「株価がいくらまで下がれば」
            hints.append(
                f"❌ {short}: 現在 {r.current_value}（基準 {r.threshold}）"
                f"\n   → 株価がもう少し下がるか、増配で利回りが上昇すれば達成"
            )
        elif "②" in r.rule_name:
            # PEG/成長ルール
            if "成長率" in r.detail and "業種平均" in r.detail:
                hints.append(
                    f"❌ {short}: {r.current_value}（基準 {r.threshold}）"
                    f"\n   → 営業利益の成長加速 or 株価下落でPEG改善が必要"
                )
            else:
                hints.append(
                    f"❌ {short}: {r.current_value}（基準 {r.threshold}）"
                    f"\n   → 株価下落でPER低下 → PEG改善を待つ"
                )
        elif "③" in r.rule_name:
            # PERルール — 「PERがいくつまで下がれば」
            val = r.current_value if not r.current_value.startswith("PER") else r.current_value
            hints.append(
                f"❌ {short}: {val}（基準 {r.threshold}）"
                f"\n   → 株価下落 or EPS改善でPER低下を待つ"
            )
        elif "④" in r.rule_name:
            # モメンタム/底打ち — 最重要
            hints.append(
                f"❌ {short}: {r.current_value}（基準 {r.threshold}）"
                f"\n   → まだ下落中。底打ち反転を確認してから"
            )
        else:
            hints.append(f"❌ {short}: {r.current_value}（基準 {r.threshold}）")

    return hints


# ============================================================
# 通知フォーマッター
# ============================================================

def format_signal_message(result) -> str:
    """🎯 エントリーシグナル確定の通知メッセージ"""
    lines = [
        f"🎯 エントリーシグナル確定！",
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
            detail = r.detail if len(r.detail) < 80 else r.detail[:77] + "..."
            lines.append(f"   {detail}")
        for w in r.warnings:
            lines.append(f"   ⚠️ {w}")

    lines.append(f"──────────────────")
    lines.append(f"検出時刻: {result.timestamp.strftime('%Y-%m-%d %H:%M')}")

    return "\n".join(lines)


def format_near_miss_message(near_miss_results: list) -> str:
    """👀 ニアミス銘柄の通知メッセージ（あと何が足りないか付き）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"👀 ニアミス銘柄（あと少しでシグナル確定）",
        f"日時: {now}",
        f"──────────────────",
    ]

    for result in near_miss_results:
        # 達成/未達マーク
        marks = "".join("✅" if r.passed else "❌" for r in result.rules)
        lines.append(f"")
        lines.append(f"■ {result.name} ({result.symbol}) {marks}")
        lines.append(f"  達成: {result.rules_passed}/{result.rules_total}")

        # 達成済みルール（簡潔に）
        passed_rules = [r for r in result.rules if r.passed]
        for r in passed_rules:
            short = _rule_short_name(r.rule_name)
            lines.append(f"  ✅ {short}: {r.current_value}")

        # 未達ルール（あと何が必要か）
        missing = analyze_missing_conditions(result)
        for hint in missing:
            lines.append(f"  {hint}")

    lines.append(f"")
    lines.append(f"──────────────────")
    lines.append(f"※ 条件が揃えば 🎯 シグナル確定通知を送信します")

    return "\n".join(lines)


def format_daily_summary(results, entry_results, near_miss_results) -> str:
    """📊 日次サマリーメッセージ"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"📊 日次スクリーニングレポート",
        f"日時: {now}",
        f"対象: 1489 ETF構成 {len(results)}銘柄",
        f"",
    ]

    if entry_results:
        lines.append(f"🎯 シグナル確定: {len(entry_results)}銘柄")
        for r in entry_results:
            lines.append(f"  → {r.name} ({r.symbol}) {r.rules_passed}/{r.rules_total}")
        lines.append("")

    if near_miss_results:
        lines.append(f"👀 ニアミス: {len(near_miss_results)}銘柄")
        for r in near_miss_results:
            marks = "".join("✅" if rule.passed else "❌" for rule in r.rules)
            lines.append(f"  {r.name} ({r.symbol}) {marks}")
        lines.append("")

    if not entry_results and not near_miss_results:
        lines.append("シグナルなし。引き続き監視中。")

    return "\n".join(lines)


def format_weekly_summary(results, entry_results, near_miss_results) -> str:
    """📋 週次サマリーメッセージ（全銘柄俯瞰）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"📋 週次スクリーニングサマリー",
        f"日時: {now}",
        f"対象: 1489 ETF構成 {len(results)}銘柄",
        f"══════════════════",
    ]

    # シグナル確定銘柄
    if entry_results:
        lines.append(f"")
        lines.append(f"🎯 シグナル確定: {len(entry_results)}銘柄")
        lines.append(f"──────────────────")
        for r in entry_results:
            lines.append(f"  {r.name} ({r.symbol})")
            for rule in r.rules:
                mark = "✅" if rule.passed else "❌"
                short = _rule_short_name(rule.rule_name)
                lines.append(f"    {mark} {short}: {rule.current_value}")
    else:
        lines.append(f"\n🎯 シグナル確定: なし")

    # ニアミス銘柄（詳細付き）
    lines.append(f"")
    if near_miss_results:
        lines.append(f"👀 ニアミス: {len(near_miss_results)}銘柄")
        lines.append(f"──────────────────")
        for r in near_miss_results:
            marks = "".join("✅" if rule.passed else "❌" for rule in r.rules)
            lines.append(f"  {r.name} ({r.symbol}) {marks}")
            missing = analyze_missing_conditions(r)
            for hint in missing:
                lines.append(f"  {hint}")
            lines.append("")
    else:
        lines.append(f"👀 ニアミス: なし")

    # 全銘柄ルール達成数の分布
    lines.append(f"")
    lines.append(f"📊 ルール達成分布")
    lines.append(f"──────────────────")
    for n in range(4, -1, -1):
        stocks = [r for r in results if r.rules_passed == n]
        if stocks:
            names = ", ".join(f"{r.name}" for r in stocks[:8])
            suffix = f" ...他{len(stocks)-8}" if len(stocks) > 8 else ""
            lines.append(f"  {n}/4: {len(stocks)}銘柄 — {names}{suffix}")

    lines.append(f"══════════════════")

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
        msg = (
            "🔔 株式スクリーナー通知テスト\n\n"
            "このメッセージが届いていれば通知設定は正常です。\n"
            f"チャネル: {', '.join(self.channels) or 'なし'}\n"
            f"送信時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "通知レベル:\n"
            "  🎯 シグナル確定 — 全ルール達成\n"
            "  👀 ニアミス — あと1条件で確定\n"
            "  📊 日次サマリー — 毎日15:30 JST\n"
            "  📋 週次サマリー — 毎週土曜9:00 JST"
        )
        self.send(msg, title="🔔 通知テスト")


# ============================================================
# スキャン実行
# ============================================================

def run_scan(rules, dry_run: bool = False, weekly: bool = False) -> int:
    """スクリーニング実行＆通知"""
    from screener_config import SCREENING_WATCHLIST
    from stock_screener import print_screening_report, screen_stocks

    notifier = ScreenerNotifier()

    logger.info(f"スキャン開始: {len(SCREENING_WATCHLIST)}銘柄")

    results = screen_stocks(SCREENING_WATCHLIST, rules)
    entry_results = [r for r in results if r.is_entry_zone]
    near_miss_results = [r for r in results if not r.is_entry_zone and r.rules_passed >= 2]

    # コンソールにレポート表示
    print_screening_report(results)

    if dry_run:
        logger.info("ドライランモード: 通知はスキップ")
        if entry_results:
            print(f"\n[ドライラン] 🎯 {len(entry_results)}件のシグナル確定（通知なし）")
        if near_miss_results:
            print(f"[ドライラン] 👀 {len(near_miss_results)}件のニアミス（通知なし）")
            # ニアミス内容はドライランでも表示
            print(format_near_miss_message(near_miss_results))
        return 0

    # === 週次モード ===
    if weekly:
        summary = format_weekly_summary(results, entry_results, near_miss_results)
        notifier.send(summary, title="📋 週次スクリーニングサマリー")
        logger.info("週次サマリー送信完了")
        return len(entry_results)

    # === 日次モード ===

    # 1. シグナル確定 → 強い通知（個別送信）
    if entry_results:
        logger.info(f"🎯 {len(entry_results)}件のエントリーシグナル確定！")
        for result in entry_results:
            msg = format_signal_message(result)
            notifier.send(msg, title=f"🎯 {result.name} ({result.symbol}) エントリーシグナル確定！")

    # 2. ニアミス → 毎日通知（あと何が必要かを明記）
    if near_miss_results:
        logger.info(f"👀 {len(near_miss_results)}件のニアミス銘柄")
        msg = format_near_miss_message(near_miss_results)
        notifier.send(msg, title=f"👀 ニアミス {len(near_miss_results)}銘柄 — あと少し")

    # 3. 日次サマリー（コンパクト版）
    summary = format_daily_summary(results, entry_results, near_miss_results)
    notifier.send(summary, title="📊 日次スクリーニングレポート")

    logger.info(f"スキャン完了: 🎯{len(entry_results)} 👀{len(near_miss_results)} / {len(results)}銘柄")
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
    parser.add_argument("--weekly", action="store_true", help="週次サマリーモード")
    parser.add_argument("--peg", type=float, default=1.0, help="PEGしきい値 (default: 1.0)")
    parser.add_argument("--yield-pct", type=float, default=20.0, help="利回り上位%%%% (default: 20)")
    parser.add_argument("--per-pct", type=float, default=30.0, help="PER下位%%%% (default: 30)")
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

    signal_count = run_scan(rules, dry_run=args.dry_run, weekly=args.weekly)
    return 0


if __name__ == "__main__":
    sys.exit(main())
