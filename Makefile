.PHONY: install start stop restart update help

# Default: install + start
all: install

install:
	@bash install.sh

start:
	@bash start.sh

stop:
	@bash stop.sh

restart: stop
	@sleep 1
	@bash start.sh

update:
	@git pull origin main
	@bash stop.sh 2>/dev/null || true
	@sleep 1
	@bash start.sh
	@echo "✅ Updated & restarted"

help:
	@echo "Torrent Bot Commands:"
	@echo "  make          → install semua & start"
	@echo "  make start    → start bot"
	@echo "  make stop     → stop bot"
	@echo "  make restart  → restart bot"
	@echo "  make update   → pull update terbaru & restart"
