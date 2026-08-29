"""
db.py - SQL Server Veritabanı Erişim Katmanı
===============================================
Engine oluşturma, tablo başlatma, veri okuma/yazma/silme.
Tüm connection'lar context manager ile yönetilir, leak riski yok.
GÖREV 1: Connection pool upgrade + @retry_on_db_error dekoratörü
GÖREV 2: Checkpoint (scan_sessions tablosu + 4 yeni fonksiyon)
"""

import time
import pyodbc
import pandas as pd
from functools import wraps
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, TimeoutError as SQLAlchemyTimeoutError
from config import (
    DB_SERVER, DB_NAME,
    DB_CONNECTION_POOL_SIZE, DB_CONNECTION_MAX_OVERFLOW,
    DB_CONNECTION_RECYCLE_SECONDS, DB_QUERY_TIMEOUT,
    RETRY_MAX_ATTEMPTS, RETRY_BACKOFF_FACTOR
)
from logger_setup import logger


# ==========================================================================
#  GÖREV 1: @retry_on_db_error Dekoratörü
# ==========================================================================

def retry_on_db_error(max_retries=None, backoff_factor=None):
    """Veritabanı işleminde hata olursa exponential backoff ile tekrar."""
    if max_retries is None:
        max_retries = RETRY_MAX_ATTEMPTS
    if backoff_factor is None:
        backoff_factor = RETRY_BACKOFF_FACTOR

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (OperationalError, SQLAlchemyTimeoutError, Exception) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = 1 * (backoff_factor ** attempt)
                        logger.warning(
                            f"[DB Retry] {func.__name__} denemesi {attempt+1}/{max_retries} basarisiz, "
                            f"{wait_time:.0f}s bekleniyor: {str(e)[:100]}"
                        )
                        time.sleep(wait_time)
            logger.error(f"[DB Retry] {func.__name__} tum {max_retries} deneme basarisiz: {last_exception}")
            raise last_exception
        return wrapper
    return decorator


# ==========================================================================
#  DB INIT
# ==========================================================================

def create_db_if_not_exists():
    """SQL Server'da OtoGaleriDB yoksa oluşturur."""
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_SERVER};DATABASE=master;Trusted_Connection=yes;autocommit=True"
    )
    try:
        conn = pyodbc.connect(conn_str, autocommit=True)
        cursor = conn.cursor()
        cursor.execute(f"SELECT name FROM sys.databases WHERE name = N'{DB_NAME}'")
        if not cursor.fetchone():
            cursor.execute(f"CREATE DATABASE {DB_NAME}")
            logger.info(f"{DB_NAME} veritabani olusturuldu.")
        conn.close()
    except Exception as e:
        logger.error(f"Veritabani olusturma hatasi: {e}")


def get_engine():
    """SQLAlchemy engine döndürür. GÖREV 1: Büyütülmüş pool + timeout ayarları."""
    create_db_if_not_exists()
    conn_str = (
        f"mssql+pyodbc://@{DB_SERVER}/{DB_NAME}"
        f"?driver=ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes"
    )
    try:
        engine = create_engine(
            conn_str,
            pool_size=DB_CONNECTION_POOL_SIZE,
            max_overflow=DB_CONNECTION_MAX_OVERFLOW,
            pool_recycle=DB_CONNECTION_RECYCLE_SECONDS,
            pool_pre_ping=True,
            connect_args={"timeout": DB_QUERY_TIMEOUT}
        )
        # Bağlantıyı hemen test et
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info(
            f"[DB] Baglanti basarili. Pool: size={DB_CONNECTION_POOL_SIZE}, "
            f"overflow={DB_CONNECTION_MAX_OVERFLOW}, recycle={DB_CONNECTION_RECYCLE_SECONDS}s"
        )
        return engine
    except Exception as e:
        logger.error(
            f"Veritabani baglantisi kurulamadi: {e}. "
            f"Kontrol listesi: 1) SQL Server calisiyor mu? "
            f"2) DB_SERVER dogru mu? (Su an: {DB_SERVER}) "
            f"3) Firewall port 1433'u aciyor mu?"
        )
        return None


def init_tables(engine):
    """Cars ve scan_sessions tablolarını yoksa oluşturur."""
    if not engine:
        return
    try:
        with engine.begin() as conn:
            # Cars tablosu
            conn.execute(text("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Cars' AND xtype='U')
            BEGIN
                CREATE TABLE Cars (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    listing_id VARCHAR(50) UNIQUE,
                    source_site NVARCHAR(50),
                    brand NVARCHAR(100),
                    model NVARCHAR(100),
                    package_trim NVARCHAR(100),
                    engine_power NVARCHAR(100),
                    year INT,
                    km INT,
                    price BIGINT,
                    location NVARCHAR(100),
                    tramer_fee BIGINT,
                    painted_parts NVARCHAR(MAX),
                    changed_parts NVARCHAR(MAX),
                    link VARCHAR(500),
                    scraped_at DATETIME,
                    is_new_listing BIT
                )
            END
            """))
            # GÖREV 2: scan_sessions (checkpoint) tablosu
            conn.execute(text("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='scan_sessions' AND xtype='U')
            BEGIN
                CREATE TABLE scan_sessions (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    session_id VARCHAR(50),
                    site_name NVARCHAR(50),
                    last_page_index INT DEFAULT 0,
                    last_listing_id VARCHAR(50),
                    started_at DATETIME DEFAULT GETDATE(),
                    last_updated_at DATETIME DEFAULT GETDATE(),
                    status NVARCHAR(20) DEFAULT 'running',
                    CONSTRAINT UQ_session_site UNIQUE (session_id, site_name)
                )
            END
            """))
        logger.info("[DB] Tablolar kontrol edildi / olusturuldu.")
    except Exception as e:
        logger.error(f"Tablo olusturma hatasi: {e}")


# ==========================================================================
#  CRUD — Cars
# ==========================================================================

def load_data(engine):
    """Cars tablosundaki tüm verileri DataFrame olarak döndürür."""
    if not engine:
        return pd.DataFrame()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT * FROM Cars ORDER BY scraped_at DESC"), conn)
            for col in ["year", "km", "price", "tramer_fee"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
            return df
    except Exception as e:
        logger.error(f"Veri okuma hatasi: {e}")
        return pd.DataFrame()


@retry_on_db_error()
def listing_exists(engine, listing_id):
    """Verilen listing_id veritabanında mevcut mu kontrol eder. DB hatası olursa otomatik retry."""
    try:
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT 1 FROM Cars WHERE listing_id=:id"),
                {"id": listing_id}
            ).scalar() is not None
    except Exception as e:
        logger.error(f"listing_exists sorgu hatasi: {e}")
        raise  # retry_on_db_error dekoratörü yakalayacak


@retry_on_db_error()
def insert_car(engine, car_data):
    """Yeni araç kaydını veritabanına ekler. DB hatası olursa otomatik retry."""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO Cars (listing_id, source_site, brand, model, package_trim,
                    engine_power, year, km, price, location, tramer_fee,
                    painted_parts, changed_parts, link, scraped_at, is_new_listing)
                VALUES (:listing_id, :source_site, :brand, :model, :package_trim,
                    :engine_power, :year, :km, :price, :location, :tramer_fee,
                    :painted_parts, :changed_parts, :link, :scraped_at, :is_new_listing)
            """), car_data)
        return True
    except Exception as e:
        logger.error(f"Arac ekleme hatasi (listing_id={car_data.get('listing_id')}): {e}")
        raise  # retry_on_db_error dekoratörü yakalayacak


def mark_all_as_seen(engine):
    """Tüm ilanları 'görüldü' (is_new_listing=0) olarak işaretler."""
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE Cars SET is_new_listing = 0"))
    except Exception as e:
        logger.error(f"mark_all_as_seen hatasi: {e}")


def clear_all(engine):
    """Cars tablosundaki tüm verileri siler."""
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM Cars"))
    except Exception as e:
        logger.error(f"clear_all hatasi: {e}")


# ==========================================================================
#  GÖREV 2: Checkpoint Fonksiyonları (scan_sessions)
# ==========================================================================

def get_or_create_session(engine, session_id: str, site_name: str) -> dict:
    """Tarama oturumu al veya yarat."""
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT last_page_index, last_listing_id, status FROM scan_sessions WHERE session_id=:sid AND site_name=:site"),
                {"sid": session_id, "site": site_name}
            ).fetchone()

            if result:
                logger.info(f"[Checkpoint] Mevcut session alindi: {site_name} sayfa={result[0]}")
                return {"page": result[0] or 0, "listing_id": result[1], "status": result[2]}

            # Yeni session oluştur
            with engine.begin() as conn_tx:
                conn_tx.execute(
                    text("INSERT INTO scan_sessions (session_id, site_name, last_page_index, status) VALUES (:sid, :site, 0, 'running')"),
                    {"sid": session_id, "site": site_name}
                )
            logger.info(f"[Checkpoint] Yeni session olusturuldu: {site_name}")
            return {"page": 0, "listing_id": None, "status": "running"}
    except Exception as e:
        logger.error(f"Checkpoint session alinamadi: {e}")
        return {"page": 0, "listing_id": None, "status": "error"}


def update_session_checkpoint(engine, session_id: str, site_name: str, page_idx: int, listing_id: str):
    """Bir sayfanın taranması bittikten sonra checkpoint güncelle."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE scan_sessions SET last_page_index=:page, last_listing_id=:lid, "
                    "last_updated_at=GETDATE() WHERE session_id=:sid AND site_name=:site"
                ),
                {"page": page_idx, "lid": listing_id, "sid": session_id, "site": site_name}
            )
    except Exception as e:
        logger.error(f"Checkpoint guncellenemedi ({site_name}, page {page_idx}): {e}")


def mark_session_complete(engine, session_id: str, site_name: str):
    """Tarama tamamlandığını işaretle."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE scan_sessions SET status='completed', last_updated_at=GETDATE() WHERE session_id=:sid AND site_name=:site"),
                {"sid": session_id, "site": site_name}
            )
        logger.info(f"[Checkpoint] {site_name} taramasi tamamlandi")
    except Exception as e:
        logger.error(f"Session completion isareti atilamadi: {e}")


def mark_session_failed(engine, session_id: str, site_name: str, reason: str):
    """Tarama başarısız olduğunu işaretle."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE scan_sessions SET status='failed', last_updated_at=GETDATE() WHERE session_id=:sid AND site_name=:site"),
                {"sid": session_id, "site": site_name}
            )
        logger.error(f"[Checkpoint] {site_name} taramasi basarisiz: {reason}")
    except Exception as e:
        logger.error(f"Session failed isareti atilamadi: {e}")
