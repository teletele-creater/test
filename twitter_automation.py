import os
import tweepy
import anthropic
from dotenv import load_dotenv
import time
import random
from datetime import datetime, timedelta
import json
import logging

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 環境変数読み込み
load_dotenv()


class TwitterAutomation:
    def __init__(self):
        # Anthropic API設定
        self.anthropic_client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        # Twitter API v2クライアント設定（wait_on_rate_limit=Trueでレート制限を自動待機）
        self.client = tweepy.Client(
            bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
            consumer_key=os.getenv("TWITTER_API_KEY"),
            consumer_secret=os.getenv("TWITTER_API_SECRET"),
            access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
            access_token_secret=os.getenv("TWITTER_ACCESS_SECRET"),
            wait_on_rate_limit=True
        )

        # Twitter API v1.1認証（フォロー確認に使用）
        self.auth = tweepy.OAuth1UserHandler(
            os.getenv("TWITTER_API_KEY"),
            os.getenv("TWITTER_API_SECRET"),
            os.getenv("TWITTER_ACCESS_TOKEN"),
            os.getenv("TWITTER_ACCESS_SECRET")
        )
        self.api = tweepy.API(self.auth, wait_on_rate_limit=True)

        # 自分のユーザーID取得
        me = self.client.get_me()
        self.my_id = me.data.id

        # フォローしたユーザーを記録するファイル
        self.followed_users_file = "followed_users.json"
        self.load_followed_users()

    def load_followed_users(self):
        """フォローしたユーザーデータを読み込む"""
        try:
            with open(self.followed_users_file, 'r') as f:
                self.followed_users = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.followed_users = {}

    def save_followed_users(self):
        """フォローしたユーザーデータを保存する"""
        with open(self.followed_users_file, 'w') as f:
            json.dump(self.followed_users, f)

    def human_like_action(self):
        """人間らしい操作間隔を模倣するための待機"""
        wait_time = random.uniform(3, 8)
        logger.info(f"{wait_time:.1f}秒待機中...")
        time.sleep(wait_time)

    def generate_tweet_content(self, topic):
        """Anthropic APIを使ってツイート内容を生成"""
        try:
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=280,
                system="あなたはソーシャルメディアマネージャーです。専門的かつ親しみやすいトーンで280文字以内のツイートを作成してください。",
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"次のトピックに関するハッシュタグを含むつぶやきを生成してください: {topic}\n\n"
                            "ルール:\n- 280文字以内\n- ターゲット層：テック好き\n"
                            "- トーン：専門的かつ親しみやすい\n- ハッシュタグを含める"
                        )
                    }
                ]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"ツイート生成エラー: {e}")
            return f"今日の{topic}について考えてみました。 #テック #AI"

    def post_tweet(self, content):
        """ツイートを投稿する"""
        try:
            response = self.client.create_tweet(text=content)
            logger.info(f"ツイート投稿成功: {content}")
            return response
        except Exception as e:
            logger.error(f"ツイート投稿エラー: {e}")
            return None

    def is_following(self, target_user_id):
        """指定ユーザーをフォロー済みか確認（v1.1 API使用）"""
        try:
            # get_friendship は (source_rel, target_rel) のタプルを返す
            friendship = self.api.get_friendship(
                source_id=self.my_id,
                target_id=target_user_id
            )
            return friendship[0].following
        except Exception as e:
            logger.error(f"フォロー確認エラー (target={target_user_id}): {e}")
            return False

    def auto_follow_by_hashtag(self, hashtag, count=10):
        """指定したハッシュタグで検索し、指定数のアカウントをフォロー"""
        # search_recent_tweets の max_results は 10〜100 の範囲
        count = max(10, min(count, 100))
        try:
            tweets = self.client.search_recent_tweets(
                query=f"#{hashtag} -is:retweet",
                max_results=count,
                tweet_fields=['author_id', 'created_at']
            )

            if not tweets.data:
                logger.info(f"ハッシュタグ #{hashtag} のツイートが見つかりませんでした")
                return

            followed_count = 0
            for tweet in tweets.data:
                user_id = tweet.author_id

                # 既にフォローしているか確認
                if self.is_following(user_id):
                    logger.info(f"ユーザー {user_id} は既にフォロー済みです")
                    continue

                try:
                    self.client.follow_user(target_user_id=user_id)
                    logger.info(f"ユーザー {user_id} をフォローしました")
                    self.followed_users[str(user_id)] = datetime.now().isoformat()
                    self.save_followed_users()
                    followed_count += 1
                    self.human_like_action()
                except Exception as e:
                    logger.error(f"フォローエラー (user_id={user_id}): {e}")

            logger.info(f"{followed_count}人のユーザーをフォローしました")
        except Exception as e:
            logger.error(f"ハッシュタグ検索エラー: {e}")

    def unfollow_non_followers(self, days=3):
        """指定日数経過してもフォローバックしていないアカウントをアンフォロー"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)

            # フォロワーIDをページネーション対応で取得
            follower_ids = set()
            for response in tweepy.Paginator(
                self.client.get_users_followers,
                id=self.my_id,
                max_results=1000
            ):
                if response.data:
                    for user in response.data:
                        follower_ids.add(user.id)

            # フォロー中ユーザーをページネーション対応で取得
            unfollow_count = 0
            for response in tweepy.Paginator(
                self.client.get_users_following,
                id=self.my_id,
                max_results=1000
            ):
                if not response.data:
                    continue

                for user in response.data:
                    user_id_str = str(user.id)

                    if user_id_str not in self.followed_users:
                        continue

                    follow_date = datetime.fromisoformat(self.followed_users[user_id_str])
                    if follow_date >= cutoff_date:
                        continue

                    if user.id in follower_ids:
                        # フォローバック済みなので記録から削除
                        del self.followed_users[user_id_str]
                        self.save_followed_users()
                        continue

                    try:
                        self.client.unfollow_user(target_user_id=user.id)
                        logger.info(f"ユーザー {user_id_str} をアンフォローしました")
                        unfollow_count += 1
                        del self.followed_users[user_id_str]
                        self.save_followed_users()
                        self.human_like_action()
                    except Exception as e:
                        logger.error(f"アンフォローエラー (user_id={user_id_str}): {e}")

            logger.info(f"{unfollow_count}人のユーザーをアンフォローしました")
        except Exception as e:
            logger.error(f"アンフォロー処理エラー: {e}")

    def auto_like_by_keyword(self, keyword, count=20):
        """指定キーワードを含むツイートに自動いいね"""
        count = max(10, min(count, 100))
        try:
            tweets = self.client.search_recent_tweets(
                query=f"{keyword} -is:retweet",
                max_results=count,
                tweet_fields=['id']
            )

            if not tweets.data:
                logger.info(f"キーワード '{keyword}' のツイートが見つかりませんでした")
                return

            liked_count = 0
            for tweet in tweets.data:
                try:
                    self.client.like(tweet_id=tweet.id)
                    logger.info(f"ツイート {tweet.id} にいいねしました")
                    liked_count += 1
                    self.human_like_action()
                except Exception as e:
                    logger.error(f"いいねエラー (tweet_id={tweet.id}): {e}")

            logger.info(f"{liked_count}件のツイートにいいねしました")
        except Exception as e:
            logger.error(f"キーワード検索エラー: {e}")


if __name__ == "__main__":
    bot = TwitterAutomation()

    topic = "AIと機械学習の最新トレンド"
    content = bot.generate_tweet_content(topic)
    bot.post_tweet(content)

    bot.auto_follow_by_hashtag("AI", count=10)
    bot.auto_like_by_keyword("機械学習", count=20)
    bot.unfollow_non_followers(days=3)
