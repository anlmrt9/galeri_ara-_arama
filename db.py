"""
db.py - SQL Server Veritabanı Erişim Katmanı
===============================================
Engine oluşturma, tablo başlatma, veri okuma/yazma/silme.
Tüm connection'lar context manager ile yönetilir, leak riski yok.
"""

import pyodbc
import pandas as pd
from sqlalchemy import create_engine, text
from config import DB_SERVER, DB_NAME, DB_POOL_SIZE, DB_MAX_OVERFLOW
from logger_setup import logger


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
        # BUG FIX: Sessiz except:pass kaldırıldı — DB oluşturulamazsa kullanıcı görsün
        logger.error(f"Veritabani olusturma hatasi: {e}")


def get_engine():
    """SQLAlchemy engine döndürür. pool_pre_ping uzun süreli bağlantı kopmasını önler."""
    create_db_if_not_exists()
    conn_str = (
        f"mssql+pyodbc://@{DB_SERVER}/{DB_NAME}"
        f"?driver=ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes"
    )
    try:
        return create_engine(
            conn_str,
            pool_size=DB_POOL_SIZE,
            max_overflow=DB_MAX_OVERFLOW,
            # pool_pre_ping: her bağlantı kullanılmadan önce canlı mı diye kontrol eder,
            # saatlerce çalışan arka plan taramasında "broken pipe" hatasını önler.
            pool_pre_ping=True,
            # pool_recycle: 30 dakikada bir bağlantıları yeniler (SQL Server idle timeout'u aşmamak için)
            pool_recycle=1800,
        )
    except Exception as e:
        logger.error(f"Engine olusturulamadi: {e}")
        return None


def init_tables(engine):
    """Cars tablosu yoksa oluşturur."""
    if not engine:
        return
    try:
        with engine.begin() as conn:
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
    except Exception as e:
        # BUG FIX: Sessiz except:pass kaldırıldı
        logger.error(f"Tablo olusturma hatasi: {e}")


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


def listing_exists(engine, listing_id):
    """Verilen listing_id veritabanında mevcut mu kontrol eder."""
    try:
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT 1 FROM Cars WHERE listing_id=:id"),
                {"id": listing_id}
            ).scalar() is not None
    except Exception as e:
        logger.error(f"listing_exists sorgu hatasi: {e}")
        return False


def insert_car(engine, car_data):
    """Yeni araç kaydını veritabanına ekler."""
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
        return False


def mark_all_as_seen(engine):
    """Tüm ilanları 'görüldü' (is_new_listing=0) olarak işaretler."""
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE Cars SET is_new_listing = 0"))
    except Exception as e:
        # BUG FIX: Sessiz except:pass kaldırıldı
        logger.error(f"mark_all_as_seen hatasi: {e}")


def clear_all(engine):
    """Cars tablosundaki tüm verileri siler."""
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM Cars"))
    except Exception as e:
        logger.error(f"clear_all hatasi: {e}")
