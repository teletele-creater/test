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
    def __init__(self, headless=False):
        # Anthropic API（ツイート生成用）
        self.anthropic_client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        # Seleniumセットアップ
        options = webdriver.ChromeOptions()
        if headless:
            # 新ヘッドレスモード（検知されにくい）
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1280,900')
        options.add_argument(
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        )
        # botと検知されにくくする設定
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)

        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self.wait = WebDriverWait(self.driver, 30)

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

    def _click_button_by_text(self, texts):
        """ボタンテキスト（日本語/英語）でクリックする"""
        if isinstance(texts, str):
            texts = [texts]
        xpath = " | ".join([f"//button[.//span[text()='{t}']]" for t in texts])
        button = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        button.click()

    def login(self):
        """X (Twitter) にログインする"""
        try:
            self.driver.get("https://x.com/i/flow/login")
            self.human_like_action(3, 5)

            # ユーザー名入力（言語問わずname="text"のinputが対象）
            username_input = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='text']"))
            )
            username_input.click()
            username_input.send_keys(self.username)
            self.human_like_action(1, 2)

            # 「次へ」ボタン（日本語/英語両対応）
            self._click_button_by_text(['次へ', 'Next'])
            self.human_like_action(2, 4)

            # 「不審なログイン」確認画面でユーザー名再入力を求められた場合に対応
            try:
                challenge = self.driver.find_element(
                    By.CSS_SELECTOR, "input[data-testid='ocfEnterTextTextInput']"
                )
                challenge.click()
                challenge.send_keys(self.username)
                self._click_button_by_text(['次へ', 'Next'])
                self.human_like_action(2, 4)
            except NoSuchElementException:
                pass

            # パスワード入力
            password_input = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='password']"))
            )
            password_input.click()
            password_input.send_keys(self.password)
            self.human_like_action(1, 2)

            # 「ログイン」ボタン（日本語/英語両対応）
            self._click_button_by_text(['ログイン', 'Log in'])

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
            # デバッグ用にスクリーンショットを保存
            try:
                self.driver.save_screenshot("login_error.png")
                logger.info("login_error.png にスクリーンショットを保存しました")
            except Exception:
                pass
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
                f"https://x.com/search?q=%23{hashtag}&src=typed_query&f=live"
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
                    self.driver.get(f"https://x.com/{uname}")
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
                f"https://x.com/search?q={query}&src=typed_query&f=live"
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
                self.driver.get(f"https://x.com/{uname}")
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


TOPICS = [
    # 浮気の兆候・サイン
    'パートナーのSNSでの些細な変化が浮気の兆候かもしれない理由',
    '急にスマホを肌身離さず持つようになったパートナーの心理',
    '週末の予定をぼかし始めた男性に見られる行動パターン',
    # 感情論
    '直感は嘘をつかない。でも証拠が必要な理由',
    '信頼と疑心の間で揺れる毎日から抜け出す方法',
    '彼の言動に違和感を感じ始めたときに確認すべきこと',
    # 自己肯定感
    '自分を大切にできない男性から離れる勇気の持ち方',
    '不安な毎日から抜け出すための具体的な第一歩',
    '自分の価値を再認識することで変わる恋愛観',
    # アドバイス
    '心理カウンセラーが教える浮気男性によく見られる口癖と行動',
    '弁護士が語る浮気を見抜くために必要な証拠の集め方',
    '探偵が実際に使う浮気調査の基本的な手法と注意点',
    # 成功事例
    'パートナーの浮気を見抜いた3つのポイントとその後の対処法',
    '不安な日々から解放された女性の体験談と転機になった出来事',
    '信頼関係を再構築した夫婦が実践した具体的なコミュニケーション',
]

HASHTAGS = [
    '浮気', '彼氏の浮気', '旦那の浮気', '浮気疑惑', '浮気調査',
    '彼氏が不安', '遠距離恋愛不安', '恋人の行動が怪しい', 'line既読スルー不安',
    '恋愛相談', '夫婦問題', '女性の悩み', '恋愛悩み',
    '探偵', '離婚相談', 'カウンセリング', '女性の悩み解決',
]

KEYWORDS = [
    '彼 怪しい', '浮気 かもしれない', 'スマホ 見せない',
    'line 返信遅い', '週末 会えない', '出張 多い', '残業 頻繁',
    '香水 変わった', '不安で眠れない', '信じられない',
    '裏切られた気持ち', '疑心暗鬼', 'ストレス 恋愛',
]


if __name__ == "__main__":
    bot = TwitterAutomation(headless=True)

    try:
        bot.login()

        # ランダムにトピックを選んでClaudeがツイートを生成＆投稿
        topic = random.choice(TOPICS)
        content = bot.generate_tweet_content(topic)
        bot.post_tweet(content)

        # ランダムにハッシュタグを選んでフォロー
        hashtag = random.choice(HASHTAGS)
        bot.follow_by_hashtag(hashtag, count=5)

        # ランダムにキーワードを選んでいいね
        keyword = random.choice(KEYWORDS)
        bot.auto_like_by_keyword(keyword, count=10)

        # 3日経ってもフォローバックなしをアンフォロー
        bot.unfollow_non_followers(days=3)
    finally:
        bot.close()
