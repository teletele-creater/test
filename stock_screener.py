"""
株式スクリーニングエンジン

投資哲学:
  業績が成長しているのに株価が上がらず、配当利回りが高くなるラインを待つ。
  3条件すべて満たす = 異常値エントリーゾーン

ルール:
  ① 総合利回り（配当＋優待換算）が過去5年の上位10%以内
  ② 営業利益成長率 ≥ 業種平均 かつ 独自PEG < 0.75
  ③ PERが過去5年レンジの下位25%以内（異常値除外）
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

from screener_config import (
    DEFAULT_SECTOR_GROWTH_RATE,
    SECTOR_BENCHMARKS,
    SHAREHOLDER_BENEFITS,
    ScreeningRules,
)

logger = logging.getLogger(__name__)


# ============================================================
# データ取得
# ============================================================

@dataclass
class StockData:
    """スクリーニングに必要な銘柄データ"""
    symbol: str
    name: str
    sector: str
    current_price: float
    market_cap: float

    # 配当
    annual_dividend_per_share: float  # 年間配当金(1株)
    dividend_yield: float  # 配当利回り(%)
    historical_dividend_yields: pd.Series | None  # 過去の配当利回り推移

    # 優待
    shareholder_benefit_value: float  # 優待換算額(年間、1単元あたり)
    min_shares_for_benefit: int  # 優待に必要な最低株数

    # 財務
    operating_incomes: dict[str, float]  # {年度: 営業利益}
    eps_values: dict[str, float]  # {年度: EPS}
    sector_avg_op_growth: float  # 業種平均営業利益成長率(%)

    # バリュエーション
    trailing_pe: float  # 実績PER
    forward_pe: float | None  # 予想PER
    historical_pes: pd.Series | None  # 過去のPER推移

    # 株価系列（底打ち確認用、オプション）
    price_history: pd.Series | None = None  # 月次終値

    timestamp: datetime = field(default_factory=datetime.now)


def fetch_stock_data(symbol: str, rules: ScreeningRules) -> StockData:
    """yfinanceから銘柄データを取得"""
    ticker = yf.Ticker(symbol)
    info = ticker.info

    # 基本情報
    name = info.get("longName") or info.get("shortName", symbol)
    sector = info.get("sector", "Unknown")
    current_price = info.get("currentPrice") or info.get("previousClose", 0)
    market_cap = info.get("marketCap", 0)

    # 配当情報
    annual_dividend = info.get("trailingAnnualDividendRate", 0) or 0
    dividend_yield_pct = (info.get("trailingAnnualDividendYield") or 0) * 100

    # 過去の配当利回り推移を計算
    hist_yields = _calc_historical_dividend_yields(ticker, rules.yield_lookback_years)

    # 優待情報（手動データ）
    benefit_info = SHAREHOLDER_BENEFITS.get(symbol, {})
    benefit_value = benefit_info.get("value_yen", 0) if rules.include_shareholder_benefits else 0
    min_shares = benefit_info.get("min_shares", 100)

    # 財務データ（営業利益）
    operating_incomes = _extract_operating_incomes(ticker)
    eps_values = _extract_eps_values(ticker)

    # 業種平均
    sector_avg = SECTOR_BENCHMARKS.get(sector, DEFAULT_SECTOR_GROWTH_RATE)

    # PER
    trailing_pe = info.get("trailingPE", 0) or 0
    forward_pe = info.get("forwardPE")

    # 過去PER推移
    hist_pes = _calc_historical_pes(ticker, rules.per_lookback_years)

    return StockData(
        symbol=symbol,
        name=name,
        sector=sector,
        current_price=current_price,
        market_cap=market_cap,
        annual_dividend_per_share=annual_dividend,
        dividend_yield=dividend_yield_pct,
        historical_dividend_yields=hist_yields,
        shareholder_benefit_value=benefit_value,
        min_shares_for_benefit=min_shares,
        operating_incomes=operating_incomes,
        eps_values=eps_values,
        sector_avg_op_growth=sector_avg,
        trailing_pe=trailing_pe,
        forward_pe=forward_pe,
        historical_pes=hist_pes,
    )


def _calc_historical_dividend_yields(ticker: yf.Ticker, years: int) -> pd.Series | None:
    """過去N年の配当利回り推移を月次ベースで計算"""
    try:
        hist = ticker.history(period=f"{years}y")
        if hist.empty:
            return None

        dividends = ticker.dividends
        if dividends.empty:
            return None

        # 月次の終値で配当利回りを計算
        monthly_close = hist["Close"].resample("ME").last()
        # 直近12ヶ月の配当合計をrollingで計算
        monthly_divs = dividends.resample("ME").sum()
        monthly_divs = monthly_divs.reindex(monthly_close.index, fill_value=0)
        rolling_annual_div = monthly_divs.rolling(12, min_periods=1).sum()

        yields = (rolling_annual_div / monthly_close * 100).dropna()
        return yields
    except Exception as e:
        logger.warning(f"Failed to calc historical yields: {e}")
        return None


def _extract_operating_incomes(ticker: yf.Ticker) -> dict[str, float]:
    """財務諸表から営業利益を抽出"""
    result = {}
    try:
        income_stmt = ticker.income_stmt
        if income_stmt is None or income_stmt.empty:
            return result

        # yfinanceのキー名対応
        op_income_keys = ["Operating Income", "OperatingIncome", "EBIT"]
        for key in op_income_keys:
            if key in income_stmt.index:
                row = income_stmt.loc[key]
                for col in row.index:
                    year_str = col.strftime("%Y") if hasattr(col, "strftime") else str(col)
                    val = row[col]
                    if pd.notna(val):
                        result[year_str] = float(val)
                break
    except Exception as e:
        logger.warning(f"Failed to extract operating incomes: {e}")
    return result


def _extract_eps_values(ticker: yf.Ticker) -> dict[str, float]:
    """財務諸表からEPSを抽出"""
    result = {}
    try:
        income_stmt = ticker.income_stmt
        if income_stmt is None or income_stmt.empty:
            return result

        eps_keys = ["Basic EPS", "Diluted EPS", "BasicEPS", "DilutedEPS"]
        for key in eps_keys:
            if key in income_stmt.index:
                row = income_stmt.loc[key]
                for col in row.index:
                    year_str = col.strftime("%Y") if hasattr(col, "strftime") else str(col)
                    val = row[col]
                    if pd.notna(val):
                        result[year_str] = float(val)
                break
    except Exception as e:
        logger.warning(f"Failed to extract EPS: {e}")
    return result


def _calc_historical_pes(ticker: yf.Ticker, years: int) -> pd.Series | None:
    """過去N年のPER推移を月次で計算"""
    try:
        hist = ticker.history(period=f"{years}y")
        if hist.empty:
            return None

        info = ticker.info
        trailing_eps = info.get("trailingEps")
        if not trailing_eps or trailing_eps <= 0:
            return None

        # 簡易: 現在のEPSベースで過去株価からPERを逆算
        # （本来はその時点のEPSを使うべきだが、yfinanceでは取得困難）
        monthly_close = hist["Close"].resample("ME").last()
        pes = monthly_close / trailing_eps
        return pes.dropna()
    except Exception as e:
        logger.warning(f"Failed to calc historical PEs: {e}")
        return None


# ============================================================
# スクリーニングルール判定
# ============================================================

@dataclass
class RuleResult:
    """個別ルールの判定結果"""
    rule_name: str
    passed: bool
    current_value: str
    threshold: str
    detail: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class ScreeningResult:
    """スクリーニング結果"""
    symbol: str
    name: str
    sector: str
    rules: list[RuleResult]
    is_entry_zone: bool  # 異常値エントリーゾーン
    rules_passed: int
    rules_total: int
    timestamp: datetime = field(default_factory=datetime.now)

    def summary(self) -> str:
        status = "★ 異常値エントリーゾーン ★" if self.is_entry_zone else "条件未達"
        lines = [
            f"{'='*60}",
            f"[{status}] {self.name} ({self.symbol})",
            f"セクター: {self.sector}",
            f"ルール達成: {self.rules_passed}/{self.rules_total}",
            f"{'─'*60}",
        ]

        for r in self.rules:
            mark = "✅" if r.passed else "❌"
            lines.append(f"  {mark} {r.rule_name}")
            lines.append(f"     現在値: {r.current_value}  基準: {r.threshold}")
            if r.detail:
                lines.append(f"     詳細: {r.detail}")
            for w in r.warnings:
                lines.append(f"     ⚠️  {w}")

        lines.append(f"{'='*60}")
        return "\n".join(lines)


def check_rule1_yield(data: StockData, rules: ScreeningRules) -> RuleResult:
    """
    ルール①: 総合利回り（配当＋優待換算）が過去5年の上位10%以内

    「株価が下がる → 配当利回りが上がる → 過去に比べて異常に高い利回り」
    を検出する。
    """
    # 現在の総合利回り計算
    dividend_yield = data.dividend_yield

    # 優待利回りの加算
    benefit_yield = 0.0
    if data.shareholder_benefit_value > 0 and data.current_price > 0:
        investment = data.current_price * data.min_shares_for_benefit
        benefit_yield = (data.shareholder_benefit_value / investment) * 100

    total_yield = dividend_yield + benefit_yield

    # 過去の利回りレンジとの比較
    if data.historical_dividend_yields is not None and len(data.historical_dividend_yields) > 6:
        hist = data.historical_dividend_yields + benefit_yield  # 優待分を加算
        # 上位N%のしきい値を計算
        threshold_value = float(np.percentile(hist.dropna(), 100 - rules.yield_top_percentile))
        passed = total_yield >= threshold_value
        detail = (
            f"総合利回り {total_yield:.2f}% "
            f"(配当 {dividend_yield:.2f}% + 優待 {benefit_yield:.2f}%)"
            f" | 5年レンジ: {float(hist.min()):.2f}%〜{float(hist.max()):.2f}%"
            f" | 上位{rules.yield_top_percentile:.0f}%ライン: {threshold_value:.2f}%"
        )
    else:
        # 過去データなし → 配当利回り3.5%以上をフォールバック基準
        fallback_threshold = 3.5
        passed = total_yield >= fallback_threshold
        threshold_value = fallback_threshold
        detail = (
            f"総合利回り {total_yield:.2f}% "
            f"(配当 {dividend_yield:.2f}% + 優待 {benefit_yield:.2f}%)"
            f" | 過去データ不足のためフォールバック基準 {fallback_threshold}% を使用"
        )

    return RuleResult(
        rule_name="① 総合利回り（過去5年上位10%）",
        passed=passed,
        current_value=f"{total_yield:.2f}%",
        threshold=f"≥ {threshold_value:.2f}%（上位{rules.yield_top_percentile:.0f}%ライン）",
        detail=detail,
    )


def check_rule2_growth_peg(data: StockData, rules: ScreeningRules) -> RuleResult:
    """
    ルール②: 営業利益成長率 ≥ 業種平均 かつ 独自PEG < 0.75

    「業績が伸びているのに株価が安い → PEGが低い → 割安成長株」
    """
    warnings = []

    # 営業利益成長率の計算
    op_incomes = data.operating_incomes
    if len(op_incomes) < rules.op_growth_min_periods:
        return RuleResult(
            rule_name="② 営業利益成長 × PEG",
            passed=False,
            current_value="データ不足",
            threshold=f"成長率≥{data.sector_avg_op_growth:.1f}% & PEG<{rules.peg_threshold}",
            detail=f"営業利益データが{len(op_incomes)}期分しかありません（{rules.op_growth_min_periods}期以上必要）",
        )

    # 年度順にソート
    sorted_years = sorted(op_incomes.keys())
    growth_rates = []
    for i in range(1, len(sorted_years)):
        prev = op_incomes[sorted_years[i - 1]]
        curr = op_incomes[sorted_years[i]]
        if prev > 0:
            rate = (curr - prev) / prev * 100
            growth_rates.append(rate)

    if not growth_rates:
        return RuleResult(
            rule_name="② 営業利益成長 × PEG",
            passed=False,
            current_value="成長率計算不可",
            threshold=f"成長率≥{data.sector_avg_op_growth:.1f}% & PEG<{rules.peg_threshold}",
            detail="営業利益がゼロまたは負で成長率を計算できません",
        )

    # 直近N期の平均成長率
    recent_rates = growth_rates[-rules.op_growth_periods:]
    avg_growth = sum(recent_rates) / len(recent_rates)

    # EPS成長率との乖離チェック
    eps = data.eps_values
    if len(eps) >= 2:
        sorted_eps_years = sorted(eps.keys())
        eps_growth_rates = []
        for i in range(1, len(sorted_eps_years)):
            prev_eps = eps[sorted_eps_years[i - 1]]
            curr_eps = eps[sorted_eps_years[i]]
            if prev_eps > 0:
                eps_growth_rates.append((curr_eps - prev_eps) / prev_eps * 100)

        if eps_growth_rates:
            avg_eps_growth = sum(eps_growth_rates[-rules.op_growth_periods:]) / len(
                eps_growth_rates[-rules.op_growth_periods:]
            )
            divergence = abs(avg_growth - avg_eps_growth)
            if divergence > rules.eps_divergence_warn_pct:
                warnings.append(
                    f"営業利益成長率({avg_growth:.1f}%)とEPS成長率({avg_eps_growth:.1f}%)に"
                    f"{divergence:.1f}%の乖離あり → 特別損益・希薄化等を確認"
                )

    # 条件1: 営業利益成長率 ≥ 業種平均
    growth_ok = avg_growth >= data.sector_avg_op_growth

    # 独自PEG計算
    pe = data.trailing_pe
    if pe <= 0 or avg_growth <= 0:
        peg = float("inf")
    else:
        peg = pe / avg_growth

    # 条件2: PEG < 0.75
    peg_ok = peg < rules.peg_threshold

    passed = growth_ok and peg_ok

    growth_rates_str = ", ".join([f"{r:.1f}%" for r in recent_rates])
    detail = (
        f"営業利益成長率(平均): {avg_growth:.1f}% [{growth_rates_str}]"
        f" | 業種平均: {data.sector_avg_op_growth:.1f}% ({'≥' if growth_ok else '<'})"
        f" | PER: {pe:.1f} | PEG: {peg:.2f} ({'<' if peg_ok else '≥'} {rules.peg_threshold})"
    )

    return RuleResult(
        rule_name="② 営業利益成長 × PEG",
        passed=passed,
        current_value=f"成長率 {avg_growth:.1f}%, PEG {peg:.2f}",
        threshold=f"成長率≥{data.sector_avg_op_growth:.1f}% & PEG<{rules.peg_threshold}",
        detail=detail,
        warnings=warnings,
    )


def check_rule3_per_range(data: StockData, rules: ScreeningRules) -> RuleResult:
    """
    ルール③: PERが過去5年レンジの下位25%以内（異常値除外）

    「株価が下がった → PERが低い → 過去の範囲でも底値圏」
    """
    current_pe = data.trailing_pe

    if current_pe <= rules.per_outlier_min:
        return RuleResult(
            rule_name="③ PER（過去5年下位25%）",
            passed=False,
            current_value=f"PER {current_pe:.1f}",
            threshold=f"下位{rules.per_bottom_percentile:.0f}%以内",
            detail=f"現在のPER({current_pe:.1f})が異常値範囲（≤{rules.per_outlier_min}）のため判定不可",
        )

    if data.historical_pes is not None and len(data.historical_pes) > 6:
        hist_pes = data.historical_pes

        # 異常値除外
        filtered = hist_pes[
            (hist_pes > rules.per_outlier_min) & (hist_pes <= rules.per_outlier_max)
        ]

        if len(filtered) < 6:
            return RuleResult(
                rule_name="③ PER（過去5年下位25%）",
                passed=False,
                current_value=f"PER {current_pe:.1f}",
                threshold=f"下位{rules.per_bottom_percentile:.0f}%以内",
                detail="異常値除外後のデータが不足",
            )

        # 下位N%のしきい値
        threshold_value = float(np.percentile(filtered.dropna(), rules.per_bottom_percentile))
        passed = current_pe <= threshold_value

        detail = (
            f"PER {current_pe:.1f}"
            f" | 5年レンジ(異常値除外): {float(filtered.min()):.1f}〜{float(filtered.max()):.1f}"
            f" | 下位{rules.per_bottom_percentile:.0f}%ライン: {threshold_value:.1f}"
        )
    else:
        # 過去データなし → PER 12以下をフォールバック
        fallback = 12.0
        passed = 0 < current_pe <= fallback
        threshold_value = fallback
        detail = (
            f"PER {current_pe:.1f}"
            f" | 過去データ不足のためフォールバック基準 PER≤{fallback} を使用"
        )

    return RuleResult(
        rule_name="③ PER（過去5年下位25%）",
        passed=passed,
        current_value=f"PER {current_pe:.1f}",
        threshold=f"≤ {threshold_value:.1f}（下位{rules.per_bottom_percentile:.0f}%ライン）",
        detail=detail,
    )


def check_rule4_momentum(data: StockData, rules: ScreeningRules) -> RuleResult:
    """
    ルール④: 底打ち確認（モメンタムフィルター）

    「落ちるナイフを掴まない」ための安全装置。
    直近N月の最安値から一定%反発していることを確認する。
    """
    if not rules.use_momentum_filter:
        return RuleResult(
            rule_name="④ 底打ち確認（モメンタム）",
            passed=True,
            current_value="フィルター無効",
            threshold="--",
            detail="momentum_filter無効のためスキップ",
        )

    if data.price_history is None or len(data.price_history) < rules.momentum_lookback_months:
        return RuleResult(
            rule_name="④ 底打ち確認（モメンタム）",
            passed=False,
            current_value="データ不足",
            threshold=f"安値から+{rules.momentum_rebound_pct:.0f}%以上",
            detail="株価系列が不足",
        )

    recent = data.price_history.iloc[-rules.momentum_lookback_months:]
    recent_low = float(recent.min())
    current = float(recent.iloc[-1])

    if recent_low <= 0:
        return RuleResult(
            rule_name="④ 底打ち確認（モメンタム）",
            passed=False,
            current_value="異常データ",
            threshold=f"安値から+{rules.momentum_rebound_pct:.0f}%以上",
        )

    rebound_pct = (current - recent_low) / recent_low * 100
    passed = rebound_pct >= rules.momentum_rebound_pct

    # 最安値がいつだったか
    low_idx = recent.idxmin()
    low_date = low_idx.strftime("%Y-%m") if hasattr(low_idx, "strftime") else str(low_idx)

    detail = (
        f"直近{rules.momentum_lookback_months}月安値: ¥{recent_low:,.0f} ({low_date})"
        f" → 現在: ¥{current:,.0f}"
        f" | 反発: {rebound_pct:+.1f}% ({'≥' if passed else '<'} {rules.momentum_rebound_pct:.0f}%)"
    )

    return RuleResult(
        rule_name="④ 底打ち確認（モメンタム）",
        passed=passed,
        current_value=f"反発 {rebound_pct:+.1f}%",
        threshold=f"安値から+{rules.momentum_rebound_pct:.0f}%以上",
        detail=detail,
    )


# ============================================================
# メインスクリーニング
# ============================================================

def screen_stock(data: StockData, rules: ScreeningRules | None = None) -> ScreeningResult:
    """1銘柄のスクリーニングを実行"""
    if rules is None:
        rules = ScreeningRules()

    # 基本3ルール
    rule_results = [
        check_rule1_yield(data, rules),
        check_rule2_growth_peg(data, rules),
        check_rule3_per_range(data, rules),
    ]

    passed_count = sum(1 for r in rule_results if r.passed)
    is_entry = passed_count >= rules.min_rules_passed

    # ルール④: 底打ち確認（基本3条件を満たした場合のみ適用）
    if rules.use_momentum_filter:
        momentum_result = check_rule4_momentum(data, rules)
        rule_results.append(momentum_result)
        # 基本3条件クリア && 底打ち確認OK → エントリー
        if is_entry and not momentum_result.passed:
            is_entry = False

    return ScreeningResult(
        symbol=data.symbol,
        name=data.name,
        sector=data.sector,
        rules=rule_results,
        is_entry_zone=is_entry,
        rules_passed=passed_count + (1 if rules.use_momentum_filter and len(rule_results) > 3 and rule_results[3].passed else 0),
        rules_total=len(rule_results),
    )


def screen_stocks(symbols: list[str], rules: ScreeningRules | None = None) -> list[ScreeningResult]:
    """複数銘柄のスクリーニングを実行（yfinanceからデータ取得）"""
    if rules is None:
        rules = ScreeningRules()

    results = []
    for symbol in symbols:
        try:
            logger.info(f"Screening {symbol}...")
            data = fetch_stock_data(symbol, rules)
            result = screen_stock(data, rules)
            results.append(result)
            logger.info(f"  {symbol}: {result.rules_passed}/{result.rules_total} rules passed")
        except Exception as e:
            logger.error(f"Error screening {symbol}: {e}")

    # エントリーゾーン銘柄を先頭にソート
    results.sort(key=lambda r: (-r.rules_passed, r.symbol))
    return results


def print_screening_report(results: list[ScreeningResult]) -> None:
    """スクリーニング結果のレポートを出力"""
    print(f"\n{'#'*60}")
    print(f"  株式スクリーニング結果 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")

    entry_zone = [r for r in results if r.is_entry_zone]
    if entry_zone:
        print(f"\n  ★ 異常値エントリーゾーン: {len(entry_zone)}銘柄 ★\n")
    else:
        print(f"\n  エントリーゾーン該当銘柄なし\n")

    for result in results:
        print(result.summary())
        print()

    # サマリーテーブル
    print(f"\n{'─'*60}")
    print(f"{'銘柄':<12} {'名称':<20} {'①利回り':>8} {'②PEG':>8} {'③PER':>8} {'判定':>6}")
    print(f"{'─'*60}")
    for r in results:
        marks = ["✅" if rule.passed else "❌" for rule in r.rules]
        status = "★ENTRY" if r.is_entry_zone else ""
        print(f"{r.symbol:<12} {r.name[:18]:<20} {marks[0]:>8} {marks[1]:>8} {marks[2]:>8} {status:>6}")
    print(f"{'─'*60}")
