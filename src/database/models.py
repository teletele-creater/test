"""
データベースモデル定義
SQLiteを使用してSPC情報・上場企業情報・分析結果を管理
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from config.settings import DB_PATH, DATA_DIR
from src.utils.logger import setup_logger

logger = setup_logger("database")

# テーブル定義SQL
CREATE_TABLES_SQL = """
-- 新規設立法人（SPC候補）テーブル
CREATE TABLE IF NOT EXISTS corporations (
    corporate_number TEXT PRIMARY KEY,     -- 法人番号（13桁）
    name TEXT NOT NULL,                     -- 法人名
    name_kana TEXT,                          -- 法人名（カナ）
    entity_type TEXT,                        -- 法人種別（合同会社、株式会社等）
    prefecture TEXT,                         -- 都道府県
    city TEXT,                               -- 市区町村
    address TEXT,                            -- 住所
    capital TEXT,                            -- 資本金
    established_date TEXT,                  -- 設立日
    representative TEXT,                    -- 代表者名
    purpose TEXT,                            -- 目的・事業内容
    source TEXT,                             -- 情報取得元
    fetched_at TEXT NOT NULL,               -- 取得日時
    is_spc_candidate INTEGER DEFAULT 0,    -- SPC候補フラグ
    spc_score REAL DEFAULT 0.0,            -- SPC可能性スコア (0-1)
    notes TEXT                              -- 備考
);

-- 上場企業テーブル
CREATE TABLE IF NOT EXISTS listed_companies (
    code TEXT PRIMARY KEY,                  -- 証券コード
    name TEXT NOT NULL,                     -- 企業名
    name_en TEXT,                           -- 企業名（英語）
    market TEXT,                            -- 市場区分
    sector TEXT,                            -- 業種
    corporate_number TEXT,                  -- 法人番号
    market_cap REAL,                        -- 時価総額
    pbr REAL,                               -- PBR
    owner_ratio REAL,                       -- オーナー持株比率
    updated_at TEXT                          -- 更新日時
);

-- MBO候補マッチングテーブル
CREATE TABLE IF NOT EXISTS mbo_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spc_corporate_number TEXT,             -- SPC法人番号
    listed_company_code TEXT,              -- 関連上場企業コード（推定）
    match_score REAL DEFAULT 0.0,          -- マッチングスコア (0-1)
    match_reasons TEXT,                     -- マッチング理由（JSON）
    status TEXT DEFAULT 'detected',        -- ステータス: detected/investigating/confirmed/dismissed
    detected_at TEXT NOT NULL,             -- 検出日時
    confirmed_at TEXT,                     -- 確認日時
    notes TEXT,                            -- 備考
    FOREIGN KEY (spc_corporate_number) REFERENCES corporations(corporate_number),
    FOREIGN KEY (listed_company_code) REFERENCES listed_companies(code)
);

-- EDINET書類テーブル
CREATE TABLE IF NOT EXISTS edinet_documents (
    doc_id TEXT PRIMARY KEY,               -- 書類管理番号
    doc_type TEXT,                          -- 書類種別
    filer_name TEXT,                        -- 提出者名
    title TEXT,                             -- タイトル
    filing_date TEXT,                       -- 提出日
    target_company TEXT,                   -- 対象企業名
    is_mbo_related INTEGER DEFAULT 0,     -- MBO関連フラグ
    content_summary TEXT,                  -- 内容サマリー
    fetched_at TEXT NOT NULL               -- 取得日時
);

-- 適時開示テーブル
CREATE TABLE IF NOT EXISTS tdnet_disclosures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    disclosure_id TEXT UNIQUE,             -- 開示ID
    company_code TEXT,                     -- 証券コード
    company_name TEXT,                     -- 企業名
    title TEXT,                            -- タイトル
    disclosed_at TEXT,                     -- 開示日時
    is_mbo_related INTEGER DEFAULT 0,     -- MBO関連フラグ
    url TEXT,                              -- 文書URL
    fetched_at TEXT NOT NULL               -- 取得日時
);

-- 監視ログ
CREATE TABLE IF NOT EXISTS monitor_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,                  -- データソース名
    action TEXT NOT NULL,                  -- アクション
    result TEXT,                           -- 結果
    details TEXT,                          -- 詳細（JSON）
    executed_at TEXT NOT NULL              -- 実行日時
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_corp_established ON corporations(established_date);
CREATE INDEX IF NOT EXISTS idx_corp_spc_candidate ON corporations(is_spc_candidate);
CREATE INDEX IF NOT EXISTS idx_corp_spc_score ON corporations(spc_score);
CREATE INDEX IF NOT EXISTS idx_corp_entity_type ON corporations(entity_type);
CREATE INDEX IF NOT EXISTS idx_mbo_status ON mbo_candidates(status);
CREATE INDEX IF NOT EXISTS idx_mbo_score ON mbo_candidates(match_score);
CREATE INDEX IF NOT EXISTS idx_edinet_type ON edinet_documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_edinet_mbo ON edinet_documents(is_mbo_related);
CREATE INDEX IF NOT EXISTS idx_tdnet_mbo ON tdnet_disclosures(is_mbo_related);
"""


class Database:
    """SQLiteデータベース管理クラス"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """テーブル作成"""
        with self._connect() as conn:
            conn.executescript(CREATE_TABLES_SQL)
        logger.info(f"Database initialized: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _now(self) -> str:
        return datetime.now().isoformat()

    # === 法人（SPC候補）操作 ===

    def upsert_corporation(self, corp: dict) -> bool:
        """法人情報をupsert。新規の場合Trueを返す"""
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT corporate_number FROM corporations WHERE corporate_number = ?",
                (corp["corporate_number"],)
            ).fetchone()

            if existing:
                conn.execute("""
                    UPDATE corporations SET
                        name=?, name_kana=?, entity_type=?, prefecture=?,
                        city=?, address=?, capital=?, established_date=?,
                        representative=?, purpose=?, source=?, fetched_at=?,
                        is_spc_candidate=?, spc_score=?, notes=?
                    WHERE corporate_number=?
                """, (
                    corp.get("name"), corp.get("name_kana"), corp.get("entity_type"),
                    corp.get("prefecture"), corp.get("city"), corp.get("address"),
                    corp.get("capital"), corp.get("established_date"),
                    corp.get("representative"), corp.get("purpose"),
                    corp.get("source"), self._now(),
                    corp.get("is_spc_candidate", 0), corp.get("spc_score", 0.0),
                    corp.get("notes"),
                    corp["corporate_number"],
                ))
                return False
            else:
                conn.execute("""
                    INSERT INTO corporations (
                        corporate_number, name, name_kana, entity_type,
                        prefecture, city, address, capital, established_date,
                        representative, purpose, source, fetched_at,
                        is_spc_candidate, spc_score, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    corp["corporate_number"], corp.get("name"), corp.get("name_kana"),
                    corp.get("entity_type"), corp.get("prefecture"), corp.get("city"),
                    corp.get("address"), corp.get("capital"), corp.get("established_date"),
                    corp.get("representative"), corp.get("purpose"),
                    corp.get("source"), self._now(),
                    corp.get("is_spc_candidate", 0), corp.get("spc_score", 0.0),
                    corp.get("notes"),
                ))
                return True

    def get_spc_candidates(self, min_score: float = 0.3) -> list:
        """SPC候補を取得"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM corporations WHERE is_spc_candidate = 1 AND spc_score >= ? ORDER BY spc_score DESC",
                (min_score,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_corporations(self, days: int = 30) -> list:
        """直近N日以内に設立された法人を取得"""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM corporations
                   WHERE established_date >= date('now', ?)
                   ORDER BY established_date DESC""",
                (f"-{days} days",)
            ).fetchall()
            return [dict(r) for r in rows]

    # === 上場企業操作 ===

    def upsert_listed_company(self, company: dict):
        """上場企業情報をupsert"""
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO listed_companies (
                    code, name, name_en, market, sector,
                    corporate_number, market_cap, pbr, owner_ratio, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name, name_en=excluded.name_en,
                    market=excluded.market, sector=excluded.sector,
                    corporate_number=excluded.corporate_number,
                    market_cap=excluded.market_cap, pbr=excluded.pbr,
                    owner_ratio=excluded.owner_ratio, updated_at=excluded.updated_at
            """, (
                company["code"], company["name"], company.get("name_en"),
                company.get("market"), company.get("sector"),
                company.get("corporate_number"), company.get("market_cap"),
                company.get("pbr"), company.get("owner_ratio"), self._now(),
            ))

    def get_listed_companies(self) -> list:
        """全上場企業を取得"""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM listed_companies ORDER BY code").fetchall()
            return [dict(r) for r in rows]

    def search_listed_companies(self, keyword: str) -> list:
        """上場企業をキーワード検索"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM listed_companies WHERE name LIKE ? OR name_en LIKE ?",
                (f"%{keyword}%", f"%{keyword}%")
            ).fetchall()
            return [dict(r) for r in rows]

    # === MBO候補操作 ===

    def add_mbo_candidate(self, candidate: dict) -> int:
        """MBO候補を追加"""
        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT INTO mbo_candidates (
                    spc_corporate_number, listed_company_code,
                    match_score, match_reasons, status, detected_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                candidate["spc_corporate_number"],
                candidate.get("listed_company_code"),
                candidate.get("match_score", 0.0),
                candidate.get("match_reasons", ""),
                candidate.get("status", "detected"),
                self._now(),
                candidate.get("notes"),
            ))
            return cursor.lastrowid

    def get_mbo_candidates(self, status: str = None) -> list:
        """MBO候補を取得"""
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM mbo_candidates WHERE status = ? ORDER BY match_score DESC",
                    (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM mbo_candidates ORDER BY match_score DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    # === EDINET書類操作 ===

    def upsert_edinet_document(self, doc: dict) -> bool:
        """EDINET書類をupsert。新規の場合Trueを返す"""
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT doc_id FROM edinet_documents WHERE doc_id = ?",
                (doc["doc_id"],)
            ).fetchone()
            if existing:
                return False
            conn.execute("""
                INSERT INTO edinet_documents (
                    doc_id, doc_type, filer_name, title, filing_date,
                    target_company, is_mbo_related, content_summary, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc["doc_id"], doc.get("doc_type"), doc.get("filer_name"),
                doc.get("title"), doc.get("filing_date"),
                doc.get("target_company"), doc.get("is_mbo_related", 0),
                doc.get("content_summary"), self._now(),
            ))
            return True

    # === 適時開示操作 ===

    def upsert_tdnet_disclosure(self, disc: dict) -> bool:
        """適時開示をupsert。新規の場合Trueを返す"""
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM tdnet_disclosures WHERE disclosure_id = ?",
                (disc.get("disclosure_id"),)
            ).fetchone()
            if existing:
                return False
            conn.execute("""
                INSERT INTO tdnet_disclosures (
                    disclosure_id, company_code, company_name, title,
                    disclosed_at, is_mbo_related, url, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                disc.get("disclosure_id"), disc.get("company_code"),
                disc.get("company_name"), disc.get("title"),
                disc.get("disclosed_at"), disc.get("is_mbo_related", 0),
                disc.get("url"), self._now(),
            ))
            return True

    # === 監視ログ ===

    def add_monitor_log(self, source: str, action: str, result: str = None, details: str = None):
        """監視ログを追加"""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO monitor_log (source, action, result, details, executed_at) VALUES (?, ?, ?, ?, ?)",
                (source, action, result, details, self._now())
            )
