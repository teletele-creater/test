"""
SPC（特別目的会社）検出エンジン
新規設立法人からMBO用SPCの可能性がある法人を検出する
"""
import re
from config.settings import (
    SPC_NAME_PATTERNS, SPC_ENTITY_TYPES, PE_FUND_KEYWORDS,
    FALSE_POSITIVE_KEYWORDS, FALSE_POSITIVE_PURPOSE_KEYWORDS,
    FUND_SPECIFIC_SPC_PATTERNS, PE_OFFICE_ADDRESSES,
)
from src.utils.logger import setup_logger

logger = setup_logger("spc_detector")


class SpcDetector:
    """SPC候補を検出するアナライザー"""

    def __init__(self):
        self.name_patterns = SPC_NAME_PATTERNS
        self.entity_types = SPC_ENTITY_TYPES
        self.pe_keywords = PE_FUND_KEYWORDS
        self.fp_keywords = FALSE_POSITIVE_KEYWORDS
        self.fp_purpose_keywords = FALSE_POSITIVE_PURPOSE_KEYWORDS
        self.fund_spc_patterns = [
            (re.compile(pat), desc) for pat, desc in FUND_SPECIFIC_SPC_PATTERNS
        ]
        self.pe_office_addresses = PE_OFFICE_ADDRESSES

    def analyze(self, corporation: dict) -> dict:
        """
        法人情報を分析し、SPC候補スコアを算出する

        Args:
            corporation: 法人情報dict

        Returns:
            スコアと理由を付与した法人情報
        """
        score = 0.0
        reasons = []

        # 1. 法人形態チェック（合同会社は高スコア）
        entity_score, entity_reason = self._check_entity_type(corporation)
        score += entity_score
        if entity_reason:
            reasons.append(entity_reason)

        # 2. 法人名パターンチェック
        name_score, name_reasons = self._check_name_patterns(corporation)
        score += name_score
        reasons.extend(name_reasons)

        # 3. ファンド固有SPC命名パターンチェック（BCJ-連番等）
        fund_score, fund_reason = self._check_fund_specific_pattern(corporation)
        score += fund_score
        if fund_reason:
            reasons.append(fund_reason)

        # 4. PEファンド関連チェック
        pe_score, pe_reason = self._check_pe_fund_relation(corporation)
        score += pe_score
        if pe_reason:
            reasons.append(pe_reason)

        # 5. 住所チェック（PEオフィス・法律事務所 + 都心エリア）
        addr_score, addr_reason = self._check_address(corporation)
        score += addr_score
        if addr_reason:
            reasons.append(addr_reason)

        # 6. 資本金チェック
        cap_score, cap_reason = self._check_capital(corporation)
        score += cap_score
        if cap_reason:
            reasons.append(cap_reason)

        # 7. 偽陽性フィルタ（不動産・太陽光等を減点）
        fp_penalty, fp_reason = self._check_false_positive(corporation)
        score += fp_penalty  # 負の値
        if fp_reason:
            reasons.append(fp_reason)

        # スコアを0-1に正規化
        score = max(min(score, 1.0), 0.0)

        corporation["spc_score"] = round(score, 3)
        corporation["is_spc_candidate"] = 1 if score >= 0.3 else 0
        corporation["notes"] = "; ".join(reasons) if reasons else ""

        if score >= 0.3:
            logger.info(
                f"SPC candidate detected: {corporation.get('name')} "
                f"(score={score:.3f}, reasons={reasons})"
            )

        return corporation

    def analyze_batch(self, corporations: list) -> list:
        """複数法人を一括分析"""
        results = [self.analyze(corp) for corp in corporations]
        candidates = [r for r in results if r.get("is_spc_candidate")]
        logger.info(f"Analyzed {len(corporations)} corps, found {len(candidates)} SPC candidates")
        return results

    def _check_entity_type(self, corp: dict) -> tuple:
        """法人形態チェック"""
        entity_type = corp.get("entity_type", "")
        if entity_type == "合同会社":
            return 0.25, "合同会社（MBO-SPCの典型的な法人形態）"
        elif entity_type in self.entity_types:
            return 0.05, f"法人形態: {entity_type}"
        return 0.0, ""

    def _check_name_patterns(self, corp: dict) -> tuple:
        """法人名のSPCパターンチェック"""
        name = corp.get("name", "")
        if not name:
            return 0.0, []

        score = 0.0
        reasons = []

        for pattern in self.name_patterns:
            if pattern.lower() in name.lower():
                score += 0.15
                reasons.append(f"名称に'{pattern}'を含む")

        # 英語名のみの法人（SPCに多い）
        if re.match(r'^[A-Za-z0-9\s\-\.&]+$', name):
            score += 0.1
            reasons.append("英語名のみの法人")

        # 大文字アルファベット略称（TBJH合同会社、BCJ-78、PSMホールディングス等）
        # MBO SPCは意味不明な略称を使うことが多い
        clean_name = re.sub(
            r'(合同会社|株式会社|ホールディングス|HD|インベストメント|キャピタル|パートナーズ)',
            '', name,
        ).strip()
        if re.match(r'^[A-Z]{2,6}(\s|$|[\-\d])', clean_name):
            score += 0.15
            reasons.append(f"アルファベット略称法人名('{clean_name}')")

        # 極端に短い名前や汎用的な名前
        if len(name) <= 5 and any(p.lower() in name.lower() for p in ["HD", "合同"]):
            score += 0.05
            reasons.append("短い汎用名称")

        return min(score, 0.4), reasons

    def _check_fund_specific_pattern(self, corp: dict) -> tuple:
        """ファンド固有のSPC命名パターン検出（BCJ-連番、エムキャップ○号等）"""
        name = corp.get("name", "") or ""
        for pattern, description in self.fund_spc_patterns:
            if pattern.search(name):
                return 0.4, f"ファンド固有SPC: {description}"
        return 0.0, ""

    def _check_pe_fund_relation(self, corp: dict) -> tuple:
        """PEファンド関連チェック"""
        text = f"{corp.get('name', '')} {corp.get('purpose', '')} {corp.get('representative', '')}"
        for keyword in self.pe_keywords:
            if keyword.lower() in text.lower():
                return 0.3, f"PEファンド関連: '{keyword}'"
        return 0.0, ""

    def _check_address(self, corp: dict) -> tuple:
        """住所チェック（PEオフィス・法律事務所の住所マッチ + 都心エリア）"""
        parts = [
            corp.get('prefecture', '') or '',
            corp.get('city', '') or '',
            corp.get('address', '') or '',
        ]
        address = " ".join(parts)
        # スペースなし版も用意（「千代田区丸の内1-9-2」形式でのマッチ用）
        address_nospace = "".join(parts)

        # 最高精度: PEファンド・M&A法律事務所の具体的住所と一致
        for pe_addr, pe_name in self.pe_office_addresses:
            if pe_addr in address or pe_addr in address_nospace:
                return 0.3, f"PE/法律事務所住所一致: {pe_name}"

        # MBO-SPCが多く登記される地域
        high_score_areas = [
            "千代田区丸の内", "千代田区大手町", "千代田区永田町",
            "千代田区紀尾井町",
            "中央区日本橋", "港区赤坂", "港区六本木", "港区虎ノ門",
        ]
        mid_score_areas = [
            "千代田区", "中央区", "港区", "新宿区", "渋谷区",
        ]

        for area in high_score_areas:
            if area in address:
                return 0.15, f"都心ビジネス街に所在({area})"

        for area in mid_score_areas:
            if area in address:
                return 0.05, f"都心部に所在({area})"

        return 0.0, ""

    def _check_false_positive(self, corp: dict) -> tuple:
        """偽陽性チェック：MBOと無関係な業種を減点"""
        name = corp.get("name", "") or ""
        purpose = corp.get("purpose", "") or ""
        text = f"{name} {purpose}".lower()

        # 法人名に偽陽性キーワードが含まれる場合
        for keyword in self.fp_keywords:
            if keyword.lower() in text:
                return -0.3, f"非MBO業種の可能性('{keyword}'を含む)"

        # 事業目的に偽陽性キーワードが含まれる場合
        for keyword in self.fp_purpose_keywords:
            if keyword.lower() in purpose.lower():
                return -0.2, f"事業目的が非MBO('{keyword}')"

        return 0.0, ""

    def _check_capital(self, corp: dict) -> tuple:
        """資本金チェック"""
        capital = corp.get("capital", "")
        if not capital:
            return 0.0, ""

        try:
            amount = int(re.sub(r'[^\d]', '', str(capital)))
            # 1円〜100万円: SPCの典型的な資本金
            if 1 <= amount <= 1_000_000:
                return 0.1, f"少額資本金({amount:,}円)"
            # 1億円以上: 本格的な買収ファンド
            elif amount >= 100_000_000:
                return 0.1, f"大型資本金({amount:,}円)"
        except (ValueError, TypeError):
            pass

        return 0.0, ""
