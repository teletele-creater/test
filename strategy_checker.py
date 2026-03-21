"""
戦略エントリー条件チェッカー

各戦略の条件を市場データと照合し、エントリーシグナルを判定する。
"""

import logging
from dataclasses import dataclass

from config import (
    ALL_STRATEGIES,
    STRATEGY_A,
    STRATEGY_B,
    STRATEGY_C,
    STRATEGY_D,
    StrategyConditions,
)
from market_data import MarketSnapshot

logger = logging.getLogger(__name__)


@dataclass
class ConditionResult:
    """個別条件の判定結果"""
    name: str
    met: bool
    current_value: str
    threshold: str


@dataclass
class StrategySignal:
    """戦略のエントリーシグナル"""
    strategy: StrategyConditions
    symbol: str
    is_triggered: bool
    conditions_met: int
    conditions_total: int
    condition_details: list[ConditionResult]
    snapshot: MarketSnapshot
    strength: str  # "STRONG", "MODERATE", "WEAK"

    def summary(self) -> str:
        """シグナルのサマリーを生成"""
        status = "ENTRY SIGNAL" if self.is_triggered else "NOT READY"
        lines = [
            f"{'='*50}",
            f"[{status}] {self.strategy.name_jp} ({self.symbol})",
            f"シグナル強度: {self.strength}",
            f"条件達成: {self.conditions_met}/{self.conditions_total} "
            f"(必要: {self.strategy.min_conditions_met})",
            f"{'─'*50}",
        ]

        for cond in self.condition_details:
            mark = "OK" if cond.met else "--"
            lines.append(f"  [{mark}] {cond.name}: {cond.current_value} (基準: {cond.threshold})")

        lines.extend([
            f"{'─'*50}",
            f"現在値: ${self.snapshot.price:.2f}",
            f"VIX: {self.snapshot.vix:.1f}",
            f"IV Rank: {self.snapshot.iv_rank:.1f}%",
            f"RSI(14): {self.snapshot.rsi:.1f}",
            f"IV/HV比率: {self.snapshot.iv_hv_ratio:.2f}",
        ])

        if self.is_triggered:
            lines.extend([
                f"{'─'*50}",
                f"推奨アクション:",
                f"  デルタ: {self.strategy.target_delta}",
                f"  DTE: {self.strategy.dte_min}-{self.strategy.dte_max}日",
                f"  利確: クレジットの{self.strategy.profit_target_pct:.0f}%",
                f"  損切: クレジットの{self.strategy.stop_loss_multiplier:.0f}倍",
                f"  強制決済: 残り{self.strategy.exit_dte} DTE",
                f"  期待勝率: {self.strategy.win_rate}",
                f"  必要証拠金: {self.strategy.bpr_range}",
            ])

        lines.append(f"{'='*50}")
        return "\n".join(lines)


def check_strategy(strategy: StrategyConditions, snapshot: MarketSnapshot) -> StrategySignal:
    """戦略の全条件をチェックし、シグナルを生成"""
    conditions: list[ConditionResult] = []

    # IV Rank条件
    if strategy.ivr_min is not None:
        conditions.append(ConditionResult(
            name="IV Rank",
            met=snapshot.iv_rank >= strategy.ivr_min,
            current_value=f"{snapshot.iv_rank:.1f}%",
            threshold=f">= {strategy.ivr_min:.0f}%",
        ))

    if strategy.ivr_max is not None:
        conditions.append(ConditionResult(
            name="IV Rank (上限)",
            met=snapshot.iv_rank <= strategy.ivr_max,
            current_value=f"{snapshot.iv_rank:.1f}%",
            threshold=f"<= {strategy.ivr_max:.0f}%",
        ))

    # VIX条件
    if strategy.vix_min is not None:
        vix_value = snapshot.nikkei_vi if snapshot.nikkei_vi and "N225" in snapshot.symbol else snapshot.vix
        conditions.append(ConditionResult(
            name="VIX/日経VI",
            met=vix_value >= strategy.vix_min,
            current_value=f"{vix_value:.1f}",
            threshold=f">= {strategy.vix_min:.0f}",
        ))

    # VIX低下中（アイアンコンドル用）
    if strategy.vix_declining:
        conditions.append(ConditionResult(
            name="VIXスパイク低下中",
            met=snapshot.vix_declining,
            current_value="Yes" if snapshot.vix_declining else "No",
            threshold="VIXがピークから低下中",
        ))

    # RSI条件（プット売り）
    if strategy.rsi_max is not None:
        conditions.append(ConditionResult(
            name="RSI (売られすぎ)",
            met=snapshot.rsi <= strategy.rsi_max,
            current_value=f"{snapshot.rsi:.1f}",
            threshold=f"<= {strategy.rsi_max:.0f}",
        ))

    # RSI条件（コール売り）
    if strategy.rsi_min is not None:
        conditions.append(ConditionResult(
            name="RSI (買われすぎ)",
            met=snapshot.rsi >= strategy.rsi_min,
            current_value=f"{snapshot.rsi:.1f}",
            threshold=f">= {strategy.rsi_min:.0f}",
        ))

    # IV/HV比率
    if strategy.iv_hv_ratio_min is not None:
        conditions.append(ConditionResult(
            name="IV/HV比率",
            met=snapshot.iv_hv_ratio >= strategy.iv_hv_ratio_min,
            current_value=f"{snapshot.iv_hv_ratio:.2f}",
            threshold=f">= {strategy.iv_hv_ratio_min:.1f}",
        ))

    # テクニカルサポート（50MA付近）
    if strategy.near_50ma:
        conditions.append(ConditionResult(
            name="50日MA付近",
            met=snapshot.near_50ma,
            current_value=f"{'Yes' if snapshot.near_50ma else 'No'} (MA: ${snapshot.ma_50:.2f})",
            threshold=f"価格がMAの±2%以内",
        ))

    # P/C Ratio
    if strategy.put_call_ratio_sma_min is not None and snapshot.put_call_ratio_sma is not None:
        conditions.append(ConditionResult(
            name="P/C Ratio 10日SMA",
            met=snapshot.put_call_ratio_sma >= strategy.put_call_ratio_sma_min,
            current_value=f"{snapshot.put_call_ratio_sma:.2f}",
            threshold=f">= {strategy.put_call_ratio_sma_min:.1f}",
        ))

    # 条件達成数の集計
    met_count = sum(1 for c in conditions if c.met)
    total_count = len(conditions)
    is_triggered = met_count >= strategy.min_conditions_met

    # シグナル強度判定
    if total_count == 0:
        strength = "WEAK"
    else:
        ratio = met_count / total_count
        if ratio >= 0.8:
            strength = "STRONG"
        elif ratio >= 0.6:
            strength = "MODERATE"
        else:
            strength = "WEAK"

    signal = StrategySignal(
        strategy=strategy,
        symbol=snapshot.symbol,
        is_triggered=is_triggered,
        conditions_met=met_count,
        conditions_total=total_count,
        condition_details=conditions,
        snapshot=snapshot,
        strength=strength,
    )

    if is_triggered:
        logger.info(f"SIGNAL: {strategy.name_jp} for {snapshot.symbol} - "
                     f"{met_count}/{total_count} conditions met ({strength})")
    else:
        logger.debug(f"No signal: {strategy.name_jp} for {snapshot.symbol} - "
                      f"{met_count}/{total_count} conditions met")

    return signal


def scan_all_strategies(snapshot: MarketSnapshot) -> list[StrategySignal]:
    """全戦略をスキャンし、シグナルのリストを返す"""
    signals = []
    for strategy in ALL_STRATEGIES:
        signal = check_strategy(strategy, snapshot)
        signals.append(signal)
    return signals


def get_triggered_signals(snapshot: MarketSnapshot) -> list[StrategySignal]:
    """トリガーされたシグナルのみ返す"""
    all_signals = scan_all_strategies(snapshot)
    return [s for s in all_signals if s.is_triggered]
