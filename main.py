import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import aiohttp
from bs4 import BeautifulSoup
import sqlite3
from dataclasses import dataclass
import os
from telegram import Bot
import time
import re
import random

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('apartment_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

os.makedirs("data", exist_ok=True)


def fix_database_if_needed(db_path: str):
    """Исправление базы данных при необходимости"""
    if not os.path.exists(db_path):
        return

    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(apartments)")
        columns = {col[1]: col[2] for col in cursor.fetchall()}

        if 'notified' in columns and columns['notified'] != 'INTEGER' or 'external_id' not in columns:
            logger.info("Исправляем схему базы данных...")

            cursor.execute('''
                           CREATE TABLE apartments_new
                           (
                               id          INTEGER PRIMARY KEY AUTOINCREMENT,
                               external_id TEXT UNIQUE NOT NULL,
                               title       TEXT        NOT NULL,
                               price       INTEGER     NOT NULL,
                               url         TEXT        NOT NULL,
                               location    TEXT,
                               rooms       INTEGER,
                               area        TEXT,
                               source      TEXT        NOT NULL,
                               created_at  TEXT    DEFAULT (datetime('now')),
                               notified    INTEGER DEFAULT 0
                           )
                           ''')

            cursor.execute('''
                           INSERT
                           OR IGNORE INTO apartments_new
                           SELECT id,
                                  COALESCE(external_id, CAST(id AS TEXT)),
                                  title,
                                  price,
                                  url,
                                  location,
                                  rooms,
                                  area,
                                  source,
                                  created_at,
                                  CASE WHEN notified = 'true' OR notified = 1 THEN 1 ELSE 0 END
                           FROM apartments
                           ''')

            cursor.execute('DROP TABLE apartments')
            cursor.execute('ALTER TABLE apartments_new RENAME TO apartments')

            logger.info("Схема базы данных исправлена")

        conn.commit()
        conn.close()

    except Exception as e:
        logger.error(f"Ошибка при исправлении БД: {e}")


@dataclass
class Apartment:
    id: str
    title: str
    price: int
    url: str
    location: str
    rooms: int
    area: str
    source: str
    created_at: str


class Database:
    def __init__(self, db_path: str = "data/apartments.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        fix_database_if_needed(self.db_path)
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()

            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=1000")
            cursor.execute("PRAGMA temp_store=memory")

            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS apartments
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               external_id
                               TEXT
                               UNIQUE
                               NOT
                               NULL,
                               title
                               TEXT
                               NOT
                               NULL,
                               price
                               INTEGER
                               NOT
                               NULL,
                               url
                               TEXT
                               NOT
                               NULL,
                               location
                               TEXT,
                               rooms
                               INTEGER,
                               area
                               TEXT,
                               source
                               TEXT
                               NOT
                               NULL,
                               created_at
                               TEXT
                               DEFAULT (
                               datetime
                           (
                               'now'
                           )),
                               notified INTEGER DEFAULT 0
                               )
                           ''')

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_price ON apartments(price)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON apartments(source)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_notified ON apartments(notified)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_location ON apartments(location)')

            conn.commit()
            conn.close()
            logger.info("База данных инициализирована успешно")
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")

    def apartment_exists(self, external_id: str) -> bool:
        """Проверка существования квартиры в БД"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(self.db_path, timeout=60.0)
                conn.execute("PRAGMA busy_timeout = 30000")
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM apartments WHERE external_id = ? LIMIT 1", (str(external_id),))
                exists = cursor.fetchone() is not None
                conn.close()
                return exists
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    logger.warning(
                        f"База заблокирована при проверке существования, попытка {attempt + 1}/{max_retries}")
                    time.sleep(1)
                    continue
                else:
                    logger.error(f"Ошибка проверки существования квартиры {external_id}: {e}")
                    return True
            except Exception as e:
                logger.error(f"Ошибка проверки существования квартиры {external_id}: {e}")
                return True

        return True

    def location_exists(self, location: str) -> bool:
        """Проверка существования квартиры с такой же локацией в БД"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(self.db_path, timeout=60.0)
                conn.execute("PRAGMA busy_timeout = 30000")
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM apartments WHERE location = ? LIMIT 1", (str(location),))
                exists = cursor.fetchone() is not None
                conn.close()
                return exists
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"База заблокирована при проверке локации, попытка {attempt + 1}/{max_retries}")
                    time.sleep(1)
                    continue
                else:
                    logger.error(f"Ошибка проверки существования локации {location}: {e}")
                    return True
            except Exception as e:
                logger.error(f"Ошибка проверки существования локации {location}: {e}")
                return True

        return True

    def add_apartment(self, apartment: Apartment) -> bool:
        """Добавление новой квартиры в БД"""
        max_retries = 3

        if self.apartment_exists(apartment.id):
            logger.debug(f"Квартира {apartment.id} уже существует")
            return False

        if self.location_exists(apartment.location):
            logger.debug(f"Квартира с локацией '{apartment.location}' уже существует")
            return False

        try:
            conn = sqlite3.connect(self.db_path, timeout=60.0)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM apartments WHERE url = ? LIMIT 1", (str(apartment.url),))
            if cursor.fetchone():
                conn.close()
                logger.debug(f"Квартира с URL {apartment.url} уже существует")
                return False
            conn.close()
        except Exception as e:
            logger.error(f"Ошибка проверки дубликата по URL: {e}")
            return False

        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(self.db_path, timeout=60.0)
                conn.execute("PRAGMA busy_timeout = 30000")
                cursor = conn.cursor()

                cursor.execute('''
                               INSERT INTO apartments (external_id, title, price, url, location, rooms, area, source,
                                                       created_at, notified)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                               ''', (
                                   str(apartment.id),
                                   str(apartment.title),
                                   int(apartment.price),
                                   str(apartment.url),
                                   str(apartment.location),
                                   int(apartment.rooms),
                                   str(apartment.area),
                                   str(apartment.source),
                                   str(apartment.created_at),
                                   0
                               ))
                conn.commit()
                conn.close()
                logger.info(
                    f"Добавлена новая квартира: {apartment.title[:50]}... - {apartment.price} ₽ - {apartment.area} - {apartment.location[:30]}...")
                return True
            except sqlite3.IntegrityError as e:
                logger.debug(f"Квартира {apartment.id} уже существует (IntegrityError)")
                return False
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"База заблокирована, попытка {attempt + 1}/{max_retries}")
                    time.sleep(1)
                    continue
                else:
                    logger.error(f"Ошибка БД для квартиры {apartment.id}: {e}")
                    return False
            except Exception as e:
                logger.error(f"Ошибка добавления квартиры {apartment.id}: {e}")
                return False

        return False

    def get_new_apartments(self) -> List[Dict[str, Any]]:
        """Получение новых квартир для уведомления"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=60.0)
            conn.execute("PRAGMA busy_timeout = 30000")
            cursor = conn.cursor()
            cursor.execute('''
                           SELECT id,
                                  external_id,
                                  title,
                                  price,
                                  url,
                                  location,
                                  rooms,
                                  area,
                                  source,
                                  created_at
                           FROM apartments
                           WHERE notified = 0
                           ORDER BY created_at DESC
                           ''')
            apartments = []
            for row in cursor.fetchall():
                apartments.append({
                    'id': int(row[0]),
                    'external_id': str(row[1]),
                    'title': str(row[2]),
                    'price': int(row[3]),
                    'url': str(row[4]),
                    'location': str(row[5]),
                    'rooms': int(row[6]),
                    'area': str(row[7]),
                    'source': str(row[8]),
                    'created_at': str(row[9])
                })
            conn.close()
            return apartments
        except Exception as e:
            logger.error(f"Ошибка получения новых квартир: {e}")
            return []

    def mark_as_notified(self, apartment_id: int):
        """Отметить квартиру как уведомленную"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=60.0)
            conn.execute("PRAGMA busy_timeout = 30000")
            cursor = conn.cursor()
            cursor.execute("UPDATE apartments SET notified = 1 WHERE id = ?", (int(apartment_id),))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Ошибка отметки уведомления для {apartment_id}: {e}")


class AvitoParser:
    def __init__(self):
        self.base_url = "https://www.avito.ru"
        self.last_request_time = 0
        self.min_delay = 15

    def get_random_headers(self):
        """Получение случайных заголовков"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]

        return {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }

    async def respect_rate_limit(self):
        """Соблюдение лимитов запросов"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_delay:
            sleep_time = self.min_delay - time_since_last + random.uniform(5, 10)
            logger.info(f"Ожидание {sleep_time:.1f} секунд для соблюдения rate limit Avito...")
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()

    def extract_price(self, price_text: str) -> Optional[int]:
        """Извлечение цены из текста"""
        try:
            numbers = re.findall(r'\d+', price_text.replace(' ', ''))
            if numbers:
                price = int(''.join(numbers))
                if 0 <= price <= 200000:
                    return price
            return None
        except:
            return None

    async def parse_apartments(self, url: str, max_price: int = 30000) -> List[Apartment]:
        """Парсинг квартир с Avito"""
        apartments = []

        try:
            logger.info(f"Начинаем парсинг Avito: {url}")

            await self.respect_rate_limit()

            headers = self.get_random_headers()
            timeout = aiohttp.ClientTimeout(total=60)

            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                try:
                    async with session.get(url) as response:
                        if response.status == 429:
                            logger.warning("Получен код 429 от Avito. Пропускаем этот цикл...")
                            return apartments
                        elif response.status == 403:
                            logger.warning("Получен код 403 от Avito. Доступ заблокирован...")
                            return apartments
                        elif response.status != 200:
                            logger.error(f"Ошибка HTTP при запросе к Avito: {response.status}")
                            return apartments

                        html = await response.text()
                        logger.info(f"Получен HTML размером {len(html)} символов")

                except Exception as e:
                    logger.error(f"Ошибка при запросе к Avito: {e}")
                    return apartments

                soup = BeautifulSoup(html, 'html.parser')

                selectors = [
                    '[data-marker="item"]',
                    '.items-item',
                    '.iva-item-root'
                ]

                items = []
                for selector in selectors:
                    items = soup.select(selector)
                    if items:
                        logger.info(f"Найдено {len(items)} элементов с селектором: {selector}")
                        break

                if not items:
                    logger.warning("Не найдено объявлений с известными селекторами на Avito")
                    return apartments

                for i, item in enumerate(items[:10]):
                    try:
                        title_elem = item.select_one('[data-marker="item-title"]')
                        if not title_elem:
                            title_elem = item.select_one('h3 a')
                        if not title_elem:
                            title_elem = item.select_one('a[href*="/kvartiry/"]')

                        if not title_elem:
                            continue

                        title = title_elem.get_text(strip=True)
                        link_url = title_elem.get('href', '')

                        if not title or not link_url:
                            continue

                        price_elem = item.select_one('[data-marker="item-price"]')
                        if not price_elem:
                            price_elem = item.select_one('.price-text')

                        if not price_elem:
                            continue

                        price_text = price_elem.get_text(strip=True)
                        price = self.extract_price(price_text)

                        if price is None or price > max_price:
                            continue

                        if link_url.startswith('/'):
                            full_url = self.base_url + link_url
                        else:
                            full_url = link_url

                        apartment_id = f"avito_{abs(hash(full_url)) % 1000000}"

                        location = "Не указано"

                        location_selectors = [
                            '[data-marker="item-address"]',
                            '.item-address-georeferences-item__content',
                            '.style-item-address-georeferences-item-TZsrp',
                            '.geo-georeferences-item__content',
                            '.item-address'
                        ]

                        location_parts = []

                        for selector in location_selectors:
                            location_elem = item.select_one(selector)
                            if location_elem:
                                location_text = location_elem.get_text(strip=True)
                                if location_text and len(location_text) > 5:
                                    location_parts.append(location_text)

                        if not location_parts:
                            all_text = item.get_text()
                            address_patterns = [
                                r'Новосибирская\s+обл\.?,\s*Новосибирск,\s*[^,\n]+(?:,\s*\d+[^,\n]*)?',
                                r'Новосибирск,\s*[^,\n]+(?:,\s*\d+[^,\n]*)?',
                                r'г\.\s*Новосибирск,\s*[^,\n]+(?:,\s*\d+[^,\n]*)?',
                                r'ул\.\s*[А-Яа-я\s\-]+(?:,\s*\d+[^,\n]*)?',
                                r'пр\.\s*[А-Яа-я\s\-]+(?:,\s*\d+[^,\n]*)?',
                                r'пер\.\s*[А-Яа-я\s\-]+(?:,\s*\d+[^,\n]*)?',
                                r'б-р\s*[А-Яа-я\s\-]+(?:,\s*\d+[^,\n]*)?'
                            ]

                            for pattern in address_patterns:
                                matches = re.findall(pattern, all_text)
                                if matches:
                                    location_parts.extend(matches[:2])
                                    break

                        if location_parts:
                            location = max(location_parts, key=len)
                            location = re.sub(r'\s+', ' ', location).strip()
                            if len(location) > 100:
                                location = location[:97] + "..."
                        else:
                            location = "Новосибирск"

                        area = "Не указано"

                        area_selectors = [
                            '[data-marker="item-specific-params"]',
                            '.item-params',
                            '.params-paramsList',
                            '.iva-item-text'
                        ]

                        for selector in area_selectors:
                            area_elem = item.select_one(selector)
                            if area_elem:
                                area_text = area_elem.get_text(strip=True)
                                area_patterns = [
                                    r'(\d+(?:[.,]\d+)?)\s*м²',
                                    r'(\d+(?:[.,]\d+)?)\s*кв\.?\s*м',
                                    r'S:\s*(\d+(?:[.,]\d+)?)',
                                    r'площадь[:\s]*(\d+(?:[.,]\d+)?)'
                                ]

                                for pattern in area_patterns:
                                    area_match = re.search(pattern, area_text, re.IGNORECASE)
                                    if area_match:
                                        area = f"{area_match.group(1)} м²"
                                        break

                                if area != "Не указано":
                                    break

                        if area == "Не указано":
                            item_text = item.get_text()
                            area_patterns = [
                                r'(\d+(?:[.,]\d+)?)\s*м²',
                                r'(\d+(?:[.,]\d+)?)\s*кв\.?\s*м',
                                r'S:\s*(\d+(?:[.,]\d+)?)',
                                r'площадь[:\s]*(\d+(?:[.,]\d+)?)'
                            ]

                            for pattern in area_patterns:
                                area_matches = re.findall(pattern, item_text, re.IGNORECASE)
                                if area_matches:
                                    for match in area_matches:
                                        try:
                                            area_value = float(match.replace(',', '.'))
                                            if 10 <= area_value <= 500:
                                                area = f"{match} м²"
                                                break
                                        except:
                                            continue
                                    if area != "Не указано":
                                        break

                        rooms = 1
                        room_patterns = [
                            r'(\d+)-комн',
                            r'(\d+)\s*комн',
                            r'(\d+)-к',
                            r'(\d+)к'
                        ]

                        title_and_text = f"{title} {item.get_text()}"
                        for pattern in room_patterns:
                            room_match = re.search(pattern, title_and_text, re.IGNORECASE)
                            if room_match:
                                try:
                                    rooms = int(room_match.group(1))
                                    if 1 <= rooms <= 10:
                                        break
                                except:
                                    continue

                        apartment = Apartment(
                            id=apartment_id,
                            title=title[:200],
                            price=price,
                            url=full_url,
                            location=location[:100],
                            rooms=rooms,
                            area=area[:50],
                            source="Avito",
                            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        )

                        apartments.append(apartment)
                        logger.info(f"Найдена квартира: {title[:50]}... - {price} ₽")

                    except Exception as e:
                        logger.error(f"Ошибка при обработке элемента Avito {i + 1}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Ошибка при парсинге Avito: {e}")

        logger.info(f"Avito: найдено {len(apartments)} подходящих квартир")
        return apartments


class CianParser:
    def __init__(self):
        self.base_url = "https://novosibirsk.cian.ru"
        self.last_request_time = 0
        self.min_delay = 5

    def get_random_headers(self):
        """Получение случайных заголовков"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]

        return {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Connection': 'keep-alive',
        }

    async def respect_rate_limit(self):
        """Соблюдение лимитов запросов"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_delay:
            sleep_time = self.min_delay - time_since_last + random.uniform(1, 3)
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()

    def extract_price(self, price_text: str) -> Optional[int]:
        """Извлечение цены из текста"""
        try:
            numbers = re.findall(r'\d+', price_text.replace(' ', ''))
            if numbers:
                price = int(''.join(numbers))
                if 0 <= price <= 200000:
                    return price
            return None
        except:
            return None

    async def parse_apartments(self, url: str, max_price: int = 30000) -> List[Apartment]:
        """Парсинг квартир с Cian"""
        apartments = []

        try:
            logger.info(f"Начинаем парсинг Cian: {url}")

            await self.respect_rate_limit()

            headers = self.get_random_headers()
            timeout = aiohttp.ClientTimeout(total=45)

            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка HTTP при запросе к Cian: {response.status}")
                        return apartments

                    html = await response.text()
                    logger.info(f"Получен HTML размером {len(html)} символов")

                    soup = BeautifulSoup(html, 'html.parser')

                    items = soup.select('[data-name="CardComponent"]')

                    if not items:
                        logger.warning("Не найдено объявлений на Cian")
                        return apartments

                    logger.info(f"Найдено {len(items)} элементов на Cian")

                    for i, item in enumerate(items[:15]):
                        try:
                            title_elem = item.select_one('[data-mark="OfferTitle"]')
                            if not title_elem:
                                title_elem = item.select_one('a[href*="/rent/flat/"]')

                            if not title_elem:
                                continue

                            title = title_elem.get_text(strip=True)

                            link_elem = item.find('a', href=lambda x: x and '/rent/flat/' in x)
                            if not link_elem:
                                continue

                            link_url = link_elem.get('href', '')

                            price_elem = item.select_one('[data-mark="MainPrice"]')
                            if not price_elem:
                                continue

                            price_text = price_elem.get_text(strip=True)
                            price = self.extract_price(price_text)

                            if price is None or price > max_price:
                                continue

                            if link_url.startswith('/'):
                                full_url = self.base_url + link_url
                            else:
                                full_url = link_url

                            apartment_id = f"cian_{abs(hash(full_url)) % 1000000}"

                            location_parts = []

                            address_selectors = [
                                '[data-name="GeoLabel"]',
                                '[data-mark="GeoLabel"]',
                                '.a10a3f92e9--address--SMU25',
                                '.a10a3f92e9--geo--RNXJ5',
                                '[data-name="AddressContainer"]'
                            ]

                            for selector in address_selectors:
                                location_elems = item.select(selector)
                                for location_elem in location_elems:
                                    location_text = location_elem.get_text(strip=True)
                                    if location_text and len(location_text) > 5:
                                        location_parts.append(location_text)

                            if not location_parts:
                                item_text = item.get_text()
                                address_patterns = [
                                    r'Новосибирская\s+область,\s*Новосибирск,\s*[^,\n]+(?:,\s*метро\s*[^,\n]+\s*\d+\s*м)?',
                                    r'Новосибирск,\s*[^,\n]+(?:,\s*метро\s*[^,\n]+)?',
                                    r'г\.\s*Новосибирск,\s*[^,\n]+(?:,\s*метро\s*[^,\n]+)?',
                                    r'ул\.\s*[А-Яа-я\s\-]+(?:,\s*\d+[^,\n]*)?(?:,\s*метро\s*[^,\n]+)?',
                                    r'пр\.\s*[А-Яа-я\s\-]+(?:,\s*\d+[^,\n]*)?(?:,\s*метро\s*[^,\n]+)?'
                                ]

                                for pattern in address_patterns:
                                    matches = re.findall(pattern, item_text)
                                    if matches:
                                        location_parts.extend(matches[:2])
                                        break

                            if location_parts:
                                full_location = ", ".join(set(location_parts))
                                location = full_location[:100] if len(full_location) <= 100 else full_location[
                                                                                                 :97] + "..."
                            else:
                                location = "Новосибирск"

                            area = "Не указано"

                            area_elem = item.select_one('[data-mark="OfferSummary"]')
                            if area_elem:
                                area_text = area_elem.get_text(strip=True)
                                area_match = re.search(r'(\d+(?:,\d+)?)\s*м²', area_text)
                                if area_match:
                                    area = f"{area_match.group(1)} м²"

                            if area == "Не указано":
                                area_selectors = [
                                    '[data-mark*="Area"]',
                                    '.a10a3f92e9--area--3xKvp',
                                    '[title*="м²"]',
                                    '[data-testid*="area"]'
                                ]

                                for selector in area_selectors:
                                    area_elem = item.select_one(selector)
                                    if area_elem:
                                        area_text = area_elem.get_text(strip=True)
                                        area_match = re.search(r'(\d+(?:,\d+)?)\s*м²', area_text)
                                        if area_match:
                                            area = f"{area_match.group(1)} м²"
                                            break

                            if area == "Не указано":
                                item_text = item.get_text()
                                area_matches = re.findall(r'(\d+(?:,\d+)?)\s*м²', item_text)
                                if area_matches:
                                    area = f"{area_matches[0]} м²"

                            rooms = 1
                            room_patterns = [
                                r'(\d+)-комн',
                                r'(\d+)\s*комн',
                                r'(\d+)-к',
                                r'(\d+)к'
                            ]

                            title_and_text = f"{title} {item.get_text()}"
                            for pattern in room_patterns:
                                room_match = re.search(pattern, title_and_text, re.IGNORECASE)
                                if room_match:
                                    try:
                                        rooms = int(room_match.group(1))
                                        if 1 <= rooms <= 10:
                                            break
                                    except:
                                        continue

                            apartment = Apartment(
                                id=apartment_id,
                                title=title[:200],
                                price=price,
                                url=full_url,
                                location=location[:100],
                                rooms=rooms,
                                area=area[:50],
                                source="Cian",
                                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            )

                            apartments.append(apartment)
                            logger.info(f"Найдена квартира: {title[:50]}... - {price} ₽")

                        except Exception as e:
                            logger.error(f"Ошибка при обработке элемента Cian {i + 1}: {e}")
                            continue

        except Exception as e:
            logger.error(f"Ошибка при парсинге Cian: {e}")

        logger.info(f"Cian: найдено {len(apartments)} подходящих квартир")
        return apartments


class TelegramNotifier:
    def __init__(self, bot_token: str, channel_id: str):
        self.bot = Bot(token=bot_token)
        self.channel_id = channel_id

    async def send_apartment_notification(self, apartment: Dict[str, Any]):
        """Отправка уведомления о новой квартире"""
        try:
            message = f"""
🏠 *Новая квартира найдена!*

📍 *Локация:* {apartment['location']}
💰 *Цена:* {apartment['price']:,} ₽/мес
🏠 *Комнат:* {apartment['rooms']}
📐 *Площадь:* {apartment['area']}
🌐 *Источник:* {apartment['source']}

*{apartment['title']}*

🔗 [Посмотреть объявление]({apartment['url']})

⏰ Найдено: {apartment['created_at']}
            """.strip()

            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )

            logger.info(f"Уведомление отправлено для квартиры {apartment['id']}")

        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления: {e}")


class ApartmentMonitor:
    def __init__(self):
        self.db = Database()
        self.avito_parser = AvitoParser()
        self.cian_parser = CianParser()

        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        channel_id = os.getenv('TELEGRAM_CHANNEL_ID')

        if bot_token and channel_id:
            self.notifier = TelegramNotifier(bot_token, channel_id)
        else:
            self.notifier = None
            logger.warning("Telegram настройки не найдены. Уведомления отключены.")

        fix_database_if_needed(self.db.db_path)

    async def monitor_apartments(self):
        """Основной цикл мониторинга"""
        urls = [
            "https://www.avito.ru/novosibirsk/kvartiry/sdam/na_dlitelnyy_srok/3-komnatnye-ASgBAgICA0SSA8gQ8AeQUswIklk",
            "https://novosibirsk.cian.ru/cat.php?deal_type=rent&engine_version=2&foot_min=15&metro%5B0%5D=248&metro%5B1%5D=249&metro%5B2%5D=250&metro%5B3%5D=251&metro%5B4%5D=252&metro%5B5%5D=257&metro%5B6%5D=258&offer_type=flat&only_foot=2&room3=1&sort=price_object_order&type=4"
        ]

        while True:
            try:
                logger.info("=" * 50)
                logger.info("Начинаем новый цикл мониторинга квартир...")

                all_apartments = []

                try:
                    cian_apartments = await self.cian_parser.parse_apartments(urls[1])
                    all_apartments.extend(cian_apartments)
                    logger.info(f"Cian: найдено {len(cian_apartments)} квартир")
                except Exception as e:
                    logger.error(f"Ошибка парсинга Cian: {e}")

                await asyncio.sleep(15)

                try:
                    avito_apartments = await self.avito_parser.parse_apartments(urls[0])
                    all_apartments.extend(avito_apartments)
                    logger.info(f"Avito: найдено {len(avito_apartments)} квартир")
                except Exception as e:
                    logger.error(f"Ошибка парсинга Avito: {e}")

                logger.info(f"Всего найдено квартир: {len(all_apartments)}")

                new_apartments_count = 0
                for apartment in all_apartments:
                    try:
                        if self.db.add_apartment(apartment):
                            new_apartments_count += 1
                    except Exception as e:
                        logger.error(f"Ошибка добавления квартиры в БД: {e}")

                logger.info(f"Добавлено {new_apartments_count} новых квартир в БД")

                if self.notifier and new_apartments_count > 0:
                    try:
                        await self.send_notifications()
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомлений: {e}")

                logger.info("Ожидание 5 минут до следующей проверки...")
                await asyncio.sleep(300)

            except Exception as e:
                logger.error(f"Критическая ошибка в цикле мониторинга: {e}")
                logger.info("Ожидание 2 минуты перед повторной попыткой...")
                await asyncio.sleep(120)

    async def send_notifications(self):
        """Отправка уведомлений о новых квартирах"""
        try:
            new_apartments = self.db.get_new_apartments()
            logger.info(f"Найдено {len(new_apartments)} новых квартир для уведомления")

            for apartment in new_apartments:
                try:
                    await self.notifier.send_apartment_notification(apartment)
                    self.db.mark_as_notified(apartment['id'])

                    await asyncio.sleep(3)
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления для квартиры {apartment['id']}: {e}")
        except Exception as e:
            logger.error(f"Ошибка в процессе отправки уведомлений: {e}")


async def main():
    logger.info("Запуск системы мониторинга квартир...")
    monitor = ApartmentMonitor()
    await monitor.monitor_apartments()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки. Завершение работы...")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
