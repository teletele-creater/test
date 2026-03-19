"""
MBO予測システム - メインエントリポイント
新規法人のSPC検出 → 上場企業とのマッチング → 通知 を定期実行する
"""
import argparse
import schedule
import time
from datetime import datetime

from config.settings import (
    NTA_CHECK_INTERVAL_MINUTES,
    EDINET_CHECK_INTERVAL_MINUTES,
    ANALYSIS_INTERVAL_MINUTES,
)
from src.database.models import Database
from src.scrapers.nta_scraper import NtaScraper
from src.scrapers.edinet_scraper import EdinetScraper
from src.scrapers.tdnet_scraper import TdnetScraper
from src.scrapers.jpx_scraper import JpxScraper
from src.analyzers.spc_detector import SpcDetector
from src.analyzers.mbo_matcher import MboMatcher
from src.notifiers.slack_notifier import SlackNotifier
from src.notifiers.email_notifier import EmailNotifier
from src.utils.logger import setup_logger

logger = setup_logger("main")


class MboDetector:
    """MBO検出システムのメインオーケストレーター"""

    def __init__(self):
        self.db = Database()
        self.nta = NtaScraper()
        self.edinet = EdinetScraper()
        self.tdnet = TdnetScraper()
        self.jpx = JpxScraper()
        self.spc_detector = SpcDetector()
        self.mbo_matcher = MboMatcher(self.db)
        self.slack = SlackNotifier()
        self.email = EmailNotifier()

    def run_nta_check(self):
        """国税庁APIから新規法人を取得・分析"""
        logger.info("=== NTA Corporation Check ===")
        try:
            corporations = self.nta.fetch_new_corporations()
            analyzed = self.spc_detector.analyze_batch(corporations)

            new_count = 0
            spc_count = 0
            for corp in analyzed:
                is_new = self.db.upsert_corporation(corp)
                if is_new:
                    new_count += 1
                if corp.get("is_spc_candidate"):
                    spc_count += 1
                    self.slack.notify_new_spc(corp)

            self.db.add_monitor_log("nta", "fetch_corporations",
                                    f"new={new_count}, spc_candidates={spc_count}")
            logger.info(f"NTA check done: {new_count} new, {spc_count} SPC candidates")
        except Exception as e:
            logger.error(f"NTA check failed: {e}")
            self.db.add_monitor_log("nta", "fetch_corporations", f"error: {e}")

    def run_edinet_check(self):
        """EDINET APIからMBO関連書類を取得"""
        logger.info("=== EDINET Document Check ===")
        try:
            docs = self.edinet.fetch_mbo_related_documents(days=1)
            new_count = 0
            for doc in docs:
                is_new = self.db.upsert_edinet_document(doc)
                if is_new:
                    new_count += 1
                    self.slack.notify_edinet_filing(doc)

            self.db.add_monitor_log("edinet", "fetch_documents", f"mbo_docs={new_count}")
            logger.info(f"EDINET check done: {new_count} new MBO-related documents")
        except Exception as e:
            logger.error(f"EDINET check failed: {e}")
            self.db.add_monitor_log("edinet", "fetch_documents", f"error: {e}")

    def run_tdnet_check(self):
        """TDnetからMBO関連適時開示を取得"""
        logger.info("=== TDnet Disclosure Check ===")
        try:
            disclosures = self.tdnet.fetch_mbo_related_disclosures()
            new_count = 0
            for disc in disclosures:
                is_new = self.db.upsert_tdnet_disclosure(disc)
                if is_new:
                    new_count += 1

            self.db.add_monitor_log("tdnet", "fetch_disclosures", f"mbo_disclosures={new_count}")
            logger.info(f"TDnet check done: {new_count} new MBO-related disclosures")
        except Exception as e:
            logger.error(f"TDnet check failed: {e}")
            self.db.add_monitor_log("tdnet", "fetch_disclosures", f"error: {e}")

    def run_jpx_update(self):
        """JPX上場企業リストを更新"""
        logger.info("=== JPX Listed Companies Update ===")
        try:
            companies = self.jpx.fetch_listed_companies()
            for company in companies:
                self.db.upsert_listed_company(company)

            self.db.add_monitor_log("jpx", "update_companies", f"count={len(companies)}")
            logger.info(f"JPX update done: {len(companies)} companies")
        except Exception as e:
            logger.error(f"JPX update failed: {e}")
            self.db.add_monitor_log("jpx", "update_companies", f"error: {e}")

    def run_matching(self):
        """MBOマッチング分析を実行"""
        logger.info("=== MBO Matching Analysis ===")
        try:
            candidates = self.mbo_matcher.run_matching()
            for candidate in candidates:
                if candidate.get("match_score", 0) >= 0.5:
                    self.slack.notify_mbo_candidate(candidate)
                    self.email.notify_mbo_candidate(candidate)

            self.db.add_monitor_log("matcher", "run_matching", f"candidates={len(candidates)}")
            logger.info(f"Matching done: {len(candidates)} candidates")
        except Exception as e:
            logger.error(f"Matching failed: {e}")
            self.db.add_monitor_log("matcher", "run_matching", f"error: {e}")

    def run_once(self):
        """全チェックを1回実行"""
        logger.info(f"Running all checks at {datetime.now().isoformat()}")
        self.run_nta_check()
        self.run_edinet_check()
        self.run_tdnet_check()
        self.run_matching()

    def run_scheduler(self):
        """スケジューラーで定期実行"""
        logger.info("Starting MBO Detector scheduler")

        # 初回実行
        self.run_jpx_update()
        self.run_once()

        # スケジュール設定
        schedule.every(NTA_CHECK_INTERVAL_MINUTES).minutes.do(self.run_nta_check)
        schedule.every(EDINET_CHECK_INTERVAL_MINUTES).minutes.do(self.run_edinet_check)
        schedule.every(EDINET_CHECK_INTERVAL_MINUTES).minutes.do(self.run_tdnet_check)
        schedule.every(ANALYSIS_INTERVAL_MINUTES).minutes.do(self.run_matching)
        schedule.every().day.at("06:00").do(self.run_jpx_update)

        logger.info(
            f"Scheduled: NTA every {NTA_CHECK_INTERVAL_MINUTES}min, "
            f"EDINET/TDnet every {EDINET_CHECK_INTERVAL_MINUTES}min, "
            f"Matching every {ANALYSIS_INTERVAL_MINUTES}min, "
            f"JPX daily at 06:00"
        )

        while True:
            schedule.run_pending()
            time.sleep(10)


def main():
    parser = argparse.ArgumentParser(description="MBO Detection System")
    parser.add_argument("--once", action="store_true", help="Run all checks once and exit")
    parser.add_argument("--nta", action="store_true", help="Run NTA check only")
    parser.add_argument("--edinet", action="store_true", help="Run EDINET check only")
    parser.add_argument("--tdnet", action="store_true", help="Run TDnet check only")
    parser.add_argument("--jpx", action="store_true", help="Update JPX listed companies")
    parser.add_argument("--match", action="store_true", help="Run MBO matching only")
    args = parser.parse_args()

    detector = MboDetector()

    if args.nta:
        detector.run_nta_check()
    elif args.edinet:
        detector.run_edinet_check()
    elif args.tdnet:
        detector.run_tdnet_check()
    elif args.jpx:
        detector.run_jpx_update()
    elif args.match:
        detector.run_matching()
    elif args.once:
        detector.run_once()
    else:
        detector.run_scheduler()


if __name__ == "__main__":
    main()
