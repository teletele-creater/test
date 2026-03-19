"""
MBOマッチングエンジン
SPC候補と上場企業を紐付け、MBO可能性を分析する
"""
import json
import re
from difflib import SequenceMatcher

from src.database.models import Database
from src.utils.logger import setup_logger

logger = setup_logger("mbo_matcher")


class MboMatcher:
    """SPC候補と上場企業のマッチング分析"""

    def __init__(self, db: Database = None):
        self.db = db or Database()

    def run_matching(self) -> list:
        """
        全SPC候補と上場企業のマッチングを実行する

        Returns:
            MBO候補のリスト
        """
        spc_candidates = self.db.get_spc_candidates(min_score=0.3)
        listed_companies = self.db.get_listed_companies()

        if not spc_candidates:
            logger.info("No SPC candidates to match")
            return []

        if not listed_companies:
            logger.warning("No listed companies data available")
            return []

        logger.info(
            f"Matching {len(spc_candidates)} SPC candidates "
            f"against {len(listed_companies)} listed companies"
        )

        mbo_candidates = []

        for spc in spc_candidates:
            matches = self._find_matches(spc, listed_companies)
            for match in matches:
                candidate = {
                    "spc_corporate_number": spc["corporate_number"],
                    "listed_company_code": match["code"],
                    "match_score": match["score"],
                    "match_reasons": json.dumps(match["reasons"], ensure_ascii=False),
                    "status": "detected",
                    "notes": f"SPC: {spc['name']} -> Listed: {match['name']}",
                }
                self.db.add_mbo_candidate(candidate)
                mbo_candidates.append(candidate)
                logger.info(
                    f"MBO candidate: {spc['name']} -> {match['name']} "
                    f"(score={match['score']:.3f})"
                )

        logger.info(f"Found {len(mbo_candidates)} MBO candidate matches")
        return mbo_candidates

    def _find_matches(self, spc: dict, listed_companies: list) -> list:
        """SPC候補と上場企業のマッチングを実行"""
        matches = []

        for company in listed_companies:
            score, reasons = self._calculate_match_score(spc, company)
            if score >= 0.2:
                matches.append({
                    "code": company["code"],
                    "name": company["name"],
                    "score": round(score, 3),
                    "reasons": reasons,
                })

        # スコア降順でソート
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches[:3]  # 上位3件まで

    def _calculate_match_score(self, spc: dict, company: dict) -> tuple:
        """マッチングスコアを計算"""
        score = 0.0
        reasons = []

        # 1. 名称の類似度チェック
        name_score, name_reason = self._check_name_similarity(spc, company)
        score += name_score
        if name_reason:
            reasons.append(name_reason)

        # 2. 住所の一致チェック
        addr_score, addr_reason = self._check_address_match(spc, company)
        score += addr_score
        if addr_reason:
            reasons.append(addr_reason)

        # 3. MBO対象になりやすい企業特性
        profile_score, profile_reasons = self._check_company_profile(company)
        score += profile_score
        reasons.extend(profile_reasons)

        return min(score, 1.0), reasons

    # SPC名から除去するサフィックス（類似度計算用）
    _SPC_SUFFIXES = re.compile(
        r'(合同会社|株式会社|ホールディングス|HD|インベストメント|'
        r'キャピタル|パートナーズ|アドバイザリー|アクイジション|'
        r'Holdings|Investment|Capital|Partners|Acquisition|Advisory|'
        r'合同|LLC|Inc\.?|Co\.?,?\s*Ltd\.?)',
        re.IGNORECASE,
    )

    def _normalize_name(self, name: str) -> str:
        """比較用に法人名を正規化（サフィックス除去）"""
        cleaned = self._SPC_SUFFIXES.sub('', name).strip()
        # 全角→半角の基本変換
        cleaned = cleaned.replace('　', ' ').strip()
        return cleaned if cleaned else name

    def _check_name_similarity(self, spc: dict, company: dict) -> tuple:
        """SPC名と上場企業名の類似度を確認"""
        spc_name = spc.get("name", "")
        company_name = company.get("name", "")

        if not spc_name or not company_name:
            return 0.0, ""

        # 企業名からも法人格を除去
        clean_company = re.sub(r'(株式会社|（株）|ホールディングス)', '', company_name).strip()

        # 1. SPC名に企業名が直接含まれる
        if clean_company and len(clean_company) >= 2 and clean_company in spc_name:
            return 0.5, f"SPC名に企業名'{clean_company}'を含む"

        # 2. 正規化した名前同士で類似度チェック
        norm_spc = self._normalize_name(spc_name)
        norm_company = self._normalize_name(company_name)

        if norm_spc and norm_company:
            # 正規化後に一方が他方を含む
            if len(norm_company) >= 2 and norm_company in norm_spc:
                return 0.45, f"正規化名で企業名'{norm_company}'を含む"
            if len(norm_spc) >= 2 and norm_spc in norm_company:
                return 0.45, f"正規化名でSPC名'{norm_spc}'を含む"

            # 文字列類似度
            similarity = SequenceMatcher(None, norm_spc, norm_company).ratio()
            if similarity >= 0.6:
                return 0.35, f"正規化名の類似度が高い({similarity:.2f})"
            elif similarity >= 0.4:
                return 0.2, f"正規化名がやや類似({similarity:.2f})"

        # 3. 元の名前でもフォールバック
        similarity = SequenceMatcher(None, spc_name, company_name).ratio()
        if similarity >= 0.5:
            return 0.3, f"名称類似度が高い({similarity:.2f})"
        elif similarity >= 0.3:
            return 0.1, f"名称にやや類似({similarity:.2f})"

        return 0.0, ""

    @staticmethod
    def _check_address_match(spc: dict, company: dict) -> tuple:
        """住所の一致チェック"""
        # 現在は簡易チェック（法人番号から住所を突合）
        # 将来的にはより詳細な住所マッチングを実装
        return 0.0, ""

    @staticmethod
    def _check_company_profile(company: dict) -> tuple:
        """MBO対象になりやすい企業特性チェック"""
        score = 0.0
        reasons = []

        # 低PBR
        pbr = company.get("pbr")
        if pbr is not None and pbr > 0:
            if pbr < 0.5:
                score += 0.15
                reasons.append(f"PBR極端に低い({pbr:.2f})")
            elif pbr < 1.0:
                score += 0.1
                reasons.append(f"PBR1倍割れ({pbr:.2f})")

        # オーナー持株比率
        owner_ratio = company.get("owner_ratio")
        if owner_ratio is not None:
            if owner_ratio >= 30:
                score += 0.15
                reasons.append(f"オーナー持株比率高い({owner_ratio:.1f}%)")
            elif owner_ratio >= 20:
                score += 0.1
                reasons.append(f"オーナー持株比率({owner_ratio:.1f}%)")

        # 時価総額（中小型株がMBO対象になりやすい）
        market_cap = company.get("market_cap")
        if market_cap is not None and market_cap > 0:
            cap_billion = market_cap / 1_000_000_000
            if cap_billion < 50:
                score += 0.1
                reasons.append(f"小型株(時価総額{cap_billion:.0f}億円)")
            elif cap_billion < 200:
                score += 0.05
                reasons.append(f"中型株(時価総額{cap_billion:.0f}億円)")

        return score, reasons
