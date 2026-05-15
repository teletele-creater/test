import os
import anthropic
from dotenv import load_dotenv
import time
import random
from datetime import datetime, timedelta
import json
import logging
import undetected_chromedriver as uc
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

        # ログイン状態を保持するプロファイルディレクトリ（スクリプトと同じ場所に保存）
        profile_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome_profile")

        # undetected-chromedriverセットアップ（bot検知回避）
        options = uc.ChromeOptions()
        options.add_argument(f'--user-data-dir={profile_dir}')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1280,900')

        self.driver = uc.Chrome(options=options, headless=headless, use_subprocess=True)
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

    def _is_logged_in(self):
        """現在ログイン済みかチェック"""
        try:
            self.driver.find_element(
                By.XPATH, "//a[@data-testid='AppTabBar_Home_Link']"
            )
            return True
        except NoSuchElementException:
            return False

    def login(self, wait_minutes=5):
        """X (Twitter) にログインする
        - セッション保存済みなら自動スキップ
        - 未ログインならブラウザを開いて手動ログインを待機
        """
        self.driver.get("https://x.com/home")
        self.human_like_action(3, 5)

        if self._is_logged_in():
            logger.info("セッション有効：ログインをスキップしました")
            return

        # 手動ログインを促すメッセージを大きく表示
        print("\n" + "=" * 70)
        print("  Chromeブラウザが開きました。Xに手動でログインしてください")
        print(f"  ログイン完了を自動検知して処理を続行します（最大{wait_minutes}分待機）")
        print("  ※一度ログインすればchrome_profileに保存され次回からは自動スキップ")
        print("=" * 70 + "\n")

        self.driver.get("https://x.com/i/flow/login")

        # ホーム画面のリンクが表示されるまで定期的にチェック（最大wait_minutes分）
        check_interval = 3
        max_checks = (wait_minutes * 60) // check_interval
        for i in range(max_checks):
            time.sleep(check_interval)
            if self._is_logged_in():
                logger.info("ログイン完了を検知しました")
                self.human_like_action(2, 4)
                return
            if i % 10 == 0 and i > 0:
                remaining = wait_minutes - (i * check_interval) // 60
                logger.info(f"ログイン待機中...（残り約{remaining}分）")

        # タイムアウト
        try:
            self.driver.save_screenshot("login_timeout.png")
        except Exception:
            pass
        raise TimeoutException(
            f"{wait_minutes}分以内にログインが完了しませんでした。"
            "再実行してログインしてください。"
        )

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

    def _safe_click(self, element):
        """通常クリックが効かない場合はJSクリックでフォールバック"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.3)
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)

    def _type_text(self, element, text):
        """絵文字などBMP外の文字も含めて入力する（CDP経由）"""
        self._safe_click(element)
        time.sleep(0.3)
        try:
            self.driver.execute_cdp_cmd("Input.insertText", {"text": text})
        except Exception:
            # CDPが使えない場合はBMP外文字を除外してsend_keysにフォールバック
            safe_text = ''.join(c for c in text if ord(c) < 0x10000)
            element.send_keys(safe_text)

    def _parse_count(self, text):
        """'1,234' '1.2万' '1K' などをintに変換"""
        if not text:
            return 0
        text = text.strip().replace(',', '').replace('件', '').replace(' ', '')
        try:
            if '万' in text:
                return int(float(text.replace('万', '')) * 10000)
            if text.upper().endswith('K'):
                return int(float(text[:-1]) * 1000)
            if text.upper().endswith('M'):
                return int(float(text[:-1]) * 1000000)
            return int(text)
        except (ValueError, TypeError):
            return 0

    def _get_user_stats(self):
        """現在表示中のプロフィールページからフォロワー数などを取得"""
        stats = {'followers': 0, 'following': 0, 'has_bio': False}
        try:
            following_el = self.driver.find_element(
                By.XPATH,
                "//a[contains(@href, '/following')]//span[@data-testid='count' or (not(@class) and string-length(text())>0)][1]"
            )
            stats['following'] = self._parse_count(following_el.text)
        except Exception:
            pass
        try:
            followers_el = self.driver.find_element(
                By.XPATH,
                "//a[contains(@href, '/followers') and not(contains(@href, '/followers_you_follow'))]//span[@data-testid='count' or (not(@class) and string-length(text())>0)][1]"
            )
            stats['followers'] = self._parse_count(followers_el.text)
        except Exception:
            pass
        try:
            self.driver.find_element(By.XPATH, "//div[@data-testid='UserDescription']")
            stats['has_bio'] = True
        except NoSuchElementException:
            pass
        return stats

    def _is_quality_account(self, stats, uname):
        """スパム・bot・非アクティブアカウントを除外する"""
        followers = stats['followers']
        following = stats['following']

        if followers < 20:
            logger.info(f"@{uname} スキップ: フォロワー数が少なすぎます ({followers}人)")
            return False
        if following > 5000:
            logger.info(f"@{uname} スキップ: フォロー数が多すぎます ({following}人) = スパム型")
            return False
        if followers > 0 and following / max(followers, 1) > 10:
            logger.info(f"@{uname} スキップ: フォロー/フォロワー比が異常 ({following}/{followers})")
            return False
        if not stats['has_bio']:
            logger.info(f"@{uname} スキップ: bioなし = 非アクティブアカウント")
            return False
        return True

    def _like_recent_tweets(self, uname, count=2):
        """プロフィールページで最新ツイートをいいねする（フォロー前の事前エンゲージ）"""
        liked = 0
        try:
            like_buttons = self.driver.find_elements(
                By.XPATH, "//button[@data-testid='like']"
            )
            for btn in like_buttons[:count]:
                try:
                    self._safe_click(btn)
                    liked += 1
                    self.human_like_action(1, 2)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"いいねエラー (@{uname}): {e}")
        if liked > 0:
            logger.info(f"@{uname} のツイートに{liked}件いいねしました（フォロー前）")
        return liked

    def post_tweet(self, content):
        """ツイートを投稿する"""
        try:
            # ホーム画面に確実に移動
            self.driver.get("https://x.com/home")
            self.human_like_action(2, 4)

            tweet_box = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[@data-testid='tweetTextarea_0']")
                )
            )
            self._type_text(tweet_box, content)
            self.human_like_action(1, 2)

            post_button = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//button[@data-testid='tweetButtonInline']")
                )
            )
            self._safe_click(post_button)
            logger.info(f"ツイート投稿成功: {content[:50]}...")
            self.human_like_action(2, 4)
        except Exception as e:
            logger.error(f"ツイート投稿エラー: {e}")

    def follow_by_hashtag(self, hashtag, count=5):
        """ハッシュタグ検索結果のユーザーをフォローする（品質フィルタ付き）"""
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

                    # --- 品質フィルタ ---
                    stats = self._get_user_stats()
                    if not self._is_quality_account(stats, uname):
                        continue

                    # --- フォロー前にいいね（事前エンゲージ）---
                    self._like_recent_tweets(uname, count=2)
                    self.human_like_action(1, 3)

                    # --- フォロー ---
                    follow_button = self.wait.until(
                        EC.presence_of_element_located(
                            (By.XPATH,
                             "//button[@data-testid='placementTracking']//span[text()='フォロー']")
                        )
                    )
                    self._safe_click(follow_button)
                    logger.info(f"@{uname} をフォローしました (フォロワー:{stats['followers']} フォロー:{stats['following']})")
                    self.followed_users[uname] = datetime.now().isoformat()
                    self.save_followed_users()
                    followed_count += 1
                    self.human_like_action(4, 8)
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

            liked_ids = set()
            while liked_count < count and scroll_attempts < 8:
                like_buttons = self.driver.find_elements(
                    By.XPATH, "//button[@data-testid='like']"
                )
                clicked_this_round = False
                for button in like_buttons:
                    if liked_count >= count:
                        break
                    btn_key = id(button)
                    if btn_key in liked_ids:
                        continue
                    try:
                        self._safe_click(button)
                        logger.info(f"いいねしました ({liked_count + 1}件目)")
                        liked_count += 1
                        liked_ids.add(btn_key)
                        clicked_this_round = True
                        self.human_like_action(2, 5)
                    except Exception as e:
                        logger.error(f"いいねエラー: {e}")

                self.driver.execute_script("window.scrollBy(0, 800);")
                self.human_like_action(2, 3)
                scroll_attempts += 1
                if not clicked_this_round and scroll_attempts >= 8:
                    break

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
                    EC.presence_of_element_located(
                        (By.XPATH,
                         "//button[@data-testid='placementTracking']//span[text()='フォロー中']")
                    )
                )
                self._safe_click(following_button)
                self.human_like_action(1, 2)

                # 確認ダイアログ
                confirm_button = self.wait.until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//button[@data-testid='confirmationSheetConfirm']")
                    )
                )
                self._safe_click(confirm_button)
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
    # 具体的・ニッチ（スパムが少ない）
    '浮気調査', '浮気疑惑', '旦那の浮気', '彼氏の浮気',
    '不倫調査', '浮気確認', '浮気バレた',
    # 悩み系（実際に困っている人が使う）
    '彼氏が不安', '遠距離恋愛不安', '恋人の行動が怪しい',
    '夫婦問題', '離婚相談', '恋愛相談',
]

KEYWORDS = [
    '彼 怪しい', '浮気 かもしれない', 'スマホ 見せない',
    'line 返信遅い', '週末 会えない', '出張 多い',
    '香水 変わった', '不安で眠れない', '信じられない',
    '裏切られた気持ち', '疑心暗鬼',
]


if __name__ == "__main__":
    bot = TwitterAutomation(headless=False)

    try:
        bot.login()

        # ランダムにトピックを選んでClaudeがツイートを生成＆投稿
        topic = random.choice(TOPICS)
        content = bot.generate_tweet_content(topic)
        bot.post_tweet(content)

        # ランダムにハッシュタグを選んでフォロー（品質フィルタ付き）
        hashtag = random.choice(HASHTAGS)
        bot.follow_by_hashtag(hashtag, count=5)

        # ランダムにキーワードを選んでいいね
        keyword = random.choice(KEYWORDS)
        bot.auto_like_by_keyword(keyword, count=10)

        # 3日経ってもフォローバックなしをアンフォロー
        bot.unfollow_non_followers(days=3)
    finally:
        bot.close()
