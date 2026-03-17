"""
ストレージ管理
分析結果をMarkdownファイルに保存し、インデックスを更新する
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from analyzer import Analysis
from config import NOTES_DIR


STATE_FILE = Path(__file__).parent / ".state.json"


def _load_state() -> dict:
    """前回実行時の状態を読み込む（差分取得用）"""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_tweet_id": None, "processed_ids": []}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_last_tweet_id() -> str | None:
    """最後に処理したツイートIDを返す（差分取得に使用）"""
    return _load_state().get("last_tweet_id")


def _format_markdown(analysis: Analysis) -> str:
    """Analysis を Markdown テキストに変換する"""
    tweet = analysis.tweet
    jst_time = tweet.created_at.strftime("%Y-%m-%d %H:%M")

    # 背景を箇条書きに
    backgrounds_md = "\n".join(f"・{bg}" for bg in analysis.backgrounds) if analysis.backgrounds else "・（情報不足）"

    # テンプレートに沿った形式
    template_section = f"""{analysis.reason}によるもの
キーワード:{analysis.keywords}
{backgrounds_md}

関連銘柄
{analysis.related_stocks if analysis.related_stocks else "（該当なし）"}"""

    return f"""# {analysis.stock_code} {analysis.stock_name}

**日時**: {jst_time} JST
**ツイートID**: [{tweet.id}](https://x.com/{_get_username()}/status/{tweet.id})

---

## 元ポスト

> {tweet.text.replace(chr(10), '  \n> ')}

---

## 株価上昇理由分析

{template_section}

---

*分析日時: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC*
"""


def _get_username() -> str:
    from config import TARGET_USERNAME
    return TARGET_USERNAME


def save_analysis(analysis: Analysis) -> Path:
    """
    分析結果をMarkdownファイルに保存する

    Returns:
        保存したファイルのパス
    """
    tweet = analysis.tweet
    date_str = tweet.created_at.strftime("%Y%m%d_%H%M")
    code = analysis.stock_code.replace("/", "-")
    filename = f"{date_str}_{code}.md"
    filepath = NOTES_DIR / filename

    content = _format_markdown(analysis)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  [保存] {filepath.name}")

    # 状態を更新
    state = _load_state()
    if not state.get("last_tweet_id") or int(tweet.id) > int(state["last_tweet_id"]):
        state["last_tweet_id"] = tweet.id
    if tweet.id not in state.get("processed_ids", []):
        state.setdefault("processed_ids", []).append(tweet.id)
    _save_state(state)

    return filepath


def save_analyses(analyses: list[Analysis]) -> list[Path]:
    """複数の分析結果を保存しインデックスを更新する"""
    paths = []
    for analysis in analyses:
        path = save_analysis(analysis)
        paths.append(path)

    if paths:
        update_index()

    return paths


def update_index() -> None:
    """notes/index.md を全ファイルから再生成する"""
    md_files = sorted(NOTES_DIR.glob("*.md"), reverse=True)
    md_files = [f for f in md_files if f.name != "index.md"]

    lines = [
        "# 株価上昇理由メモ (@shodousan)\n",
        f"*最終更新: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC*\n",
        "",
        "---",
        "",
        "| 日時 | 銘柄 | 理由 | キーワード |",
        "|------|------|------|-----------|",
    ]

    for path in md_files:
        try:
            text = path.read_text(encoding="utf-8")
            # ヘッダー行から銘柄情報を取得
            first_line = text.split("\n")[0].replace("# ", "")
            # 日時を抽出
            date_line = next((l for l in text.split("\n") if l.startswith("**日時**:")), "")
            date_val = date_line.replace("**日時**:", "").strip()
            # 理由を抽出
            reason_line = next((l for l in text.split("\n") if "によるもの" in l), "")
            reason = reason_line.replace("によるもの", "").strip()
            # キーワードを抽出
            kw_line = next((l for l in text.split("\n") if l.startswith("キーワード:")), "")
            kw = kw_line.replace("キーワード:", "").strip()

            lines.append(f"| {date_val} | [{first_line}]({path.name}) | {reason} | {kw} |")
        except Exception:
            continue

    lines.append("")
    index_path = NOTES_DIR / "index.md"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[INDEX] {index_path} を更新しました ({len(md_files)} 件)")
