"""
無在庫転売管理ツール - CLIエントリーポイント

使い方:
    # フェーズ1: 価格差リサーチ
    python -m dropshipping research --urls "URL1,URL2,..."
    python -m dropshipping research --keyword "検索キーワード"

    # フェーズ2: 在庫監視
    python -m dropshipping monitor           # 単発チェック
    python -m dropshipping monitor --loop    # 5分間隔で継続監視

    # フェーズ3: メルカリ公開停止
    python -m dropshipping pause

    # データベース操作
    python -m dropshipping list              # 全商品一覧
    python -m dropshipping list --profitable # 利益商品のみ
    python -m dropshipping set-status <id> <status>  # ステータス変更
"""

import argparse
import asyncio
import sys

from .utils.config import config
from .utils.database import (
    get_all_items,
    get_profitable_items,
    init_db,
    update_item_status,
)
from .utils.helpers import format_price, get_logger

logger = get_logger(__name__)


def cmd_research(args):
    """フェーズ1: 価格差リサーチ"""
    from .scrapers.researcher import research_keyword, research_urls

    init_db()

    if args.keyword:
        results = asyncio.run(
            research_keyword(
                keyword=args.keyword,
                max_products=args.max_results,
                shipping_cost=args.shipping,
            )
        )
    elif args.urls:
        url_list = [u.strip() for u in args.urls.split(",") if u.strip()]
        if not url_list:
            print("エラー: URLリストが空です")
            sys.exit(1)
        results = asyncio.run(
            research_urls(url_list, shipping_cost=args.shipping)
        )
    else:
        print("エラー: --urls または --keyword を指定してください")
        sys.exit(1)

    if results:
        print(f"\n合計 {len(results)}件の利益商品が見つかりました。")
    else:
        print("\n利益基準を満たす商品は見つかりませんでした。")


def cmd_monitor(args):
    """フェーズ2: 在庫監視"""
    from .monitors.stock_monitor import run_stock_check, start_monitoring

    init_db()

    if args.loop:
        if args.interval:
            config.monitor.check_interval = args.interval
        asyncio.run(start_monitoring())
    else:
        asyncio.run(run_stock_check())


def cmd_pause(args):
    """フェーズ3: メルカリ公開停止"""
    from .automation.mercari_automation import pause_out_of_stock_listings

    init_db()
    asyncio.run(pause_out_of_stock_listings())


def cmd_list(args):
    """商品一覧表示"""
    init_db()

    if args.profitable:
        items = get_profitable_items(config.profit.min_profit_threshold)
        label = f"利益 {format_price(config.profit.min_profit_threshold)} 以上の商品"
    else:
        items = get_all_items()
        label = "全商品"

    if not items:
        print("商品データがありません。")
        return

    print(f"\n{'=' * 80}")
    print(f"  {label} ({len(items)}件)")
    print(f"{'=' * 80}")
    print(f"{'ID':>4}  {'ステータス':^12}  {'Amazon価格':>10}  {'メルカリ相場':>10}  {'利益':>10}  商品名")
    print(f"{'-' * 80}")

    for item in items:
        amazon_price = format_price(item["amazon_price"]) if item["amazon_price"] else "-"
        mercari_price = format_price(item["mercari_avg_sold_price"]) if item["mercari_avg_sold_price"] else "-"
        profit = format_price(item["estimated_profit"]) if item["estimated_profit"] else "-"
        title = (item["amazon_title"] or "(不明)")[:30]
        status = item["status"]

        print(f"{item['id']:>4}  {status:^12}  {amazon_price:>10}  {mercari_price:>10}  {profit:>10}  {title}")

    print(f"{'=' * 80}\n")


def cmd_set_status(args):
    """ステータス変更"""
    init_db()
    valid_statuses = ["researched", "listed", "out_of_stock", "paused", "sold", "archived"]
    if args.status not in valid_statuses:
        print(f"エラー: 無効なステータス '{args.status}'")
        print(f"有効なステータス: {', '.join(valid_statuses)}")
        sys.exit(1)

    update_item_status(args.item_id, args.status)
    print(f"商品ID {args.item_id} のステータスを '{args.status}' に更新しました。")


def main():
    parser = argparse.ArgumentParser(
        description="無在庫転売管理ツール - Amazon × メルカリ価格差アービトラージ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="実行するコマンド")

    # research コマンド
    p_research = subparsers.add_parser("research", help="価格差リサーチ")
    p_research.add_argument("--urls", help="Amazon URLリスト（カンマ区切り）")
    p_research.add_argument("--keyword", help="検索キーワード")
    p_research.add_argument("--max-results", type=int, default=10, help="最大検索件数 (デフォルト: 10)")
    p_research.add_argument("--shipping", type=int, default=None, help="送料 (デフォルト: 700円)")
    p_research.add_argument(
        "--min-profit", type=int, default=None,
        help=f"最低利益しきい値 (デフォルト: {config.profit.min_profit_threshold}円)",
    )
    p_research.set_defaults(func=cmd_research)

    # monitor コマンド
    p_monitor = subparsers.add_parser("monitor", help="在庫監視")
    p_monitor.add_argument("--loop", action="store_true", help="継続的に監視（デフォルト: 単発チェック）")
    p_monitor.add_argument("--interval", type=int, default=None, help="チェック間隔（秒）")
    p_monitor.set_defaults(func=cmd_monitor)

    # pause コマンド
    p_pause = subparsers.add_parser("pause", help="メルカリ出品の公開停止")
    p_pause.set_defaults(func=cmd_pause)

    # list コマンド
    p_list = subparsers.add_parser("list", help="商品一覧表示")
    p_list.add_argument("--profitable", action="store_true", help="利益商品のみ表示")
    p_list.set_defaults(func=cmd_list)

    # set-status コマンド
    p_status = subparsers.add_parser("set-status", help="商品ステータス変更")
    p_status.add_argument("item_id", type=int, help="商品ID")
    p_status.add_argument("status", help="新しいステータス")
    p_status.set_defaults(func=cmd_set_status)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # min-profitの反映
    if hasattr(args, "min_profit") and args.min_profit is not None:
        config.profit.min_profit_threshold = args.min_profit

    args.func(args)


if __name__ == "__main__":
    main()
