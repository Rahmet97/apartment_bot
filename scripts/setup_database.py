"""
Скрипт для инициализации базы данных с защитой от дублирования
"""

import sqlite3
import os
import logging
from typing import List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('db_setup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def setup_database(db_path: str = "data/apartments.db") -> None:
    """Создание и настройка базы данных с защитой от дубликатов"""
    try:
        logger.info(f"Инициализация базы данных: {db_path}")

        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-10000")

            cursor.execute('''
            CREATE TABLE IF NOT EXISTS apartments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                price INTEGER NOT NULL,
                url TEXT UNIQUE NOT NULL,
                location TEXT,
                rooms INTEGER,
                area TEXT,
                source TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notified BOOLEAN DEFAULT FALSE,
            )''')

            indexes = [
                ('idx_apartments_external_id', 'apartments(external_id)'),
                ('idx_apartments_url', 'apartments(url)'),
                ('idx_apartments_price_source', 'apartments(price, source)'),
                ('idx_apartments_created_at', 'apartments(created_at)'),
                ('idx_apartments_notified', 'apartments(notified)')
            ]

            for name, columns in indexes:
                cursor.execute(f'CREATE INDEX IF NOT EXISTS {name} ON {columns}')

            cursor.execute('''
            CREATE TABLE IF NOT EXISTS monitoring_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                items_processed INTEGER DEFAULT 0,
                new_items INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                execution_time REAL,
                details TEXT
            )''')

            cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')

            default_settings: List[Tuple[str, str, str]] = [
                ('max_price', '30000', 'Максимальная цена для мониторинга'),
                ('check_interval', '300', 'Интервал проверки в секундах'),
                ('last_check_avito', '', 'Время последней проверки Avito'),
                ('last_check_cian', '', 'Время последней проверки Cian'),
                ('notifications_enabled', 'true', 'Включены ли уведомления')
            ]

            cursor.executemany('''
            INSERT OR IGNORE INTO settings (key, value, description)
            VALUES (?, ?, ?)
            ''', default_settings)

            conn.commit()
            logger.info(f"База данных успешно инициализирована: {os.path.abspath(db_path)}")

    except sqlite3.Error as e:
        logger.error(f"Ошибка SQLite: {e}")
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        raise

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Инициализация базы данных для мониторинга квартир')
    parser.add_argument('--db-path', default="data/apartments.db",
                       help='Путь к файлу базы данных (по умолчанию: data/apartments.db)')

    args = parser.parse_args()
    setup_database(args.db_path)
