"""SPC検出エンジンのテスト"""
import unittest
from src.analyzers.spc_detector import SpcDetector


class TestSpcDetector(unittest.TestCase):

    def setUp(self):
        self.detector = SpcDetector()

    def test_llc_with_holdings_name(self):
        """合同会社 + ホールディングス名称 → 高スコア"""
        corp = {
            "corporate_number": "1234567890123",
            "name": "ABCホールディングス",
            "entity_type": "合同会社",
            "prefecture": "東京都",
            "city": "千代田区",
            "address": "丸の内1-1-1",
        }
        result = self.detector.analyze(corp)
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertGreaterEqual(result["spc_score"], 0.3)

    def test_llc_with_investment_name(self):
        """合同会社 + インベストメント名称"""
        corp = {
            "corporate_number": "9999999999999",
            "name": "第一インベストメント",
            "entity_type": "合同会社",
            "prefecture": "東京都",
            "city": "港区",
            "address": "六本木1-1-1",
        }
        result = self.detector.analyze(corp)
        self.assertEqual(result["is_spc_candidate"], 1)

    def test_pe_fund_keyword(self):
        """PEファンド名を含む法人"""
        corp = {
            "corporate_number": "1111111111111",
            "name": "ベインキャピタルジャパン合同会社",
            "entity_type": "合同会社",
            "prefecture": "東京都",
            "city": "千代田区",
        }
        result = self.detector.analyze(corp)
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertGreaterEqual(result["spc_score"], 0.5)

    def test_ordinary_company_low_score(self):
        """一般的な企業名 → 低スコア"""
        corp = {
            "corporate_number": "2222222222222",
            "name": "田中食品",
            "entity_type": "株式会社",
            "prefecture": "大阪府",
            "city": "大阪市北区",
        }
        result = self.detector.analyze(corp)
        self.assertEqual(result["is_spc_candidate"], 0)
        self.assertLess(result["spc_score"], 0.3)

    def test_english_only_name(self):
        """英語名のみの法人"""
        corp = {
            "corporate_number": "3333333333333",
            "name": "Global Acquisition Partners",
            "entity_type": "合同会社",
            "prefecture": "東京都",
            "city": "港区",
            "address": "虎ノ門1-1-1",
        }
        result = self.detector.analyze(corp)
        self.assertEqual(result["is_spc_candidate"], 1)

    def test_small_capital(self):
        """少額資本金"""
        corp = {
            "corporate_number": "4444444444444",
            "name": "テストキャピタル",
            "entity_type": "合同会社",
            "capital": "1",
            "prefecture": "東京都",
            "city": "中央区",
        }
        result = self.detector.analyze(corp)
        self.assertEqual(result["is_spc_candidate"], 1)

    def test_batch_analyze(self):
        """バッチ分析"""
        corps = [
            {"corporate_number": "1111", "name": "ABCホールディングス", "entity_type": "合同会社"},
            {"corporate_number": "2222", "name": "田中食品", "entity_type": "株式会社"},
        ]
        results = self.detector.analyze_batch(corps)
        self.assertEqual(len(results), 2)
        candidates = [r for r in results if r["is_spc_candidate"]]
        self.assertGreaterEqual(len(candidates), 1)


class TestSpcDetectorEdgeCases(unittest.TestCase):

    def setUp(self):
        self.detector = SpcDetector()

    def test_empty_corporation(self):
        """空の法人情報"""
        corp = {"corporate_number": "0000000000000"}
        result = self.detector.analyze(corp)
        self.assertEqual(result["is_spc_candidate"], 0)
        self.assertEqual(result["spc_score"], 0.0)

    def test_none_fields(self):
        """Noneフィールドを含む法人情報"""
        corp = {
            "corporate_number": "5555555555555",
            "name": None,
            "entity_type": None,
            "capital": None,
        }
        result = self.detector.analyze(corp)
        self.assertIsNotNone(result["spc_score"])


if __name__ == "__main__":
    unittest.main()
