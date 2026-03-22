"""データベース管理モジュール（SQLite）"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import config


def get_db_path() -> Path:
    return config.db_path


@contextmanager
def get_connection():
    """DBコネクションのコンテキストマネージャー"""
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """データベースの初期化（テーブル作成）"""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                -- Amazon情報
                amazon_url TEXT NOT NULL UNIQUE,
                amazon_title TEXT,
                amazon_price INTEGER,
                amazon_in_stock BOOLEAN DEFAULT 1,
                amazon_asin TEXT,
                -- メルカリ情報
                mercari_keyword TEXT,
                mercari_avg_sold_price INTEGER,
                mercari_sold_count INTEGER DEFAULT 0,
                -- 利益情報
                estimated_profit INTEGER,
                shipping_cost INTEGER DEFAULT 700,
                -- ステータス管理
                status TEXT DEFAULT 'researched'
                    CHECK(status IN (
                        'researched',   -- リサーチ済み
                        'listed',       -- メルカリに出品中
                        'out_of_stock', -- Amazon在庫切れ
                        'paused',       -- メルカリ出品停止済み
                        'sold',         -- 販売完了
                        'archived'      -- アーカイブ
                    )),
                -- 直前のステータス（ステータス遷移追跡用）
                previous_status TEXT,
                -- メタデータ
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked_at TIMESTAMP,
                notes TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
            CREATE INDEX IF NOT EXISTS idx_items_amazon_url ON items(amazon_url);
            CREATE INDEX IF NOT EXISTS idx_items_profit ON items(estimated_profit);

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                amazon_price INTEGER,
                mercari_avg_price INTEGER,
                estimated_profit INTEGER,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS stock_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                in_stock BOOLEAN NOT NULL,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL,
                message TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN DEFAULT 1,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            );
        """)
        # 既存DBにprevious_statusカラムがない場合は追加
        try:
            conn.execute("SELECT previous_status FROM items LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE items ADD COLUMN previous_status TEXT")


def upsert_item(
    amazon_url: str,
    amazon_title: Optional[str] = None,
    amazon_price: Optional[int] = None,
    amazon_in_stock: bool = True,
    amazon_asin: Optional[str] = None,
    mercari_keyword: Optional[str] = None,
    mercari_avg_sold_price: Optional[int] = None,
    mercari_sold_count: int = 0,
    estimated_profit: Optional[int] = None,
    shipping_cost: int = 700,
    status: str = "researched",
) -> int:
    """商品情報をUPSERT（存在すれば更新、なければ挿入）"""
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO items (
                amazon_url, amazon_title, amazon_price, amazon_in_stock,
                amazon_asin, mercari_keyword, mercari_avg_sold_price,
                mercari_sold_count, estimated_profit, shipping_cost,
                status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(amazon_url) DO UPDATE SET
                amazon_title = COALESCE(excluded.amazon_title, amazon_title),
                amazon_price = COALESCE(excluded.amazon_price, amazon_price),
                amazon_in_stock = excluded.amazon_in_stock,
                amazon_asin = COALESCE(excluded.amazon_asin, amazon_asin),
                mercari_keyword = COALESCE(excluded.mercari_keyword, mercari_keyword),
                mercari_avg_sold_price = COALESCE(excluded.mercari_avg_sold_price, mercari_avg_sold_price),
                mercari_sold_count = excluded.mercari_sold_count,
                estimated_profit = COALESCE(excluded.estimated_profit, estimated_profit),
                shipping_cost = excluded.shipping_cost,
                status = excluded.status,
                updated_at = ?
            """,
            (
                amazon_url, amazon_title, amazon_price, amazon_in_stock,
                amazon_asin, mercari_keyword, mercari_avg_sold_price,
                mercari_sold_count, estimated_profit, shipping_cost,
                status, now, now,
            ),
        )
        return cursor.lastrowid


def get_listed_items() -> list[dict]:
    """出品中（listed）の商品一覧を取得"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM items WHERE status = 'listed' ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]


def get_out_of_stock_listed_items() -> list[dict]:
    """在庫なし＆元々出品中だった商品一覧を取得

    status='out_of_stock' かつ previous_status='listed' の商品のみ返す。
    リサーチしただけの商品（researched → out_of_stock）は含まない。
    """
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM items
               WHERE status = 'out_of_stock'
                 AND previous_status = 'listed'
               ORDER BY id""",
        ).fetchall()
        return [dict(row) for row in rows]


def update_item_status(item_id: int, new_status: str):
    """商品のステータスを更新（直前のステータスも保持）"""
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            """UPDATE items
               SET previous_status = status,
                   status = ?,
                   updated_at = ?
               WHERE id = ?""",
            (new_status, now, item_id),
        )


def update_stock_status(item_id: int, in_stock: bool):
    """在庫ステータスを更新し、在庫チェック履歴を記録"""
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE items SET amazon_in_stock = ?, last_checked_at = ?, updated_at = ? WHERE id = ?",
            (in_stock, now, now, item_id),
        )
        conn.execute(
            "INSERT INTO stock_checks (item_id, in_stock) VALUES (?, ?)",
            (item_id, in_stock),
        )


def record_price_history(item_id: int, amazon_price: int, mercari_avg: int, profit: int):
    """価格履歴を記録"""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO price_history (item_id, amazon_price, mercari_avg_price, estimated_profit) VALUES (?, ?, ?, ?)",
            (item_id, amazon_price, mercari_avg, profit),
        )


def record_notification(item_id: int, notification_type: str, message: str, success: bool = True):
    """通知履歴を記録"""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO notifications (item_id, notification_type, message, success) VALUES (?, ?, ?, ?)",
            (item_id, notification_type, message, success),
        )


def get_profitable_items(min_profit: int = 3000) -> list[dict]:
    """利益がしきい値以上の商品一覧を取得"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM items WHERE estimated_profit >= ? ORDER BY estimated_profit DESC",
            (min_profit,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_all_items() -> list[dict]:
    """全商品一覧を取得"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM items ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def is_already_notified(item_id: int, notification_type: str) -> bool:
    """同じ商品に対して同じ種類の通知が既に送信済みかチェック（重複通知防止）"""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM notifications
               WHERE item_id = ? AND notification_type = ? AND success = 1""",
            (item_id, notification_type),
        ).fetchone()
        return row["cnt"] > 0
