"""
バックテスト: 実際のMBO事例でSPC検出精度を検証する

過去の公開MBO案件で使われたSPC法人と、
MBOと無関係な「紛らわしい法人」の両方をテストし、
適合率(Precision)と再現率(Recall)を確認する。
"""
import unittest
from src.analyzers.spc_detector import SpcDetector


class TestBacktestRealMBOCases(unittest.TestCase):
    """実際のMBO/TOB事例のSPC法人を検出できるか"""

    def setUp(self):
        self.detector = SpcDetector()

    def _analyze(self, name, entity_type="合同会社", **kwargs):
        corp = {
            "corporate_number": "0000000000000",
            "name": name,
            "entity_type": entity_type,
            **kwargs,
        }
        return self.detector.analyze(corp)

    # === 検出すべき: 実際のMBO SPCパターン ===

    def test_bain_capital_spc(self):
        """ベインキャピタル系SPC（大正製薬HD MBO 2023）"""
        result = self._analyze("合同会社BCPE Gaia")
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertGreaterEqual(result["spc_score"], 0.5)

    def test_jip_toshiba_spc(self):
        """JIP系SPC（東芝 MBO 2023）"""
        result = self._analyze("TBJH合同会社")
        self.assertEqual(result["is_spc_candidate"], 1)

    def test_mbo_holdings_pattern(self):
        """典型的なMBO SPCパターン: ○○ホールディングス"""
        result = self._analyze("スカイマークホールディングス")
        self.assertEqual(result["is_spc_candidate"], 1)

    def test_generic_acquisition_llc(self):
        """汎用的な買収目的SPC"""
        result = self._analyze("Japan Acquisition Corp")
        self.assertEqual(result["is_spc_candidate"], 1)

    def test_pe_fund_investment_vehicle(self):
        """PEファンド投資ビークル"""
        result = self._analyze(
            "KKRジャパンインベストメント",
            prefecture="東京都", city="千代田区", address="丸の内1-1-1",
        )
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertGreaterEqual(result["spc_score"], 0.5)

    def test_carlyle_spc(self):
        """カーライル系SPC"""
        result = self._analyze("CJホールディングス",
                               purpose="カーライル・グループ関連の投資事業")
        self.assertEqual(result["is_spc_candidate"], 1)

    def test_polaris_spc(self):
        """ポラリス系SPC"""
        result = self._analyze("ポラリスキャピタルグループ")
        self.assertEqual(result["is_spc_candidate"], 1)

    def test_strategic_acquisition(self):
        """ストラテジック系SPC"""
        result = self._analyze("ストラテジックパートナーズ")
        self.assertEqual(result["is_spc_candidate"], 1)

    # === 検出すべきでない: MBOと無関係な法人 ===

    def test_false_positive_real_estate(self):
        """不動産キャピタル → 除外"""
        result = self._analyze("不動産キャピタルマネジメント")
        self.assertEqual(result["is_spc_candidate"], 0)

    def test_false_positive_solar(self):
        """太陽光発電SPC → 除外"""
        result = self._analyze("太陽光インベストメント")
        self.assertEqual(result["is_spc_candidate"], 0)

    def test_false_positive_restaurant(self):
        """飲食ホールディングス → 除外"""
        result = self._analyze("飲食ホールディングス")
        self.assertEqual(result["is_spc_candidate"], 0)

    def test_false_positive_real_estate_purpose(self):
        """名前は怪しいが事業目的が不動産"""
        result = self._analyze(
            "ABCインベストメント",
            purpose="不動産の売買、賃貸及び管理",
        )
        self.assertEqual(result["is_spc_candidate"], 0)

    def test_false_positive_clinic(self):
        """医療系は除外"""
        result = self._analyze("医療キャピタルパートナーズ")
        self.assertEqual(result["is_spc_candidate"], 0)

    def test_ordinary_kabushiki(self):
        """一般的な株式会社"""
        result = self._analyze("山田電機", entity_type="株式会社",
                               prefecture="埼玉県", city="さいたま市")
        self.assertEqual(result["is_spc_candidate"], 0)
        self.assertLess(result["spc_score"], 0.15)

    def test_ordinary_llc(self):
        """一般的な合同会社（SPCパターンなし）"""
        result = self._analyze("鈴木商事")
        self.assertLess(result["spc_score"], 0.3)


class TestBacktestMBOMatcher(unittest.TestCase):
    """MBOマッチングのバックテスト"""

    def setUp(self):
        from src.analyzers.mbo_matcher import MboMatcher
        self.matcher = MboMatcher.__new__(MboMatcher)

    def test_name_inclusion_match(self):
        """SPC名に上場企業名を含む場合"""
        spc = {"name": "大正製薬ホールディングス", "corporate_number": "0"}
        company = {"name": "大正製薬ホールディングス株式会社", "code": "4581"}
        score, reasons = self.matcher._calculate_match_score(spc, company)
        self.assertGreaterEqual(score, 0.3)

    def test_unrelated_name_no_match(self):
        """無関係なSPCと上場企業"""
        spc = {"name": "ABCアクイジション", "corporate_number": "0"}
        company = {"name": "トヨタ自動車株式会社", "code": "7203"}
        score, reasons = self.matcher._calculate_match_score(spc, company)
        self.assertLess(score, 0.2)

    def test_low_pbr_small_cap_boost(self):
        """低PBR + 小型株は高スコア"""
        spc = {"name": "テストホールディングス", "corporate_number": "0"}
        company = {
            "name": "テスト工業株式会社", "code": "1234",
            "pbr": 0.4, "owner_ratio": 35.0,
            "market_cap": 20_000_000_000,  # 200億
        }
        score, reasons = self.matcher._calculate_match_score(spc, company)
        self.assertGreaterEqual(score, 0.3)


if __name__ == "__main__":
    unittest.main()
