import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    telegram_bot_token: Optional[str] = None
    telegram_channel_id: Optional[str] = None
    
    database_path: str = "data/apartments.db"
    
    check_interval: int = 300
    max_price: int = 30000
    
    request_timeout: int = 30
    retry_attempts: int = 3
    retry_delay: int = 5
    
    avito_url: str = "https://www.avito.ru/novosibirsk/kvartiry/sdam/na_dlitelnyy_srok/3-komnatnye-ASgBAgICA0SSA8gQ8AeQUswIklk?context=H4sIAAAAAAAA_wEjANz_YToxOntzOjg6ImZyb21QYWdlIjtzOjc6ImNhdGFsb2ciO312FITcIwAAAA&f=ASgBAgICBESSA8gQ8AeQUswIklmwsxT~oY8D&footWalkingMetro=20&metro=2017-2018-2019-2020-2025-2026-2027-2028"
    cian_url: str = "https://novosibirsk.cian.ru/cat.php?deal_type=rent&engine_version=2&foot_min=15&metro%5B0%5D=248&metro%5B1%5D=249&metro%5B2%5D=250&metro%5B3%5D=251&metro%5B4%5D=252&metro%5B5%5D=257&metro%5B6%5D=258&offer_type=flat&only_foot=2&room3=1&sort=price_object_order&type=4"
    
    def __post_init__(self):
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', self.telegram_bot_token)
        self.telegram_channel_id = os.getenv('TELEGRAM_CHANNEL_ID', self.telegram_channel_id)
        self.database_path = os.getenv('DATABASE_PATH', self.database_path)
        self.max_price = int(os.getenv('MAX_PRICE', str(self.max_price)))
        self.check_interval = int(os.getenv('CHECK_INTERVAL', str(self.check_interval)))

config = Config()
