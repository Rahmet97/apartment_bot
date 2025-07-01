import asyncio
import logging
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
import os
import sqlite3
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ApartmentBot:
    def __init__(self, token: str):
        self.token = token
        self.db_path = "data/apartments.db"
        self.application = Application.builder().token(token).build()
        self.setup_handlers()

    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("recent", self.recent_command))
        self.application.add_handler(CommandHandler("cheap", self.cheap_command))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        welcome_message = """
🏠 *Добро пожаловать в бот мониторинга квартир!*

Я помогу вам отслеживать новые предложения аренды квартир в Новосибирске дешевле 30,000 ₽.

*Доступные команды:*
/help - Показать это сообщение
/stats - Статистика по найденным квартирам
/recent - Последние найденные квартиры
/cheap - Самые дешевые квартиры

Бот автоматически мониторит Avito и Cian каждые 10 минут.
        """.strip()

        await update.message.reply_text(welcome_message, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_message = """
🤖 *Помощь по боту мониторинга квартир*

*Команды:*
/start - Приветствие и основная информация
/stats - Показать статистику найденных квартир
/recent - Показать последние 5 найденных квартир
/cheap - Показать 5 самых дешевых квартир

*Как работает бот:*
• Каждые 10 минут сканирует Avito и Cian
• Ищет 3-комнатные квартиры дешевле 30,000 ₽
• Автоматически отправляет уведомления о новых находках
• Сохраняет все данные в базу данных

*Источники:*
• Avito.ru
• Cian.ru

Если у вас есть вопросы, обратитесь к администратору.
        """.strip()

        await update.message.reply_text(help_message, parse_mode='Markdown')

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stats"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM apartments")
            total_count = cursor.fetchone()[0]

            cursor.execute("SELECT source, COUNT(*) FROM apartments GROUP BY source")
            source_stats = cursor.fetchall()

            cursor.execute("SELECT AVG(price) FROM apartments")
            avg_price = cursor.fetchone()[0] or 0

            cursor.execute("SELECT MIN(price) FROM apartments")
            min_price = cursor.fetchone()[0] or 0

            cursor.execute("""
                           SELECT COUNT(*)
                           FROM apartments
                           WHERE created_at >= datetime('now', '-1 day')
                           """)
            last_24h = cursor.fetchone()[0]

            conn.close()

            stats_message = f"""
📊 *Статистика мониторинга квартир*

📈 *Общая статистика:*
• Всего найдено: {total_count} квартир
• За последние 24 часа: {last_24h} квартир
• Средняя цена: {avg_price:,.0f} ₽
• Минимальная цена: {min_price:,.0f} ₽

📋 *По источникам:*
            """.strip()

            for source, count in source_stats:
                stats_message += f"\n• {source}: {count} квартир"

            await update.message.reply_text(stats_message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            await update.message.reply_text("❌ Ошибка при получении статистики")

    async def recent_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /recent"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT title, price, location, source, url, created_at
                           FROM apartments
                           ORDER BY id DESC LIMIT 5
                           """)

            apartments = cursor.fetchall()
            conn.close()

            if not apartments:
                await update.message.reply_text("🔍 Пока не найдено ни одной квартиры")
                return

            message = "🕐 *Последние найденные квартиры:*\n\n"

            for i, (title, price, location, source, url, created_at) in enumerate(apartments, 1):
                message += f"""
{i}. *{title[:50]}{'...' if len(title) > 50 else ''}*
💰 {price:,} ₽ | 📍 {location}
🌐 {source} | ⏰ {created_at}
🔗 [Посмотреть]({url})

                """.strip() + "\n\n"

            await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)

        except Exception as e:
            logger.error(f"Ошибка при получении последних квартир: {e}")
            await update.message.reply_text("❌ Ошибка при получении данных")

    async def cheap_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /cheap"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT title, price, location, source, url, created_at
                           FROM apartments
                           ORDER BY price ASC LIMIT 5
                           """)

            apartments = cursor.fetchall()
            conn.close()

            if not apartments:
                await update.message.reply_text("🔍 Пока не найдено ни одной квартиры")
                return

            message = "💰 *Самые дешевые квартиры:*\n\n"

            for i, (title, price, location, source, url, created_at) in enumerate(apartments, 1):
                message += f"""
{i}. *{title[:50]}{'...' if len(title) > 50 else ''}*
💰 {price:,} ₽ | 📍 {location}
🌐 {source} | ⏰ {created_at}
🔗 [Посмотреть]({url})

                """.strip() + "\n\n"

            await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)

        except Exception as e:
            logger.error(f"Ошибка при получении дешевых квартир: {e}")
            await update.message.reply_text("❌ Ошибка при получении данных")

    async def run(self):
        """Запуск бота"""
        logger.info("Запуск Telegram бота...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Остановка бота...")
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()


async def main():
    """Главная функция"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')

    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN не установлен")
        return

    bot = ApartmentBot(bot_token)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
