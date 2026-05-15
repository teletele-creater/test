import os
import re
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

HASHTAGS = [
    '#浮気',
    '#不倫',
    '#信頼関係',
    '#恋愛相談',
    '#パートナー',
    '#浮気疑惑',
    '#既婚者',
    '#恋愛',
]


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
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-backgrounding-occluded-windows')
        options.add_argument('--disable-features=CalculateNativeWinOcclusion')

        self.driver = uc.Chrome(options=options, headless=headless, use_subprocess=True)
        self.wait = WebDriverWait(self.driver, 30)

        self.username = os.getenv("TWITTER_USERNAME")
        self.password = os.getenv("TWITTER_PASSWORD")

        self.followed_users_file = "followed_users.json"
        self.load_followed_users()

        os.makedirs("screenshots", exist_ok=True)

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

    def _screenshot(self, name):
        try:
            path = f"screenshots/{name}.png"
            self.driver.save_screenshot(path)
            logger.info(f"スクリーンショット保存: {path}")
        except Exception:
            pass

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

        self._screenshot("login_timeout")
        raise TimeoutException(f"{wait_minutes}分以内にログインが完了しませんでした。")

    def generate_tweet_content(self, topic):
        hashtag = random.choice(HASHTAGS)
        try:
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=300,
                system=(
                    "あなたはベテランの心理カウンセラー兼浮気調査の専門家です。"
                    "一般の人は知らない、専門家だけが知る浮気・裏切り・嘘を見抜く具体的な行動サインや心理パターンを、"
                    "「えっそうなの！？」と思わず読み進めたくなる豆知識・小ネタとして投稿してください。"
                    "押し付けがましくなく、自然なつぶやき口調で。広告・業者・AIっぽさは絶対NG。"
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"テーマ：{topic}\n\n"
                        "次のルールでつぶやきを書いて：\n"
                        "- 冒頭で「実は」「心理学的に」「カウンセラーとして言うと」など、専門家視点で引き込む書き出し\n"
                        "- 具体的な行動・仕草・口癖など「思い当たる！」と感じさせる細かい描写を1つだけ入れる\n"
                        "- 抽象論や精神論ではなく、観察できる具体的なサインを書く\n"
                        f"- 末尾にハッシュタグ「{hashtag}」を1つだけ付ける（他のハッシュタグ禁止）\n"
                        f"- ハッシュタグ込みで130文字以内（厳守）\n"
                        "- 普通の人が個人のXでつぶやいてる感じの自然な日本語"
                    )
                }]
            )
            content = response.content[0].text.strip()
            content = re.sub(r'#\S+', '', content).strip()
            content = f"{content} {hashtag}"
            if len(content) > 140:
                max_body = 140 - len(hashtag) - 4
                content = content[:max_body].rstrip() + f"... {hashtag}"
            logger.info(f"生成ツイート({len(content)}文字): {content}")
            return content
        except Exception as e:
            logger.error(f"ツイート生成エラー: {e}")
            return f"パートナーへの不安、一人で抱え込まないで。 {hashtag}"

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
            stat_links = self.driver.find_elements(
                By.XPATH,
                "//a[contains(@href, '/following') or contains(@href, '/followers') or contains(@href, '/verified_followers')]"
            )
            for link in stat_links:
                href = link.get_attribute('href') or ''
                if '/followers_you_follow' in href:
                    continue
                text = link.text or ''
                if not text:
                    continue
                num_text = text.replace('\n', ' ').split()[0] if text.strip() else ''
                if 'フォロワー' in text or 'Followers' in text:
                    stats['followers'] = self._parse_count(num_text)
                elif 'フォロー中' in text or 'Following' in text:
                    stats['following'] = self._parse_count(num_text)
        except Exception as e:
            logger.debug(f"stats取得エラー: {e}")

        try:
            self.driver.find_element(By.XPATH, "//div[@data-testid='UserDescription']")
            stats['has_bio'] = True
        except NoSuchElementException:
            pass
        return stats

    def _is_quality_account(self, stats, uname):
        followers = stats['followers']
        following = stats['following']
        if followers < 10:
            logger.info(f"@{uname} スキップ: フォロワー数が少なすぎます ({followers}人)")
            return False
        if followers > 2000:
            logger.info(f"@{uname} スキップ: フォロワー数が多すぎます ({followers}人、業者/インフルエンサーの可能性)")
            return False
        if following > 8000:
            logger.info(f"@{uname} スキップ: フォロー数が多すぎます ({following}人)")
            return False
        if followers > 0 and following / followers > 15:
            logger.info(f"@{uname} スキップ: フォロー/フォロワー比が異常 ({following}/{followers})")
            return False
        if not stats['has_bio']:
            logger.info(f"@{uname} bioなし（フォロー続行）")
        return True

    def _like_recent_tweets(self, uname, count=2):
        liked = 0
        short_wait = WebDriverWait(self.driver, 8)
        try:
            short_wait.until(
                EC.presence_of_element_located((By.XPATH, "//article[@data-testid='tweet']"))
            )
            like_buttons = self.driver.find_elements(
                By.XPATH, "//article[@data-testid='tweet']//button[@data-testid='like']"
            )
            for btn in like_buttons[:count]:
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(0.5)
                    self._safe_click(btn)
                    liked += 1
                    self.human_like_action(1, 2)
                except Exception:
                    pass
        except Exception:
            logger.info(f"@{uname} のいいねスキップ（ツイート未検出）")
        if liked > 0:
            logger.info(f"@{uname} のツイートに{liked}件いいねしました(フォロー前)")
        return liked

    def _click_follow_button(self, uname):
        """フォローボタンをクリックし、実際にフォロー成功したか検証する。"""
        primary_xpath = (
            "//button[contains(@data-testid, '-follow') "
            "and not(contains(@data-testid, 'unfollow'))]"
        )
        fallback_xpaths = [
            "//button[@aria-label and contains(@aria-label, 'フォロー') "
            "and not(contains(@aria-label, 'フォロー中')) "
            "and not(contains(@aria-label, 'リクエスト'))]",
            "//div[@data-testid='primaryColumn']//button[.//span[text()='フォロー']]",
            "//div[@data-testid='placementTracking']//button[.//span[text()='フォロー']]",
        ]

        clicked = False
        try:
            btn = WebDriverWait(self.driver, 6).until(
                EC.element_to_be_clickable((By.XPATH, primary_xpath))
            )
            self._safe_click(btn)
            clicked = True
        except Exception:
            pass

        if not clicked:
            for xpath in fallback_xpaths:
                try:
                    elems = self.driver.find_elements(By.XPATH, xpath)
                    for elem in elems:
                        if elem.is_displayed() and elem.is_enabled():
                            self._safe_click(elem)
                            clicked = True
                            break
                except Exception:
                    continue
                if clicked:
                    break

        if not clicked:
            self._screenshot(f"no_follow_btn_{uname}")
            try:
                already = self.driver.find_elements(
                    By.XPATH,
                    "//button[contains(@data-testid, '-unfollow')] | "
                    "//button[@aria-label and contains(@aria-label, 'フォロー中')]"
                )
                if already:
                    return 'already_following'
            except Exception:
                pass
            return False

        time.sleep(2)
        self._screenshot(f"after_follow_{uname}")

        try:
            confirmed = self.driver.find_elements(
                By.XPATH,
                "//button[contains(@data-testid, '-unfollow')] | "
                "//button[@aria-label and contains(@aria-label, 'フォロー中')]"
            )
            if confirmed:
                return True
        except Exception:
            pass

        try:
            still_follow = self.driver.find_elements(By.XPATH, primary_xpath)
            if still_follow:
                logger.warning(f"@{uname} フォローボタンがまだ存在→クリック失敗の可能性")
                return False
        except Exception:
            pass

        return True

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
        followed_count = 0
        keywords_to_try = [keyword] + random.sample(
            [k for k in KEYWORDS if k != keyword],
            min(len(KEYWORDS) - 1, 8)
        )

        for current_keyword in keywords_to_try:
            if followed_count >= count:
                break
            try:
                query = current_keyword.replace(' ', '%20')
                self.driver.get(f"https://x.com/search?q={query}&src=typed_query&f=live")
                self.human_like_action(3, 5)

                for _ in range(5):
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    self.human_like_action(2, 3)

                user_links = self.driver.find_elements(
                    By.XPATH,
                    "//article[@data-testid='tweet']//div[@data-testid='User-Name']//a[contains(@href, '/') and not(contains(@href, '/status/'))]"
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

                        stats = self._get_user_stats()
                        logger.info(f"@{uname} ステット: フォロワー={stats['followers']} フォロー={stats['following']} bio={stats['has_bio']}")
                        if not self._is_quality_account(stats, uname):
                            continue

                        self._like_recent_tweets(uname, count=2)
                        self.human_like_action(1, 3)

                        result = self._click_follow_button(uname)
                        if result is True:
                            followed_count += 1
                            logger.info(
                                f"@{uname} をフォロー成功 ({followed_count}/{count}) "
                                f"(フォロワー:{stats['followers']} フォロー:{stats['following']})"
                            )
                            self.followed_users[uname] = datetime.now().isoformat()
                            self.save_followed_users()

                            if followed_count % 10 == 0:
                                logger.info(f"{followed_count}人完了。長休憩中（5分前後）...")
                                self.human_like_action(300, 360)
                            else:
                                self.human_like_action(180, 220)
                        elif result == 'already_following':
                            logger.info(f"@{uname} 既にフォロー中。キャッシュ")
                            self.followed_users[uname] = datetime.now().isoformat()
                            self.save_followed_users()
                        else:
                            logger.warning(f"@{uname} フォロー失敗。screenshots/after_follow_{uname}.png を確認してください")

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

                unfollow_xpaths = [
                    "//button[contains(@data-testid, '-unfollow')]",
                    "//button[.//span[normalize-space(text())='フォロー中']]",
                ]
                following_button = None
                for xp in unfollow_xpaths:
                    try:
                        following_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, xp))
                        )
                        break
                    except Exception:
                        continue
                if not following_button:
                    logger.info(f"@{uname} は既にアンフォロー済みの可能性")
                    del self.followed_users[uname]
                    self.save_followed_users()
                    continue

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
            logger.warning("ブラウザの終了がタイムアウトしました。")


TOPICS = [
    '浮気している人の8割が無意識にやってしまうスマホの置き方の癖',
    '嘘をついている人の視線の動きには3秒のズレがあるという心理学の話',
    'パートナーが急に新しい下着を買い始めた時に隠れている本当の理由',
    '浮気男性が増やしがちな「ある一言」の頻度の変化',
    '会話中に質問返しが急に増えたら気をつけるべき心理的サイン',
    'カウンセリングで聞いた、浮気バレ直前の人の睡眠時間の変化',
    '指輪を外す癖がある人に共通する潜在的な心理状態',
    '浮気されている人ほど気づかないパートナーの「香水ローテーション」',
    'メール文末の絵文字の使い方で見抜く、相手の心理状態の変化',
    '急に運動を始めた既婚男性に統計的に多い背景',
    '心理学者しか知らない、嘘をついている時の声のピッチの上がり方',
    '浮気を隠している人が無意識に避けるようになる話題のジャンル',
    'スマホを伏せて置く頻度が急に増えた人の心理的特徴',
    'パートナーが急に予定の説明を細かくし始めたら逆に警戒すべき理由',
    '行動心理学的に、嘘をつく人ほど「絶対」「本当に」を多用するという話',
    '浮気期の人に共通する、SNSのアイコン変更タイミングのパターン',
    '関係カウンセラーが現場で見てきた、浮気を3秒で見抜く視線の癖',
    'クローゼットの服のかけ方が変わった時にパートナーに起きていること',
    '「最近忙しい」が口癖になった時に裏で進行している心理プロセス',
    '車のシートの位置が微妙にズレている時に考えるべき可能性',
]

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
    '浮気 疑いたくなった',
    '彼 最近 おかしい',
]


if __name__ == "__main__":
    bot = TwitterAutomation(headless=False)

    try:
        bot.login()

        topic = random.choice(TOPICS)
        content = bot.generate_tweet_content(topic)
        bot.post_tweet(content)

        keyword = random.choice(KEYWORDS)
        bot.follow_by_keyword_search(keyword, count=80)

        keyword = random.choice(KEYWORDS)
        bot.auto_like_by_keyword(keyword, count=10)

        bot.unfollow_non_followers(days=7)
    finally:
        bot.close()
