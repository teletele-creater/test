"""データベースモデルのテスト"""
import os
import tempfile
import unittest
from src.database.models import Database


class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.db = Database(db_path=self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_upsert_corporation_new(self):
        """新規法人の挿入"""
        corp = {
            "corporate_number": "1234567890123",
            "name": "テスト合同会社",
            "entity_type": "合同会社",
        }
        is_new = self.db.upsert_corporation(corp)
        self.assertTrue(is_new)

    def test_upsert_corporation_update(self):
        """既存法人の更新"""
        corp = {
            "corporate_number": "1234567890123",
            "name": "テスト合同会社",
            "entity_type": "合同会社",
        }
        self.db.upsert_corporation(corp)
        corp["name"] = "テスト合同会社（更新）"
        is_new = self.db.upsert_corporation(corp)
        self.assertFalse(is_new)

    def test_get_spc_candidates(self):
        """SPC候補の取得"""
        corp = {
            "corporate_number": "1111111111111",
            "name": "SPC テスト",
            "is_spc_candidate": 1,
            "spc_score": 0.8,
        }
        self.db.upsert_corporation(corp)
        candidates = self.db.get_spc_candidates(min_score=0.5)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["name"], "SPC テスト")

    def test_upsert_listed_company(self):
        """上場企業の挿入・更新"""
        company = {
            "code": "1234",
            "name": "テスト株式会社",
            "market": "プライム",
            "sector": "情報・通信業",
        }
        self.db.upsert_listed_company(company)
        companies = self.db.get_listed_companies()
        self.assertEqual(len(companies), 1)

    def test_search_listed_companies(self):
        """上場企業の検索"""
        self.db.upsert_listed_company({"code": "1234", "name": "テスト株式会社"})
        self.db.upsert_listed_company({"code": "5678", "name": "サンプル株式会社"})
        results = self.db.search_listed_companies("テスト")
        self.assertEqual(len(results), 1)

    def test_add_mbo_candidate(self):
        """MBO候補の追加"""
        # 先に法人と上場企業を作成
        self.db.upsert_corporation({
            "corporate_number": "1111111111111",
            "name": "SPC",
        })
        self.db.upsert_listed_company({"code": "1234", "name": "Target"})

        candidate_id = self.db.add_mbo_candidate({
            "spc_corporate_number": "1111111111111",
            "listed_company_code": "1234",
            "match_score": 0.75,
        })
        self.assertIsNotNone(candidate_id)

        candidates = self.db.get_mbo_candidates()
        self.assertEqual(len(candidates), 1)

    def test_upsert_edinet_document(self):
        """EDINET書類のupsert"""
        doc = {
            "doc_id": "S100ABC",
            "doc_type": "公開買付届出書",
            "filer_name": "テスト",
            "title": "テスト書類",
        }
        is_new = self.db.upsert_edinet_document(doc)
        self.assertTrue(is_new)
        is_new = self.db.upsert_edinet_document(doc)
        self.assertFalse(is_new)

    def test_upsert_tdnet_disclosure(self):
        """TDnet開示のupsert"""
        disc = {
            "disclosure_id": "td001",
            "company_code": "1234",
            "company_name": "テスト",
            "title": "MBOに関するお知らせ",
        }
        is_new = self.db.upsert_tdnet_disclosure(disc)
        self.assertTrue(is_new)
        is_new = self.db.upsert_tdnet_disclosure(disc)
        self.assertFalse(is_new)

    def test_monitor_log(self):
        """監視ログの追加"""
        self.db.add_monitor_log("test", "action", "result", '{"key": "value"}')


if __name__ == "__main__":
    unittest.main()
