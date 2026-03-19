"""
確信度ティア評価（「役満」システム）のテスト

実際のMBO事例を再現し、各ティアが正しく判定されるか検証する。
"""
import unittest
from src.analyzers.spc_detector import SpcDetector
from src.analyzers.mbo_matcher import MboMatcher
from src.analyzers.confidence_assessor import (
    ConfidenceAssessor,
    TIER_YAKUMAN, TIER_HANEMAN, TIER_BAIMAN, TIER_MANGAN, TIER_SANHAN, TIER_IIHAN,
)


class TestConfidenceTiers(unittest.TestCase):
    """確信度ティアの判定テスト"""

    def setUp(self):
        self.detector = SpcDetector()
        self.matcher = MboMatcher.__new__(MboMatcher)
        self.assessor = ConfidenceAssessor()

    def _run_assessment(self, spc_data, company_data=None):
        """SPC検出 → マッチング → 確信度評価 のフルフロー"""
        spc = self.detector.analyze(spc_data)
        match_result = None
        if company_data:
            score, reasons = self.matcher._calculate_match_score(spc, company_data)
            match_result = {"score": score, "reasons": reasons}
        return self.assessor.assess(spc, company_data, match_result)

    # ================================================================
    # 役満（90%超）: 第1＋第2（SPC検出＋代表者一致）
    # ================================================================

    def test_yakuman_taisho_pharma(self):
        """大正製薬HD MBO: SPC「大手門」の代表者=副社長・上原茂氏

        オーナー家主導型MBOの典型。SPCの代表者が上場企業の
        役員と一致した時点でMBO以外の合理的説明がほぼ存在しない。
        """
        spc = {
            "corporate_number": "0001",
            "name": "大手門株式会社",
            "entity_type": "株式会社",
            "representative": "上原茂",
            "prefecture": "東京都", "city": "豊島区",
            "purpose": "有価証券の取得、保有及び管理",
        }
        company = {
            "name": "大正製薬ホールディングス株式会社",
            "code": "4581",
            "officers": ["上原茂", "上原明", "斎藤充弘"],
            "owner_name": "上原明",
            "pbr": 0.7,
            "owner_ratio": 52.0,
            "market_cap": 500e9,
            "ceo_age": 68,
        }
        result = self._run_assessment(spc, company)
        self.assertEqual(result["tier"], TIER_YAKUMAN)
        self.assertGreaterEqual(result["confidence"], 90)
        self.assertIn("tile_1", result["signal_ids"])
        self.assertIn("tile_2", result["signal_ids"])

    def test_yakuman_with_purpose(self):
        """役満＋事業目的（第4牌）で確信度がさらに上がる"""
        spc = {
            "corporate_number": "0001b",
            "name": "ABCホールディングス",
            "entity_type": "合同会社",
            "representative": "山田太郎",
            "purpose": "有価証券の取得、保有及び管理、対象会社の事業活動の支配及び管理",
        }
        company = {
            "name": "XYZ工業株式会社",
            "code": "9999",
            "officers": ["山田太郎", "佐藤花子"],
            "pbr": 0.6,
            "owner_ratio": 35.0,
            "market_cap": 30e9,
            "ceo_age": 72,
        }
        result = self._run_assessment(spc, company)
        self.assertEqual(result["tier"], TIER_YAKUMAN)
        self.assertGreaterEqual(result["confidence"], 95)
        self.assertIn("tile_4", result["signal_ids"])

    # ================================================================
    # 跳満（70-80%）: 第1＋第3の地方住所一致
    # ================================================================

    def test_haneman_io_data(self):
        """アイ・オー・データ機器 MBO: SPC「AHC」が石川県金沢市に設立

        大株主「有限会社トレント」と同一住所。
        地方都市で大株主と同一住所に新規法人が設立される偶然は極めて低い。
        """
        spc = {
            "corporate_number": "0002",
            "name": "AHC",
            "entity_type": "株式会社",
            "prefecture": "石川県", "city": "金沢市",
            "address": "上堤町1番35号",
            "capital": "1",
        }
        company = {
            "name": "アイ・オー・データ機器株式会社",
            "code": "6916",
            "hq_address": "石川県金沢市桜田町三丁目10番地",
            "address": "石川県金沢市上堤町1番35号",  # 大株主の住所
            "pbr": 0.8,
            "owner_ratio": 25.0,
            "market_cap": 30e9,
            "ceo_age": 67,
        }
        result = self._run_assessment(spc, company)
        self.assertEqual(result["tier"], TIER_HANEMAN)
        self.assertGreaterEqual(result["confidence"], 70)
        self.assertIn("tile_3_local", result["signal_ids"])

    # ================================================================
    # 倍満（60-70%）: 複合シグナル
    # ================================================================

    def test_baiman_composite_signals(self):
        """都心住所一致＋代表者一致＋買収目的＋ファンダメンタル整合"""
        spc = {
            "corporate_number": "0003",
            "name": "テストインベストメント",
            "entity_type": "合同会社",
            "representative": "鈴木一郎",
            "prefecture": "東京都", "city": "千代田区",
            "address": "丸の内1-1-1",
            "purpose": "有価証券の取得及び保有",
        }
        company = {
            "name": "テスト電機株式会社",
            "code": "3333",
            "officers": ["鈴木一郎", "田中次郎"],
            "address": "東京都千代田区丸の内1-1-1",
            "pbr": 0.5,
            "owner_ratio": 30.0,
            "market_cap": 40e9,
            "ceo_age": 70,
        }
        result = self._run_assessment(spc, company)
        # 代表者一致があるので役満になるはず（第2牌が最強）
        self.assertIn(result["tier"], [TIER_YAKUMAN, TIER_BAIMAN])
        self.assertGreaterEqual(result["confidence"], 60)

    # ================================================================
    # 満貫（40-60%）: 買収目的SPC＋ファンダメンタル整合
    # ================================================================

    def test_mangan_acquisition_purpose_with_fundamentals(self):
        """買収目的SPCがファンダメンタル条件と整合"""
        spc = {
            "corporate_number": "0004",
            "name": "ABCキャピタル",
            "entity_type": "合同会社",
            "purpose": "有価証券の取得、保有及び管理、企業の買収に関する業務",
            "prefecture": "東京都", "city": "千代田区",
        }
        company = {
            "name": "中堅製造株式会社",
            "code": "4444",
            "pbr": 0.6,
            "owner_ratio": 40.0,
            "market_cap": 25e9,
            "ceo_age": 73,
        }
        result = self._run_assessment(spc, company)
        self.assertIn(result["tier"], [TIER_MANGAN, TIER_BAIMAN])
        self.assertGreaterEqual(result["confidence"], 40)
        self.assertIn("tile_4", result["signal_ids"])
        self.assertIn("tile_5", result["signal_ids"])

    # ================================================================
    # 三翻（20-40%）: SPC検出のみ、ターゲット不明
    # ================================================================

    def test_sanhan_bcj_sequential_no_target(self):
        """BCJ-連番検出のみ: Bainが動いているがターゲット不明

        INFORICHのケースに相当。BCJ-98等の連番で
        「Bainが何か動いている」とわかるが、どの上場企業かは不明。
        """
        spc = {
            "corporate_number": "0005",
            "name": "BCJ-99",
            "entity_type": "株式会社",
            "prefecture": "東京都", "city": "千代田区",
            "address": "丸の内1-9-2",
        }
        # 企業情報なし（ターゲット不明）
        result = self._run_assessment(spc, company_data=None)
        self.assertEqual(result["tier"], TIER_SANHAN)
        self.assertGreaterEqual(result["confidence"], 20)
        self.assertLessEqual(result["confidence"], 40)

    def test_sanhan_generic_holdings_spc(self):
        """汎用的なホールディングスSPC、ターゲット不明"""
        spc = {
            "corporate_number": "0006",
            "name": "ストラテジックパートナーズ",
            "entity_type": "合同会社",
            "prefecture": "東京都", "city": "港区",
        }
        result = self._run_assessment(spc, company_data=None)
        self.assertEqual(result["tier"], TIER_SANHAN)

    # ================================================================
    # 一翻（20%未満）: シグナル不十分
    # ================================================================

    def test_iihan_no_signals(self):
        """SPC候補にもならない一般法人"""
        spc = {
            "corporate_number": "0007",
            "name": "田中商事",
            "entity_type": "株式会社",
            "prefecture": "大阪府", "city": "大阪市",
        }
        result = self._run_assessment(spc, company_data=None)
        self.assertEqual(result["tier"], TIER_IIHAN)
        self.assertLess(result["confidence"], 20)

    # ================================================================
    # オーナー家主導 vs PEファンド主導の違い
    # ================================================================

    def test_owner_led_higher_confidence(self):
        """オーナー家主導型は代表者一致で役満が成立しやすい

        PEファンド主導型はノミニー取締役で第2牌が引けないことが多い。
        本当の役満はオーナー家主導型でしか成立しない。
        """
        # オーナー家主導型
        spc_owner = {
            "corporate_number": "0008a",
            "name": "上原ホールディングス",
            "entity_type": "株式会社",
            "representative": "上原茂",
            "purpose": "株式の取得及び保有",
            "prefecture": "東京都", "city": "豊島区",
        }
        company = {
            "name": "テスト製薬株式会社", "code": "9876",
            "officers": ["上原茂"], "owner_name": "上原茂",
            "pbr": 0.7, "owner_ratio": 50.0, "market_cap": 100e9, "ceo_age": 65,
        }
        result_owner = self._run_assessment(spc_owner, company)

        # PEファンド主導型（ノミニー取締役で第2牌が引けない）
        spc_pe = {
            "corporate_number": "0008b",
            "name": "BCJ-100",
            "entity_type": "株式会社",
            "representative": "杉本勇次",  # Bainのパートナー
            "prefecture": "東京都", "city": "千代田区",
            "address": "丸の内1-9-2",
        }
        result_pe = self._run_assessment(spc_pe, company)

        # オーナー家主導の方が確信度が高い
        self.assertGreater(result_owner["confidence"], result_pe["confidence"])

    # ================================================================
    # シグナル検出の正確性テスト
    # ================================================================

    def test_tile_4_purpose_detection(self):
        """第4牌: 事業目的チェックの検出"""
        spc = {
            "corporate_number": "0009",
            "name": "テストキャピタル",
            "entity_type": "合同会社",
            "purpose": "有価証券の取得、保有及び管理並びにこれらに付帯する一切の業務",
        }
        spc = self.detector.analyze(spc)
        self.assertIn("買収目的SPC", spc["notes"])

    def test_tile_5_fundamental_two_or_more(self):
        """第5牌: ファンダメンタル条件2つ以上で検出"""
        company_strong = {
            "pbr": 0.5, "owner_ratio": 35.0,
            "market_cap": 20e9, "ceo_age": 70,
        }
        self.assertTrue(self.assessor._has_fundamental_match(company_strong))

        company_weak = {"pbr": 1.5, "market_cap": 1000e9}
        self.assertFalse(self.assessor._has_fundamental_match(company_weak))

    def test_local_address_detection(self):
        """地方住所の判定"""
        spc_local = {"prefecture": "石川県", "city": "金沢市"}
        self.assertTrue(self.assessor._is_local_address_match(spc_local))

        spc_tokyo = {"prefecture": "東京都", "city": "千代田区"}
        self.assertFalse(self.assessor._is_local_address_match(spc_tokyo))

        spc_tama = {"prefecture": "東京都", "city": "八王子市"}
        self.assertTrue(self.assessor._is_local_address_match(spc_tama))


class TestConfidenceSummary(unittest.TestCase):
    """確信度評価のサマリ出力テスト"""

    def test_full_pipeline_demo(self):
        """フルパイプラインのデモ（結果の整合性確認）"""
        detector = SpcDetector()
        matcher = MboMatcher.__new__(MboMatcher)
        assessor = ConfidenceAssessor()

        # 大正製薬相当のケース
        spc = detector.analyze({
            "corporate_number": "demo_001",
            "name": "大手門株式会社",
            "entity_type": "株式会社",
            "representative": "上原茂",
            "purpose": "有価証券の取得、保有及び管理",
            "prefecture": "東京都", "city": "豊島区",
        })

        company = {
            "name": "大正製薬ホールディングス株式会社",
            "code": "4581",
            "officers": ["上原茂", "上原明"],
            "pbr": 0.7,
            "owner_ratio": 52.0,
            "market_cap": 500e9,
            "ceo_age": 68,
        }

        score, reasons = matcher._calculate_match_score(spc, company)
        result = assessor.assess(spc, company, {"score": score, "reasons": reasons})

        self.assertEqual(result["tier"], TIER_YAKUMAN)
        self.assertIn("tile_1", result["signal_ids"])
        self.assertIn("tile_2", result["signal_ids"])
        self.assertIn("assessment", result)
        self.assertIn("大手門", result["assessment"])


if __name__ == "__main__":
    unittest.main()
