"""
通知モジュール

Discord, LINE Notify, Email, Slack に対応した通知システム。
.envファイルで設定されたチャネルに自動送信する。
"""

import json
import logging
import os
import smtplib
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv

from strategy_checker import StrategySignal

load_dotenv()
logger = logging.getLogger(__name__)


class Notifier:
    """マルチチャネル通知クラス"""

    def __init__(self):
        self.discord_url = os.getenv("DISCORD_WEBHOOK_URL")
        self.line_token = os.getenv("LINE_NOTIFY_TOKEN")
        self.email_sender = os.getenv("EMAIL_SENDER")
        self.email_password = os.getenv("EMAIL_PASSWORD")
        self.email_recipient = os.getenv("EMAIL_RECIPIENT")
        self.slack_url = os.getenv("SLACK_WEBHOOK_URL")

        self._channels = []
        if self.discord_url:
            self._channels.append("Discord")
        if self.line_token:
            self._channels.append("LINE")
        if self.email_sender and self.email_password and self.email_recipient:
            self._channels.append("Email")
        if self.slack_url:
            self._channels.append("Slack")

        if self._channels:
            logger.info(f"Notification channels configured: {', '.join(self._channels)}")
        else:
            logger.warning("No notification channels configured. Alerts will only be printed to console.")

    def send_signal(self, signal: StrategySignal) -> None:
        """シグナルを全チャネルに送信"""
        summary = signal.summary()

        # コンソール出力（常に実行）
        print(summary)

        if not signal.is_triggered:
            return

        # 各チャネルに通知
        title = f"[{signal.strength}] {signal.strategy.name_jp} - {signal.symbol}"

        if self.discord_url:
            self._send_discord(title, summary)
        if self.line_token:
            self._send_line(summary)
        if self.email_sender:
            self._send_email(title, summary)
        if self.slack_url:
            self._send_slack(title, summary)

    def send_status_report(self, signals: list[StrategySignal]) -> None:
        """全戦略のステータスレポートを送信"""
        triggered = [s for s in signals if s.is_triggered]

        lines = [
            f"{'='*50}",
            f"Options Alert System - Status Report",
            f"{'='*50}",
        ]

        if triggered:
            lines.append(f"\nENTRY SIGNALS DETECTED: {len(triggered)}")
            for s in triggered:
                lines.append(f"  [{s.strength}] {s.strategy.name_jp} ({s.symbol})")
        else:
            lines.append("\nNo entry signals at this time.")

        lines.append(f"\n{'─'*50}")
        lines.append("All strategies status:")

        for s in signals:
            status = "SIGNAL" if s.is_triggered else "---"
            lines.append(
                f"  [{status}] {s.strategy.name_jp}: "
                f"{s.conditions_met}/{s.conditions_total} conditions met"
            )

        report = "\n".join(lines)
        print(report)

        if triggered:
            for s in triggered:
                self.send_signal(s)

    def _send_discord(self, title: str, message: str) -> None:
        """Discord Webhookに送信"""
        try:
            # Discordは2000文字制限
            content = f"**{title}**\n```\n{message[:1900]}\n```"
            payload = {"content": content}
            resp = requests.post(
                self.discord_url,
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("Discord notification sent")
        except Exception as e:
            logger.error(f"Discord notification failed: {e}")

    def _send_line(self, message: str) -> None:
        """LINE Notifyに送信"""
        try:
            headers = {"Authorization": f"Bearer {self.line_token}"}
            payload = {"message": f"\n{message[:900]}"}  # LINE Notifyは1000文字制限
            resp = requests.post(
                "https://notify-api.line.me/api/notify",
                headers=headers,
                data=payload,
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("LINE notification sent")
        except Exception as e:
            logger.error(f"LINE notification failed: {e}")

    def _send_email(self, title: str, message: str) -> None:
        """Gmailで送信"""
        try:
            msg = MIMEText(message, "plain", "utf-8")
            msg["Subject"] = f"Options Alert: {title}"
            msg["From"] = self.email_sender
            msg["To"] = self.email_recipient

            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
                server.login(self.email_sender, self.email_password)
                server.send_message(msg)
            logger.info("Email notification sent")
        except Exception as e:
            logger.error(f"Email notification failed: {e}")

    def _send_slack(self, title: str, message: str) -> None:
        """Slack Webhookに送信"""
        try:
            payload = {
                "text": f"*{title}*",
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{title}*\n```{message[:2900]}```"},
                    }
                ],
            }
            resp = requests.post(
                self.slack_url,
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("Slack notification sent")
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")

    def send_test(self) -> None:
        """テスト通知を全チャネルに送信"""
        test_msg = (
            "Options Alert System - Test Notification\n"
            "This is a test message to verify notification channels.\n"
            "If you received this, your alerts are configured correctly."
        )
        print(f"Sending test notification to: {', '.join(self._channels) or 'Console only'}")

        if self.discord_url:
            self._send_discord("Test", test_msg)
        if self.line_token:
            self._send_line(test_msg)
        if self.email_sender:
            self._send_email("Test Notification", test_msg)
        if self.slack_url:
            self._send_slack("Test", test_msg)

        print("Test notifications sent.")
