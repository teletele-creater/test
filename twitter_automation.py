import os
import anthropic
from dotenv import load_dotenv
import time
import random
from datetime import datetime, timedelta
import json
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()


class TwitterAutomation:
    def __init__(self, headless=True):
        # Anthropic API（ツイート生成用）
        self.anthropic_client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        # Seleniumセットアップ
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        # botと検知されにくくする設定
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)

        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self.wait = WebDriverWait(self.driver, 15)

        self.username = os.getenv("TWITTER_USERNAME")
        self.password = os.getenv("TWITTER_PASSWORD")

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

    def human_like_action(self, min_sec=2, max_sec=6):
        """人間らしい操作間隔を模倣するための待機"""
        wait_time = random.uniform(min_sec, max_sec)
        logger.info(f"{wait_time:.1f}秒待機中...")
        time.sleep(wait_time)

    def login(self):
        """Twitterにログインする"""
        try:
            self.driver.get("https://twitter.com/login")

            # ユーザー名入力
            username_input = self.wait.until(
                EC.presence_of_element_located((By.NAME, "text"))
            )
            username_input.send_keys(self.username)

            # 次へボタン
            next_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//span[text()='次へ']"))
            )
            next_button.click()
            self.human_like_action(1, 3)

            # パスワード入力
            password_input = self.wait.until(
                EC.presence_of_element_located((By.NAME, "password"))
            )
            password_input.send_keys(self.password)

            # ログインボタン
            login_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//span[text()='ログイン']"))
            )
            login_button.click()

            # ホーム画面の読み込み完了を待機
            self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//a[@data-testid='AppTabBar_Home_Link']")
                )
            )
            logger.info("ログイン成功")
            self.human_like_action(3, 5)
        except Exception as e:
            logger.error(f"ログインエラー: {e}")
            raise

    def generate_tweet_content(self, topic):
        """Claude APIを使ってツイート内容を生成"""
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
            tweet_box = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[@data-testid='tweetTextarea_0']")
                )
            )
            tweet_box.click()
            tweet_box.send_keys(content)
            self.human_like_action(1, 2)

            post_button = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[@data-testid='tweetButtonInline']")
                )
            )
            post_button.click()
            logger.info(f"ツイート投稿成功: {content[:50]}...")
            self.human_like_action(2, 4)
        except Exception as e:
            logger.error(f"ツイート投稿エラー: {e}")

    def follow_by_hashtag(self, hashtag, count=5):
        """ハッシュタグ検索結果のユーザーをフォローする"""
        try:
            self.driver.get(
                f"https://twitter.com/search?q=%23{hashtag}&src=typed_query&f=live"
            )
            self.human_like_action(3, 5)

            # スクロールしてツイートを追加読み込み
            for _ in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                self.human_like_action(2, 3)

            # ツイートに含まれるユーザー名を収集
            user_links = self.driver.find_elements(
                By.XPATH,
                "//div[@data-testid='User-Name']//a[contains(@href, '/') and not(contains(@href, '/status/'))]"
            )
            usernames = []
            for link in user_links:
                href = link.get_attribute('href')
                if href:
                    uname = href.rstrip('/').split('/')[-1]
                    if uname and uname not in usernames and uname != self.username:
                        usernames.append(uname)

            followed_count = 0
            for uname in usernames:
                if followed_count >= count:
                    break
                if uname in self.followed_users:
                    logger.info(f"@{uname} は既にフォロー済みです")
                    continue

                try:
                    self.driver.get(f"https://twitter.com/{uname}")
                    self.human_like_action(2, 4)

                    follow_button = self.wait.until(
                        EC.element_to_be_clickable(
                            (By.XPATH,
                             "//button[@data-testid='placementTracking']//span[text()='フォロー']")
                        )
                    )
                    follow_button.click()
                    logger.info(f"@{uname} をフォローしました")
                    self.followed_users[uname] = datetime.now().isoformat()
                    self.save_followed_users()
                    followed_count += 1
                    self.human_like_action(3, 7)
                except TimeoutException:
                    logger.info(f"@{uname} はフォロー済みかボタンが見つかりません")
                except Exception as e:
                    logger.error(f"フォローエラー (@{uname}): {e}")

            logger.info(f"{followed_count}人をフォローしました")
        except Exception as e:
            logger.error(f"ハッシュタグ検索エラー: {e}")

    def auto_like_by_keyword(self, keyword, count=10):
        """キーワードで検索してツイートにいいねする"""
        try:
            query = keyword.replace(' ', '%20')
            self.driver.get(
                f"https://twitter.com/search?q={query}&src=typed_query&f=live"
            )
            self.human_like_action(3, 5)

            liked_count = 0
            scroll_attempts = 0

            while liked_count < count and scroll_attempts < 5:
                like_buttons = self.driver.find_elements(
                    By.XPATH, "//button[@data-testid='like']"
                )
                for button in like_buttons:
                    if liked_count >= count:
                        break
                    try:
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView();", button
                        )
                        button.click()
                        logger.info(f"いいねしました ({liked_count + 1}件目)")
                        liked_count += 1
                        self.human_like_action(2, 5)
                    except Exception as e:
                        logger.error(f"いいねエラー: {e}")

                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                self.human_like_action(2, 3)
                scroll_attempts += 1

            logger.info(f"{liked_count}件のツイートにいいねしました")
        except Exception as e:
            logger.error(f"いいね処理エラー: {e}")

    def unfollow_non_followers(self, days=3):
        """指定日数経過してもフォローバックしていないユーザーをアンフォロー"""
        cutoff_date = datetime.now() - timedelta(days=days)
        targets = [
            uname for uname, date_str in self.followed_users.items()
            if datetime.fromisoformat(date_str) < cutoff_date
        ]

        unfollow_count = 0
        for uname in targets:
            try:
                self.driver.get(f"https://twitter.com/{uname}")
                self.human_like_action(2, 4)

                # フォローバックされているか確認
                try:
                    self.driver.find_element(
                        By.XPATH, "//span[contains(text(), 'フォローされています')]"
                    )
                    logger.info(f"@{uname} にはフォローバックされています。スキップ")
                    del self.followed_users[uname]
                    self.save_followed_users()
                    continue
                except NoSuchElementException:
                    pass

                # アンフォローボタンをクリック
                following_button = self.wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH,
                         "//button[@data-testid='placementTracking']//span[text()='フォロー中']")
                    )
                )
                following_button.click()
                self.human_like_action(1, 2)

                # 確認ダイアログ
                confirm_button = self.wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[@data-testid='confirmationSheetConfirm']")
                    )
                )
                confirm_button.click()
                logger.info(f"@{uname} をアンフォローしました")
                del self.followed_users[uname]
                self.save_followed_users()
                unfollow_count += 1
                self.human_like_action(3, 7)
            except TimeoutException:
                logger.info(f"@{uname} は既にアンフォロー済みの可能性があります")
                del self.followed_users[uname]
                self.save_followed_users()
            except Exception as e:
                logger.error(f"アンフォローエラー (@{uname}): {e}")

        logger.info(f"{unfollow_count}人をアンフォローしました")

    def close(self):
        """ブラウザを閉じる"""
        self.driver.quit()


if __name__ == "__main__":
    bot = TwitterAutomation(headless=True)

    try:
        bot.login()

        # Claude APIでツイート生成＆投稿
        topic = "AIと機械学習の最新トレンド"
        content = bot.generate_tweet_content(topic)
        bot.post_tweet(content)

        # ハッシュタグからフォロー
        bot.follow_by_hashtag("テック", count=5)

        # キーワードでいいね
        bot.auto_like_by_keyword("機械学習", count=10)

        # 3日経ってもフォローバックなしをアンフォロー
        bot.unfollow_non_followers(days=3)
    finally:
        bot.close()
