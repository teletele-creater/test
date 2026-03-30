#!/usr/bin/env python3
"""パラメータ最適化の高速版"""
import sys
import numpy as np
np.random.seed(42)

from backtest_screener import SIMULATED_STOCKS, run_backtest
from screener_config import ScreeningRules

stocks = SIMULATED_STOCKS
param_sets = []

for peg in [0.5, 0.75, 1.0, 1.2]:
    for yld in [10.0, 15.0, 20.0, 30.0]:
        for per in [20.0, 25.0, 30.0, 40.0]:
            for mr in [2, 3]:
                for mom in [True, False]:
                    for reb in [3.0, 5.0, 8.0]:
                        if not mom and reb != 5.0:
                            continue
                        param_sets.append({
                            "peg_threshold": peg,
                            "yield_top_percentile": yld,
                            "per_bottom_percentile": per,
                            "min_rules_passed": mr,
                            "use_momentum_filter": mom,
                            "momentum_rebound_pct": reb,
                        })

print(f"Total combos: {len(param_sets)}")

SEP = "-" * 110

for holding in [6, 12, 18]:
    print(f"\n{'='*80}")
    print(f"  HOLDING: {holding} months")
    print(f"{'='*80}")

    results = []
    for params in param_sets:
        rules = ScreeningRules(**params)
        bt = run_backtest(stocks, rules, holding_months=holding)

        if bt.total_trades < 3:
            score = -100
        else:
            trade_bonus = min(bt.total_trades / 10, 1.0)
            score = (
                bt.win_rate * 0.3
                + bt.avg_total_return * 2.0
                + bt.sharpe_like * 10.0
                - max(0, -bt.max_loss) * 0.3
            ) * trade_bonus
        results.append((params, bt, score))

    results.sort(key=lambda x: x[2], reverse=True)

    print(f"\n  TOP 20:")
    print(SEP)
    header = (
        f"{'PEG':>5} {'Yld':>5} {'PER':>5} {'Rule':>4} {'Mom':>4} {'Reb':>4} |"
        f"{'#':>4} {'WinR':>7} {'AvgR':>8} {'TotR':>8} {'MaxL':>8} {'Sharp':>8} {'Score':>8}"
    )
    print(header)
    print(SEP)

    for params, bt, score in results[:20]:
        mom = "ON" if params["use_momentum_filter"] else "OFF"
        print(
            f"{params['peg_threshold']:>5.2f} "
            f"{params['yield_top_percentile']:>5.0f} "
            f"{params['per_bottom_percentile']:>5.0f} "
            f"{params['min_rules_passed']:>4} "
            f"{mom:>4} "
            f"{params['momentum_rebound_pct']:>4.0f} |"
            f"{bt.total_trades:>4} "
            f"{bt.win_rate:>6.1f}% "
            f"{bt.avg_return:>+7.2f}% "
            f"{bt.avg_total_return:>+7.2f}% "
            f"{bt.max_loss:>+7.2f}% "
            f"{bt.sharpe_like:>8.3f} "
            f"{score:>8.1f}"
        )
    print(SEP)

    # Best details
    best_params, best_bt, best_score = results[0]
    print(f"\n  BEST (holding={holding}m):")
    print(f"    PEG<{best_params['peg_threshold']} | Yield top {best_params['yield_top_percentile']}%"
          f" | PER bottom {best_params['per_bottom_percentile']}%"
          f" | min_rules={best_params['min_rules_passed']}"
          f" | momentum={'ON' if best_params['use_momentum_filter'] else 'OFF'}"
          f" rebound={best_params['momentum_rebound_pct']}%")
    print(best_bt.summary())

    # Print trade details for best
    from backtest_screener import print_trade_details
    print_trade_details(best_bt)
