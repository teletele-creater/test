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
    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.html_only:
        run_html_only()
    else:
        run(fetch_all=args.all)


if __name__ == "__main__":
    main()
