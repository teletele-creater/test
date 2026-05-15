import os
import anthropic
from dotenv import load_dotenv
import time
import random
from datetime import datetime, timedelta
import json
import logging
import threading
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()


class TwitterAutomation:
    def __init__(self, headless=False):
        self.anthropic_client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        profile_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome_profile")

        options = uc.ChromeOptions()
        options.add_argument(f'--user-data-dir={profile_dir}')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1280,900')

        self.driver = uc.Chrome(options=options, headless=headless, use_subprocess=True)
        self.wait = WebDriverWait(self.driver, 30)

        self.username = os.getenv("TWITTER_USERNAME")
        self.password = os.getenv("TWITTER_PASSWORD")

        self.followed_users_file = "followed_users.json"
        self.load_followed_users()

    def load_followed_users(self):
        try:
            with open(self.followed_users_file, 'r') as f:
                self.followed_users = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.followed_users = {}

    def save_followed_users(self):
        with open(self.followed_users_file, 'w') as f:
            json.dump(self.followed_users, f)

    def human_like_action(self, min_sec=2, max_sec=6):
        wait_time = random.uniform(min_sec, max_sec)
        logger.info(f"{wait_time:.1f}秒待機中...")
        time.sleep(wait_time)

    def _is_logged_in(self):
        try:
            self.driver.find_element(By.XPATH, "//a[@data-testid='AppTabBar_Home_Link']")
            return True
        except NoSuchElementException:
            return False

    def login(self, wait_minutes=5):
        self.driver.get("https://x.com/home")
        self.human_like_action(3, 5)

        if self._is_logged_in():
            logger.info("セッション有効：ログインをスキップしました")
            return

        print("\n" + "=" * 70)
        print("  Chromeブラウザが開きました。Xに手動でログインしてください")
        print(f"  ログイン完了を自動検知して処理を続行します（最大{wait_minutes}分待機）")
        print("  ※一度ログインすればchrome_profileに保存され次回からは自動スキップ")
        print("=" * 70 + "\n")

        self.driver.get("https://x.com/i/flow/login")

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

        try:
            self.driver.save_screenshot("login_timeout.png")
        except Exception:
            pass
        raise TimeoutException(f"{wait_minutes}分以内にログインが完了しませんでした。再実行してログインしてください。")

    def generate_tweet_content(self, topic):
        """240文字以内でツイートを生成し、超過時は切り捨てる"""
        try:
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=300,
                system=(
                    "あなたは恋愛・パートナーシップの悩みに寄り添うアドバイザーです。"
                    "浮気の不安や疑惑を抄える人の気持ちに共感しながら、"
                    "寄り添いかつ前向きなトーンでツイートを作成してください。"
                    "「必ず240文字以内」に収めること。業者・広告っぽくならないこと。"
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"次のトピックに関するハッシュタグを含むつぶやきを生成してください: {topic}\n\n"
                        "ルール:\n"
                        "- 【必須】240文字以内（超過絶対不可）\n"
                        "- ターゲット層：パートナーへの不安・浮気の悩みを持つ人\n"
                        "- トーン：共感的、親しみやすい、前向き\n"
                        "- 関連するハッシュタグを含める\n"
                        "- 業者・広告のような文体は避ける"
                    )
                }]
            )
            content = response.content[0].text.strip()
            # 280文字超過の安全剰り捨て
            if len(content) > 280:
                content = content[:276] + '...'
            logger.info(f"生成ツイート({len(content)}文字): {content[:50]}...")
            return content
        except Exception as e:
            logger.error(f"ツイート生成エラー: {e}")
            return f"今日の{topic}について考えてみました。 #恋愛相談 #恋愛不安"

    def _safe_click(self, element):
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.3)
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)

    def _type_text(self, element, text):
        self._safe_click(element)
        time.sleep(0.3)
        try:
            self.driver.execute_cdp_cmd("Input.insertText", {"text": text})
        except Exception:
            safe_text = ''.join(c for c in text if ord(c) < 0x10000)
            element.send_keys(safe_text)

    def _parse_count(self, text):
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
        followers = stats['followers']
        following = stats['following']
        if followers < 20:
            logger.info(f"@{uname} スキップ: フォロワー数が少なすぎます ({followers}人)")
            return False
        if following > 5000:
            logger.info(f"@{uname} スキップ: フォロー数が多すぎます ({following}人)")
            return False
        if following / max(followers, 1) > 10:
            logger.info(f"@{uname} スキップ: フォロー/フォロワー比が異常 ({following}/{followers})")
            return False
        if not stats['has_bio']:
            logger.info(f"@{uname} スキップ: bioなし")
            return False
        return True

    def _like_recent_tweets(self, uname, count=2):
        """profileページのツイート記事内のいいねボタンを正確に指定してフォロー前にいいね"""
        liked = 0
        try:
            # ツイートタイムラインが読み込まれるまで待機
            self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//article[@data-testid='tweet']"))
            )
            # article内のいいねボタンに絞り込む（業者系リツイートを除外するため）
            like_buttons = self.driver.find_elements(
                By.XPATH, "//article[@data-testid='tweet']//button[@data-testid='like']"
            )
            for btn in like_buttons[:count]:
                try:
                    self._safe_click(btn)
                    liked += 1
                    self.human_like_action(1, 2)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"@{uname} のいいねスキップ: {e}")
        if liked > 0:
            logger.info(f"@{uname} のツイートに{liked}件いいねしました（フォロー前）")
        return liked

    def post_tweet(self, content):
        try:
            self.driver.get("https://x.com/home")
            self.human_like_action(2, 4)

            tweet_box = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//div[@data-testid='tweetTextarea_0']"))
            )
            self._type_text(tweet_box, content)
            self.human_like_action(1, 2)

            post_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[@data-testid='tweetButtonInline']"))
            )
            self._safe_click(post_button)
            logger.info(f"ツイート投稿成功: {content[:50]}...")
            self.human_like_action(2, 4)
        except Exception as e:
            logger.error(f"ツイート投稿エラー: {e}")

    def follow_by_keyword_search(self, keyword, count=80):
        """KEYWORDSの組み合わせ検索で悩みを持つ個人アカウントをフォロー。
        5時間でcount人完了 = 1人あたり素4分
        - 通常待機: 180-220秒
        - 10人ごとの休憩: 300-360秒
        """
        followed_count = 0
        # 避けるキーワードが尽きたら次のキーワードに移る
        keywords_to_try = [keyword] + random.sample(
            [k for k in KEYWORDS if k != keyword],
            min(len(KEYWORDS) - 1, 8)
        )

        for current_keyword in keywords_to_try:
            if followed_count >= count:
                break
            try:
                query = current_keyword.replace(' ', '%20')
                self.driver.get(
                    f"https://x.com/search?q={query}&src=typed_query&f=live"
                )
                self.human_like_action(3, 5)

                # スクロールしてツイートを追加読み込み
                for _ in range(5):
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    self.human_like_action(2, 3)

                # 検索結果のツイート記事の投稿者のみを取得（article内に絞り込む）
                user_links = self.driver.find_elements(
                    By.XPATH,
                    "//article[@data-testid='tweet']//div[@data-testid='User-Name"]//a[contains(@href, '/') and not(contains(@href, '/status/'))]"
                )
                usernames = []
                for link in user_links:
                    href = link.get_attribute('href')
                    if href:
                        uname = href.rstrip('/').split('/')[-1]
                        if uname and uname not in usernames and uname != self.username:
                            usernames.append(uname)

                logger.info(f"'{current_keyword}'検索で{len(usernames)}人発見")

                for uname in usernames:
                    if followed_count >= count:
                        break
                    if uname in self.followed_users:
                        logger.info(f"@{uname} は既にフォロー済み")
                        continue

                    try:
                        self.driver.get(f"https://x.com/{uname}")
                        self.human_like_action(2, 4)

                        # 品質フィルター
                        stats = self._get_user_stats()
                        if not self._is_quality_account(stats, uname):
                            continue

                        # フォロー前にいいね（2件）
                        self._like_recent_tweets(uname, count=2)
                        self.human_like_action(1, 3)

                        # フォロー
                        follow_button = self.wait.until(
                            EC.presence_of_element_located(
                                (By.XPATH,
                                 "//button[@data-testid='placementTracking']//span[text()='フォロー']")
                            )
                        )
                        self._safe_click(follow_button)
                        followed_count += 1
                        logger.info(
                            f"@{uname} をフォロー ({followed_count}/{count}) "
                            f"(フォロワー:{stats['followers']} フォロー:{stats['following']})"
                        )
                        self.followed_users[uname] = datetime.now().isoformat()
                        self.save_followed_users()

                        # 10人ごとに5分の長休憩、それ以外は3分待機
                        if followed_count % 10 == 0:
                            logger.info(f"{followed_count}人完了。長休憩中（5分前後）...")
                            self.human_like_action(300, 360)
                        else:
                            self.human_like_action(180, 220)

                    except TimeoutException:
                        logger.info(f"@{uname} はフォロー済みかボタンが見つかりません")
                    except Exception as e:
                        logger.error(f"フォローエラー (@{uname}): {e}")

            except Exception as e:
                logger.error(f"キーワード検索エラー ({current_keyword}): {e}")

        logger.info(f"合計{followed_count}人をフォローしました")

    def auto_like_by_keyword(self, keyword, count=10):
        try:
            query = keyword.replace(' ', '%20')
            self.driver.get(f"https://x.com/search?q={query}&src=typed_query&f=live")
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

    def unfollow_non_followers(self, days=7):
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

                following_button = self.wait.until(
                    EC.presence_of_element_located(
                        (By.XPATH,
                         "//button[@data-testid='placementTracking']//span[text()='フォロー中']")
                    )
                )
                self._safe_click(following_button)
                self.human_like_action(1, 2)

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
        def _quit():
            try:
                self.driver.quit()
            except Exception:
                pass
        t = threading.Thread(target=_quit, daemon=True)
        t.start()
        t.join(timeout=10)
        if t.is_alive():
            logger.warning("ブラウザの終了がタイムアウトしました。Chromeプロセスは手動で終了してください。")


TOPICS = [
    'パートナーのSNSでの些細な変化が浮気の兆候かもしれない理由',
    '急にスマホを肌身離さず持つようになったパートナーの心理',
    '週末の予定をぼかし始めたパートナーに見られる行動パターン',
    '直感は嘘をつかない。でも証拠が必要な理由',
    '信頼と疑心の間で揺れる毎日から抜け出す方法',
    '彼の言動に違和感を感じ始めたときに確認すべきこと',
    '自分を大切にできない男性から離れる勇気の持ち方',
    '不安な毎日から抜け出すための具体的な第一歩',
    '自分の価値を再認識することで変わる恋愛観',
    '心理カウンセラーが教える浮気男性によく見られる口癖と行動',
    'パートナーの浮気を見抜いた3つのポイントとその後の対処法',
    '不安な日々から解放された女性の体験談と転機になった出来事',
    '信頼関係を再構築した夫婦が実践した具体的なコミュニケーション',
]

# 浮気を疑っている・不安を持つ個人が実際につぶやくワードの組み合わせ
KEYWORDS = [
    '彼氏 最近 冷たい',
    '旦那 帰り 遅い 怪しい',
    '浮気 してるかな',
    '彼氏 嘘 ついてる',
    '返信 急に 遅くなった',
    'スマホ 見せてくれない',
    '急に 優しくなった 怪しい',
    '残業 多すぎ 怪しい',
    '旦那 休日 どこ 行ってた',
    '信じたい でも 不安',
    '浮気 疑いたくない',
    '彼 最近 おかしい',
]


if __name__ == "__main__":
    bot = TwitterAutomation(headless=False)

    try:
        bot.login()

        topic = random.choice(TOPICS)
        content = bot.generate_tweet_content(topic)
        bot.post_tweet(content)

        # キーワード組み合わせ検索で500時間かけて８０人フォロー
        keyword = random.choice(KEYWORDS)
        bot.follow_by_keyword_search(keyword, count=80)

        keyword = random.choice(KEYWORDS)
        bot.auto_like_by_keyword(keyword, count=10)

        bot.unfollow_non_followers(days=7)
    finally:
        bot.close()
