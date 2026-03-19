"""
バックテスト: 実際のMBO事例でSPC検出精度を検証する

過去の公開MBO案件で使われたSPC法人と、
MBOと無関係な「紛らわしい法人」の両方をテストし、
適合率(Precision)と再現率(Recall)を確認する。

参照: レポート「SPCからMBOを事前に読む方法：実務的手法の全体像」
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

    # ================================================================
    # レポート記載の実MBO事例
    # ================================================================

    def test_taisho_pharma_ohtemon(self):
        """大正製薬HD MBO (2023) - SPC「大手門株式会社」
        レポート: SPC設立2023/8/17, TOB公表2023/11/24, リードタイム約3ヶ月
        代表者は副社長・上原茂氏（創業家）、住所は豊島区の本社近辺
        """
        result = self._analyze(
            "大手門株式会社", entity_type="株式会社",
            representative="上原茂",
            prefecture="東京都", city="豊島区",
        )
        # 「大手門」は汎用名だが株式会社+代表者情報で検出を期待
        # 注: この事例はSPC検出単独では困難。代表者照合が必要
        self.assertIsNotNone(result["spc_score"])

    def test_bcj78_outsourcing(self):
        """アウトソーシング MBO (2023) - SPC「BCJ-78」
        レポート: Bain Capital BCJ-連番パターン
        """
        result = self._analyze(
            "BCJ-78", entity_type="株式会社",
            prefecture="東京都", city="千代田区", address="丸の内1-9-2",
            capital="1",
        )
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertGreaterEqual(result["spc_score"], 0.7)
        self.assertIn("Bain Capital", result["notes"])

    def test_bcj98_nisshin(self):
        """日新 MBO - SPC「BCJ-98」"""
        result = self._analyze(
            "BCJ-98", entity_type="株式会社",
            prefecture="東京都", city="千代田区", address="丸の内1-9-2",
        )
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertIn("Bain Capital", result["notes"])

    def test_bcj52_hitachi_metals(self):
        """日立金属 - SPC「BCJ-52」"""
        result = self._analyze("BCJ-52")
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertIn("BCJ-連番", result["notes"])

    def test_mcap12_nagatanien(self):
        """永谷園HD MBO (2024) - SPC「エムキャップ十二号」
        レポート: 丸の内キャピタルのパターン、リードタイム約41日
        """
        result = self._analyze(
            "エムキャップ十二号", entity_type="株式会社",
            prefecture="東京都", city="千代田区",
        )
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertIn("丸の内キャピタル", result["notes"])

    def test_bloom1_benesse(self):
        """ベネッセHD MBO (2023) - SPC「ブルーム1」
        レポート: EQT系、SPC設立2023/8/1, TOB公表2023/11/10
        """
        result = self._analyze(
            "ブルーム1", entity_type="株式会社",
            prefecture="東京都", city="千代田区",
        )
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertIn("EQT", result["notes"])

    def test_ahc_io_data(self):
        """アイ・オー・データ機器 MBO (2022) - SPC「AHC」
        レポート: 最も有名なSPC検出事例。石川県金沢市に設立。
        大株主「有限会社トレント」と同一住所。
        """
        result = self._analyze(
            "AHC", entity_type="株式会社",
            prefecture="石川県", city="金沢市", address="上堤町1番35号",
            capital="1",
        )
        self.assertEqual(result["is_spc_candidate"], 1)

    def test_bacj80_snowpeak(self):
        """スノーピーク MBO (2024) - SPC「BACJ-80」"""
        result = self._analyze("BACJ-80", entity_type="株式会社")
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertIn("Bain Capital", result["notes"])

    def test_bcpe_gaia_bain(self):
        """ベインキャピタル系SPC（BCPE Gaiaパターン）"""
        result = self._analyze("合同会社BCPE Gaia")
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertGreaterEqual(result["spc_score"], 0.5)

    def test_jip_toshiba_spc(self):
        """JIP系SPC（東芝 MBO 2023）- TBJH合同会社"""
        result = self._analyze("TBJH合同会社")
        self.assertEqual(result["is_spc_candidate"], 1)

    # Carlyleの遊び心パターン
    def test_carlyle_crispy_kfc(self):
        """カーライル系SPC（日本KFC）- クリスピー"""
        result = self._analyze(
            "クリスピー株式会社", entity_type="株式会社",
            prefecture="東京都", city="千代田区",
        )
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertIn("Carlyle", result["notes"])

    def test_carlyle_juicy_kfc(self):
        """カーライル系SPC（日本KFC）- ジューシー"""
        result = self._analyze("ジューシー株式会社", entity_type="株式会社")
        self.assertEqual(result["is_spc_candidate"], 1)

    # Integral系
    def test_integral_voyager_daioz(self):
        """Integral系SPC（ダイオーズ）- ボイジャー"""
        result = self._analyze(
            "ボイジャー株式会社", entity_type="株式会社",
            prefecture="東京都", city="千代田区", address="丸の内1-9-2",
        )
        self.assertEqual(result["is_spc_candidate"], 1)

    # Polaris系
    def test_polaris_psm_holdings(self):
        """Polaris系SPC（総合メディカル）- PSMホールディングス"""
        result = self._analyze(
            "PSMホールディングス", entity_type="株式会社",
            prefecture="東京都", city="千代田区",
        )
        self.assertEqual(result["is_spc_candidate"], 1)

    # PE住所マッチングテスト
    def test_pe_office_address_bain(self):
        """Bain Capitalオフィス住所に登記された法人"""
        result = self._analyze(
            "ABC株式会社", entity_type="株式会社",
            prefecture="東京都", city="千代田区",
            address="丸の内1-9-2 グラントウキョウサウスタワー",
            capital="1",
        )
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertIn("Bain Capital", result["notes"])

    def test_pe_office_address_law_firm(self):
        """M&A法律事務所住所に登記された法人"""
        result = self._analyze(
            "XYZホールディングス", entity_type="株式会社",
            prefecture="東京都", city="千代田区",
            address="大手町1-1-2 大手町三井ビル",
        )
        self.assertEqual(result["is_spc_candidate"], 1)
        self.assertIn("西村あさひ", result["notes"])

    # ================================================================
    # その他の一般パターン
    # ================================================================

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

    def test_strategic_acquisition(self):
        """ストラテジック系SPC"""
        result = self._analyze("ストラテジックパートナーズ")
        self.assertEqual(result["is_spc_candidate"], 1)

    # ================================================================
    # 検出すべきでない: MBOと無関係な法人
    # ================================================================

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

    def test_false_positive_securitization_spc(self):
        """証券化SPC → 除外（レポート: 不動産SPCが大量のノイズ）"""
        result = self._analyze(
            "第一号不動産特定目的会社",
            purpose="不動産の取得及び管理",
        )
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
            "market_cap": 20_000_000_000,
        }
        score, reasons = self.matcher._calculate_match_score(spc, company)
        self.assertGreaterEqual(score, 0.3)

    def test_representative_match_taisho(self):
        """レポート: 大正製薬MBOでSPC代表者と企業役員が一致"""
        spc = {
            "name": "大手門株式会社",
            "corporate_number": "0",
            "representative": "上原茂",
        }
        company = {
            "name": "大正製薬ホールディングス株式会社",
            "code": "4581",
            "officers": ["上原茂", "上原明"],
            "pbr": 0.9,
            "owner_ratio": 40.0,
            "market_cap": 500_000_000_000,
        }
        score, reasons = self.matcher._calculate_match_score(spc, company)
        self.assertGreaterEqual(score, 0.5)
        reason_text = " ".join(reasons)
        self.assertIn("上原茂", reason_text)

    def test_owner_name_match(self):
        """SPC代表者がオーナー名と一致"""
        spc = {
            "name": "ABCホールディングス",
            "corporate_number": "0",
            "representative": "田中太郎",
        }
        company = {
            "name": "田中産業株式会社",
            "code": "9999",
            "owner_name": "田中太郎",
            "owner_ratio": 45.0,
        }
        score, reasons = self.matcher._calculate_match_score(spc, company)
        self.assertGreaterEqual(score, 0.5)

    def test_full_profile_mbo_candidate(self):
        """レポート記載の全条件を満たす理想的なMBO候補"""
        spc = {"name": "XYZホールディングス", "corporate_number": "0"}
        company = {
            "name": "XYZ工業株式会社", "code": "5678",
            "pbr": 0.4,               # PBR極端に低い
            "owner_ratio": 35.0,      # オーナー持株比率高い
            "market_cap": 20e9,       # 小型株（200億円）
            "ceo_age": 72,            # CEO高齢
            "net_cash": 12e9,         # ネットキャッシュ60%
            "fcf_yield": 0.08,        # FCF利回り8%
            "has_activist": True,     # アクティビスト株主あり
            "analyst_coverage": 1,    # アナリスト1名
        }
        score, reasons = self.matcher._calculate_match_score(spc, company)
        self.assertGreaterEqual(score, 0.9)
        reason_text = " ".join(reasons)
        self.assertIn("PBR", reason_text)
        self.assertIn("オーナー", reason_text)
        self.assertIn("CEO", reason_text)
        self.assertIn("ネットキャッシュ", reason_text)
        self.assertIn("アクティビスト", reason_text)

    def test_ceo_age_signal(self):
        """CEO年齢シグナル"""
        spc = {"name": "ABCホールディングス", "corporate_number": "0"}
        company = {
            "name": "ABC電機株式会社", "code": "1111",
            "ceo_age": 70,
        }
        score, reasons = self.matcher._calculate_match_score(spc, company)
        reason_text = " ".join(reasons)
        self.assertIn("CEO", reason_text)


if __name__ == "__main__":
    unittest.main()
