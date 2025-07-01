.PHONY: help install run test clean docker-build docker-run setup debug test-parsers check-db clean-db logs full-debug

help:
	@echo "Доступные команды:"
	@echo "  install     - Установка зависимостей"
	@echo "  setup       - Настройка базы данных"
	@echo "  run         - Запуск мониторинга"
	@echo "  run-bot     - Запуск Telegram бота"
	@echo "  test        - Запуск тестов"
	@echo "  clean       - Очистка временных файлов"
	@echo "  docker-build - Сборка Docker образа"
	@echo "  docker-run  - Запуск в Docker"
	@echo "  debug       - Запуск с��рипта отладки парсеров"
	@echo "  test-parsers- Запуск тестов парсеров"
	@echo "  check-db    - Проверка базы данных"
	@echo "  clean-db    - Очистка базы данных"
	@echo "  logs        - Просмотр логов"
	@echo "  full-debug  - Полная отладка"

install:
	pip install -r requirements.txt

setup:
	python scripts/setup_database.py --db-path data/apartments.db
	@echo "Не забудьте создать .env файл с настройками Telegram!"

run:
	python main.py

run-bot:
	python bot.py

test:
	pytest tests/ -v

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache/
	rm -rf *.egg-info/

docker-build:
	docker build -t apartment-monitor .

docker-run:
	docker-compose up -d

docker-stop:
	docker-compose down

docker-logs:
	docker-compose logs -f

dev-install:
	pip install -r requirements.txt
	pip install pytest pytest-asyncio flake8 black

lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	black --check .

format:
	black .

prod-deploy:
	docker-compose -f docker-compose.prod.yml up -d

prod-logs:
	docker-compose -f docker-compose.prod.yml logs -f

backup-db:
	cp data/apartments.db backups/apartments_$(shell date +%Y%m%d_%H%M%S).db

debug:
	python debug_parsers.py

test-parsers:
	python scripts/setup_database.py --test-parsers

check-db:
	sqlite3 data/apartments.db "SELECT COUNT(*) as total_apartments FROM apartments;"
	sqlite3 data/apartments.db "SELECT source, COUNT(*) as count FROM apartments GROUP BY source;"
	sqlite3 data/apartments.db "SELECT * FROM apartments ORDER BY created_at DESC LIMIT 5;"

clean-db:
	rm -f data/apartments.db test_apartments.db

logs:
	tail -f apartment_monitor.log

full-debug: clean-db setup debug check-db
