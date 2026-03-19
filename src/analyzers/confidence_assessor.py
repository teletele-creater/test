"""
MBO確信度ティア評価エンジン（「役満」システム）

5つのシグナル（牌）の組み合わせからMBOの確信度を段階評価する。
麻雀の役になぞらえ、シグナルの組み合わせパターンごとに
確信度ティアを判定する。

=== 5つの牌 ===
第1牌: SPC設立の検出（必須）
    → 国税庁法人番号公表サイトで新規法人を検出
第2牌: SPC代表者と対象企業の役員・大株主の一致（最強シグナル）
    → 登記情報提供サービスで代表者確認、役員四季報・有報と照合
第3牌: SPCの登記住所が対象企業の大株主 or 本社と地理的に紐づく
    → 地方都市の特定住所一致は特に強力（I-Oデータの金沢市のケース）
第4牌: SPCの事業目的が「株式の取得・保有・管理」
    → 不動産SPCや証券化SPCとの識別が可能
第5牌: ファンダメンタル条件との整合
    → PBR1倍割れ、オーナー経営者、後継者問題等

=== 確信度ティア ===
役満（90%超）: 第1＋第2 → SPC代表者=上場企業役員。MBO以外の説明がほぼない
跳満（70-80%）: 第1＋第3（地方住所一致）→ 偶然の可能性が極めて低い
倍満（60-70%）: 第1＋第2or3＋第4＋第5 → 複合シグナルの高確度パターン
満貫（40-60%）: 第1＋第4＋第5 → 買収目的SPC＋ファンダメンタル整合
三翻（20-40%）: 第1のみ（BCJ連番等）→ ファンド活動は確認だがターゲット不明
一翻（20%未満）: SPC検出のみ、紐付け情報なし
"""
import re
from src.utils.logger import setup_logger

logger = setup_logger("confidence_assessor")

# 確信度ティア定義
TIER_YAKUMAN = "役満"       # 90%超
TIER_HANEMAN = "跳満"       # 70-80%
TIER_BAIMAN = "倍満"        # 60-70%
TIER_MANGAN = "満貫"        # 40-60%
TIER_SANHAN = "三翻"        # 20-40%
TIER_IIHAN = "一翻"         # 20%未満


class ConfidenceAssessor:
    """MBO確信度のティア評価を行う

    SpcDetectorとMboMatcherの結果を統合し、
    5つのシグナル（牌）の有無から確信度ティアを判定する。
    """

    def assess(self, spc: dict, company: dict = None, match_result: dict = None) -> dict:
        """確信度ティアを評価する

        Args:
            spc: SpcDetectorで分析済みの法人情報dict
                (spc_score, notes, is_spc_candidate等を含む)
            company: マッチング対象の上場企業dict（オプション）
            match_result: MboMatcherの_calculate_match_scoreの結果（オプション）
                {"score": float, "reasons": list}

        Returns:
            確信度評価dict:
                tier: ティア名（役満/跳満/倍満/満貫/三翻/一翻）
                confidence: 確信度（0-100%）
                signals: 検出された牌のリスト
                assessment: 人間可読な評価文
        """
        signals = self._detect_signals(spc, company, match_result)

        has = {s["id"] for s in signals}

        # === ティア判定ロジック ===

        # 役満: 第1＋第2（SPC検出＋代表者一致）
        if "tile_1" in has and "tile_2" in has:
            confidence = 95 if "tile_4" in has else 90
            tier = TIER_YAKUMAN
            assessment = self._build_yakuman_assessment(spc, company, signals)

        # 跳満: 第1＋第3で地方住所一致
        elif "tile_1" in has and "tile_3_local" in has:
            confidence = 80 if "tile_4" in has else 75
            tier = TIER_HANEMAN
            assessment = self._build_haneman_assessment(spc, company, signals)

        # 倍満: 複合シグナル（第1＋(第2or第3)＋第4＋第5）
        elif ("tile_1" in has
              and ("tile_2" in has or "tile_3" in has)
              and "tile_4" in has
              and "tile_5" in has):
            confidence = 65
            tier = TIER_BAIMAN
            assessment = self._build_baiman_assessment(signals)

        # 満貫: 第1＋第4＋第5（買収目的SPC＋ファンダメンタル整合）
        elif "tile_1" in has and "tile_4" in has and "tile_5" in has:
            confidence = 50
            tier = TIER_MANGAN
            assessment = self._build_mangan_assessment(signals)

        # 満貫: 第1＋第3（都心住所一致、地方ではない）
        elif "tile_1" in has and "tile_3" in has:
            confidence = 45
            tier = TIER_MANGAN
            assessment = "SPCと上場企業の住所が同エリア。可能性あるがターゲット確定には追加情報が必要"

        # 三翻: 第1のみ（ファンド活動検出だがターゲット不明）
        elif "tile_1" in has:
            confidence = 30
            tier = TIER_SANHAN
            assessment = "SPC検出のみ。ファンド活動の可能性はあるがターゲット企業の特定は困難"

        # 一翻: シグナル不十分
        else:
            confidence = 10
            tier = TIER_IIHAN
            assessment = "有意なシグナルなし"

        result = {
            "tier": tier,
            "confidence": confidence,
            "signals": signals,
            "signal_ids": sorted(has),
            "assessment": assessment,
        }

        logger.info(
            f"Confidence assessment: {tier}({confidence}%) "
            f"signals={sorted(has)} "
            f"spc={spc.get('name', 'N/A')} "
            f"company={company.get('name', 'N/A') if company else 'N/A'}"
        )

        return result

    def _detect_signals(self, spc: dict, company: dict = None,
                        match_result: dict = None) -> list:
        """5つの牌（シグナル）の検出状況を判定"""
        signals = []

        # === 第1牌: SPC設立の検出 ===
        if spc.get("is_spc_candidate") or (spc.get("spc_score", 0) >= 0.3):
            signals.append({
                "id": "tile_1",
                "name": "第1牌: SPC検出",
                "detail": f"SPC候補スコア {spc.get('spc_score', 0):.3f}",
            })

        # === 第2牌: SPC代表者と対象企業役員の一致 ===
        if match_result and match_result.get("reasons"):
            for reason in match_result["reasons"]:
                if "代表者" in reason and ("一致" in reason or "マッチ" in reason):
                    signals.append({
                        "id": "tile_2",
                        "name": "第2牌: 代表者一致（最強シグナル）",
                        "detail": reason,
                    })
                    break

        # === 第3牌: SPCの住所が対象企業の大株主・本社と紐づく ===
        if match_result and match_result.get("reasons"):
            for reason in match_result["reasons"]:
                if "所在地" in reason or "住所" in reason:
                    # 地方住所かどうかを判定
                    is_local = self._is_local_address_match(spc, company)
                    tile_id = "tile_3_local" if is_local else "tile_3"
                    signals.append({
                        "id": tile_id,
                        "name": f"第3牌: 住所紐付け{'（地方一致・高確度）' if is_local else ''}",
                        "detail": reason,
                    })
                    break

        # === 第4牌: 事業目的が「株式の取得・保有・管理」 ===
        notes = spc.get("notes", "")
        purpose = spc.get("purpose", "") or ""
        if "買収目的SPC" in notes or self._has_acquisition_purpose(purpose):
            signals.append({
                "id": "tile_4",
                "name": "第4牌: 買収目的の事業目的",
                "detail": f"目的欄: {purpose[:60]}..." if len(purpose) > 60 else f"目的欄: {purpose}",
            })

        # === 第5牌: ファンダメンタル条件との整合 ===
        if company and self._has_fundamental_match(company, match_result):
            signals.append({
                "id": "tile_5",
                "name": "第5牌: ファンダメンタル整合",
                "detail": self._summarize_fundamentals(company),
            })

        return signals

    @staticmethod
    def _is_local_address_match(spc: dict, company: dict = None) -> bool:
        """SPC住所が地方（東京23区以外）かつ企業と紐づくか判定

        地方住所での一致は偶然の可能性が極めて低いため「跳満」相当。
        I-Oデータ（石川県金沢市）のケースが典型。
        """
        prefecture = spc.get("prefecture", "") or ""
        city = spc.get("city", "") or ""

        # 東京23区は「地方」扱いしない（PEオフィスが集中するため偶然一致しうる）
        tokyo_central = [
            "千代田区", "中央区", "港区", "新宿区", "渋谷区",
            "文京区", "台東区", "墨田区", "江東区", "品川区",
            "目黒区", "大田区", "世田谷区", "中野区", "杉並区",
            "豊島区", "北区", "荒川区", "板橋区", "練馬区",
            "足立区", "葛飾区", "江戸川区",
        ]
        if prefecture == "東京都" and any(ward in city for ward in tokyo_central):
            return False

        # 東京都以外 or 東京都の市部 → 地方扱い
        return True

    @staticmethod
    def _has_acquisition_purpose(purpose: str) -> bool:
        """事業目的に買収関連のキーワードが含まれるか"""
        if not purpose:
            return False
        keywords = [
            "有価証券の取得", "有価証券の保有", "株式の取得",
            "株式の保有", "株式の管理", "企業の買収", "企業買収",
            "公開買付", "会社の経営管理", "子会社の経営管理",
            "議決権の取得", "対象会社の事業活動",
        ]
        return any(kw in purpose for kw in keywords)

    @staticmethod
    def _has_fundamental_match(company: dict, match_result: dict = None) -> bool:
        """ファンダメンタル条件が2つ以上合致するか"""
        hits = 0
        if company.get("pbr") is not None and company["pbr"] < 1.0:
            hits += 1
        if company.get("owner_ratio") is not None and company["owner_ratio"] >= 20:
            hits += 1
        if company.get("market_cap") is not None and company["market_cap"] < 200e9:
            hits += 1
        if company.get("ceo_age") is not None and company["ceo_age"] >= 65:
            hits += 1
        if company.get("has_activist"):
            hits += 1
        if company.get("net_cash") and company.get("market_cap"):
            if company["net_cash"] / company["market_cap"] >= 0.3:
                hits += 1
        return hits >= 2

    @staticmethod
    def _summarize_fundamentals(company: dict) -> str:
        """ファンダメンタル情報のサマリ"""
        parts = []
        if company.get("pbr") is not None:
            parts.append(f"PBR {company['pbr']:.2f}")
        if company.get("owner_ratio") is not None:
            parts.append(f"オーナー比率{company['owner_ratio']:.0f}%")
        if company.get("ceo_age") is not None:
            parts.append(f"CEO {company['ceo_age']}歳")
        if company.get("market_cap") is not None:
            b = company["market_cap"] / 1e9
            parts.append(f"時価総額{b:.0f}億")
        if company.get("has_activist"):
            parts.append("アクティビスト有")
        return ", ".join(parts) if parts else "データなし"

    @staticmethod
    def _build_yakuman_assessment(spc, company, signals):
        spc_name = spc.get("name", "?")
        co_name = company.get("name", "?") if company else "?"
        return (
            f"【役満】SPC「{spc_name}」の代表者が「{co_name}」の役員/オーナーと一致。"
            f"MBO以外の合理的説明がほぼ存在しない。確信度90%超"
        )

    @staticmethod
    def _build_haneman_assessment(spc, company, signals):
        pref = spc.get("prefecture", "")
        city = spc.get("city", "")
        return (
            f"【跳満】SPC住所が地方（{pref}{city}）で対象企業と紐付く。"
            f"都心PEオフィスではなく地方住所での一致は偶然の可能性が極めて低い。確信度70-80%"
        )

    @staticmethod
    def _build_baiman_assessment(signals):
        names = [s["name"] for s in signals]
        return f"【倍満】複合シグナル: {', '.join(names)}。複数の独立したシグナルが整合。確信度60-70%"

    @staticmethod
    def _build_mangan_assessment(signals):
        return "【満貫】買収目的SPCかつファンダメンタル条件が整合。可能性は高いがターゲット確定には追加調査が必要"
