"""
メインスクリプト
@shodousan のツイートを取得・分析してメモに保存する

使い方:
  python main.py              # 通常実行（差分取得）
  python main.py --all        # 全件取得（since_id を無視）
  python main.py --demo       # デモモード（X APIなしでテスト）
  python main.py --html-only  # HTMLのみ再生成
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta


def get_japanese_greeting() -> str:
    """現在時刻に応じた日本語の挨拶を返す"""
    jst = timezone(timedelta(hours=9))
    hour = datetime.now(jst).hour
    if 5 <= hour < 11:
        return "おはようございます！"
    elif 11 <= hour < 18:
        return "こんにちは！"
    else:
        return "こんばんは！"


def run_demo():
    """X APIなしで動作確認するデモモード"""
    from fetcher import Tweet
    from analyzer import analyze_tweet
    from storage import save_analyses
    from viewer import generate_html
    from datetime import datetime, timezone

    print("=" * 50)
    print(f"{get_japanese_greeting()} デモモード: サンプルツイートで動作確認")
    print("=" * 50)

    demo_tweets = [
        Tweet(
            id="1234567890001",
            text="7203 トヨタが第3四半期決算で過去最高益を更新。北米市場でのHV車販売が好調で、為替差益も加わり大幅増益。通期予想を上方修正。",
            created_at=datetime.now(timezone.utc),
            stock_codes=["7203"]
        ),
        Tweet(
            id="1234567890002",
            text="9984 ソフトバンクG、AI投資が実を結びビジョンファンドの評価益が急拡大。Arm株の上昇が貢献。反転攻勢の初動か。",
            created_at=datetime.now(timezone.utc),
            stock_codes=["9984"]
        ),
    ]

    from analyzer import analyze_tweets
    print(f"\n{len(demo_tweets)} 件のサンプルツイートを分析中...\n")
    analyses = analyze_tweets(demo_tweets)

    if analyses:
        paths = save_analyses(analyses)
        print(f"\n✅ {len(paths)} 件のメモを保存しました")
        html_path = generate_html()
        print(f"✅ HTMLビューワー: {html_path.absolute()}")
    else:
        print("❌ 分析結果がありません")


def run_setup():
    """ブラウザを開いてXにログインし、認証状態を保存する"""
    from playwright.sync_api import sync_playwright
    from config import AUTH_STATE_FILE

    print("=" * 50)
    print("X ログインセットアップ")
    print("=" * 50)
    print("\nブラウザが開きます。X (Twitter) にログインしてください。")
    print("ログイン完了後、このターミナルに戻って Enter を押してください。\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
        )
        page = context.new_page()
        page.goto("https://x.com/login")

        input("ログイン完了後、Enter を押してください...")

        context.storage_state(path=str(AUTH_STATE_FILE))
        browser.close()

    print(f"\n✅ 認証状態を保存しました: {AUTH_STATE_FILE}")
    print("次回から python main.py --latest または --watch で使えます")


def run_latest():
    """最新の株関連ツイート1件を取得して分析する"""
    from fetcher import fetch_latest_tweet
    from analyzer import analyze_tweet
    from storage import save_analysis
    from viewer import generate_html

    print("=" * 50)
    print(f"{get_japanese_greeting()} 最新ツイート分析モード")
    print("=" * 50)

    tweet = fetch_latest_tweet()
    if not tweet:
        print("株関連ツイートが見つかりませんでした")
        return

    print(f"\n📌 最新ツイート: {tweet.text[:60]}...\n")
    try:
        analysis = analyze_tweet(tweet)
        path = save_analysis(analysis)
        html_path = generate_html()
        print(f"\n✅ 保存: {path.name}")
        print(f"🌐 HTML: {html_path.absolute()}")
    except Exception as e:
        print(f"❌ エラー: {e}")


def run_watch(interval_min: int = 5):
    """新しいツイートを定期監視して自動分析するループ"""
    from fetcher import fetch_tweets
    from analyzer import analyze_tweet
    from storage import get_last_tweet_id, save_analysis
    from viewer import generate_html

    print("=" * 50)
    print(f"{get_japanese_greeting()} 監視モード起動 (チェック間隔: {interval_min}分)")
    print("Ctrl+C で停止")
    print("=" * 50)

    # 初回: 最新1件を取得して基準IDを設定
    print("\n[初回] 最新ツイートを取得中...")
    last_id = get_last_tweet_id()
    if not last_id:
        tweets = fetch_tweets(max_count=5)
        if tweets:
            latest = tweets[0]
            print(f"[INFO] 基準ツイートID: {latest.id}")
            print(f"[INFO] 内容: {latest.text[:60]}...")
            try:
                analysis = analyze_tweet(latest)
                path = save_analysis(analysis)
                generate_html()
                print(f"✅ 分析完了: {path.name}")
                last_id = latest.id
            except Exception as e:
                print(f"❌ 初回分析エラー: {e}")
        else:
            print("[WARN] 初回取得で株関連ツイートが見つかりませんでした")

    # 監視ループ
    try:
        while True:
            next_check = datetime.now(timezone(timedelta(hours=9)))
            print(f"\n⏳ 次回チェック: {interval_min}分後 ({next_check.strftime('%H:%M')} JST 現在)")
            time.sleep(interval_min * 60)

            jst = timezone(timedelta(hours=9))
            now_str = datetime.now(jst).strftime("%H:%M")
            print(f"\n🔍 [{now_str}] 新着チェック中...")

            current_last_id = get_last_tweet_id() or last_id
            new_tweets = fetch_tweets(since_id=current_last_id, max_count=10)

            if not new_tweets:
                print("  → 新しい株関連ツイートなし")
                continue

            print(f"  → {len(new_tweets)} 件の新着ツイートを検出！")
            for tweet in new_tweets:
                print(f"\n📌 新着: {tweet.text[:60]}...")
                try:
                    analysis = analyze_tweet(tweet)
                    path = save_analysis(analysis)
                    print(f"  ✅ 分析・保存: {path.name}")
                except Exception as e:
                    print(f"  ❌ 分析エラー: {e}")

            generate_html()
            print("🌐 HTML更新完了")

    except KeyboardInterrupt:
        print("\n\n👋 監視を終了しました")


def run_html_only():
    """HTMLのみ再生成する"""
    from viewer import generate_html
    from storage import update_index
    update_index()
    html_path = generate_html()
    print(f"✅ {html_path.absolute()}")


def run(fetch_all: bool = False):
    """メイン処理"""
    from fetcher import fetch_tweets
    from analyzer import analyze_tweets
    from storage import get_last_tweet_id, save_analyses
    from viewer import generate_html

    print("=" * 50)
    print(f"{get_japanese_greeting()} 株価初動メモシステム起動")
    print("=" * 50)

    # 差分取得（--all フラグがない場合）
    since_id = None if fetch_all else get_last_tweet_id()
    if since_id:
        print(f"[INFO] 前回取得 ID: {since_id} 以降を取得")
    else:
        print("[INFO] 全件取得モード")

    # ツイート取得
    try:
        tweets = fetch_tweets(since_id=since_id)
    except PermissionError as e:
        print(f"\n❌ {e}")
        print("\n📌 X API Basic プランが必要です:")
        print("   https://developer.twitter.com/en/portal/products")
        sys.exit(1)
    except ValueError as e:
        print(f"\n❌ {e}")
        sys.exit(1)

    if not tweets:
        print("新しい株関連ツイートはありませんでした")
        return

    print(f"\n📊 {len(tweets)} 件の株関連ツイートを分析します...\n")

    # Claude で分析
    analyses = analyze_tweets(tweets)

    if not analyses:
        print("分析できたツイートがありませんでした")
        return

    # 保存
    paths = save_analyses(analyses)

    # HTML生成
    html_path = generate_html()

    print("\n" + "=" * 50)
    print(f"✅ 完了: {len(paths)} 件のメモを保存")
    print(f"📄 メモフォルダ: {Path('notes').absolute()}")
    print(f"🌐 HTMLビューワー: {html_path.absolute()}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="@shodousan 株価初動メモシステム")
    parser.add_argument("--all", action="store_true", help="差分取得せず全件取得")
    parser.add_argument("--demo", action="store_true", help="デモモード（X APIなし）")
    parser.add_argument("--html-only", action="store_true", help="HTMLのみ再生成")
    parser.add_argument("--latest", action="store_true", help="最新ツイート1件のみ分析")
    parser.add_argument("--watch", type=int, nargs="?", const=5, metavar="分",
                        help="監視ループ起動。チェック間隔を分で指定（デフォルト: 5分）")
    parser.add_argument("--setup", action="store_true", help="Xにログインして認証状態を保存")
    args = parser.parse_args()

    if args.setup:
        run_setup()
    elif args.demo:
        run_demo()
    elif args.html_only:
        run_html_only()
    elif args.latest:
        run_latest()
    elif args.watch is not None:
        run_watch(interval_min=args.watch)
    else:
        run(fetch_all=args.all)


if __name__ == "__main__":
    main()
