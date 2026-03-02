#!/bin/bash
# ═══════════════════════════════════════════════════
# PRSTA AI Bot — Initial Server Setup
# Run ONCE on a fresh server to install everything
#
# Quick install (copy-paste on server):
#   bash <(curl -fsSL https://raw.githubusercontent.com/andrchq/prsta_ai/main/setup.sh)
#
# Or manually:
#   git clone https://github.com/andrchq/prsta_ai.git
#   cd prsta_ai && bash setup.sh
# ═══════════════════════════════════════════════════

set -e

GIT_REPO="https://github.com/andrchq/prsta_ai.git"
INSTALL_DIR="/opt/prsta_ai"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo -e "${BOLD}${BLUE}  🤖 PRSTA AI Bot — Server Setup${NC}"
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo ""

# ─── 1. Install Docker if not present ────────────

if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}📦 Установка Docker...${NC}"
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo -e "${GREEN}✅ Docker установлен${NC}"
else
    echo -e "${GREEN}✅ Docker уже установлен: $(docker --version)${NC}"
fi

# ─── 2. Install Docker Compose plugin ────────────

if ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}📦 Установка Docker Compose плагина...${NC}"
    apt-get update -qq
    apt-get install -y -qq docker-compose-plugin
    echo -e "${GREEN}✅ Docker Compose установлен${NC}"
else
    echo -e "${GREEN}✅ Docker Compose уже установлен: $(docker compose version)${NC}"
fi

# ─── 3. Clone or detect project directory ────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# If docker-compose.yml exists here, we're already inside the project
if [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    PROJECT_DIR="$SCRIPT_DIR"
elif [ -d "$INSTALL_DIR" ]; then
    echo -e "${GREEN}✅ Проект уже существует в $INSTALL_DIR${NC}"
    PROJECT_DIR="$INSTALL_DIR"
    cd "$PROJECT_DIR"
    git pull
else
    echo -e "${YELLOW}📥 Клонирование репозитория...${NC}"
    git clone "$GIT_REPO" "$INSTALL_DIR"
    PROJECT_DIR="$INSTALL_DIR"
fi

cd "$PROJECT_DIR"
echo -e "${BLUE}📂 Рабочая директория: $PROJECT_DIR${NC}"

# ─── 4. Create .env from template ────────────────

if [ ! -f ".env" ]; then
    echo ""
    echo -e "${YELLOW}⚙️  Создание .env файла...${NC}"
    cp .env.example .env

    # Prompt for essential values
    echo ""
    read -p "🔑 Введи BOT_TOKEN: " bot_token
    sed -i "s|BOT_TOKEN=.*|BOT_TOKEN=$bot_token|" .env

    read -p "🔑 Введи OPENROUTER_API_KEY: " openrouter_key
    sed -i "s|OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=$openrouter_key|" .env

    read -p "👤 Введи свой Telegram ID (для админки): " admin_id
    sed -i "s|ADMIN_IDS=.*|ADMIN_IDS=$admin_id|" .env

    echo -e "${GREEN}✅ .env файл создан${NC}"
else
    echo -e "${GREEN}✅ .env файл уже существует${NC}"
fi

# ─── 5. Setup bai CLI command ────────────────────

BAI_SCRIPT="$PROJECT_DIR/bai"
BAI_LINK="/usr/local/bin/bai"

if [ -f "$BAI_SCRIPT" ]; then
    chmod +x "$BAI_SCRIPT"

    # Create symlink for global access
    if [ -L "$BAI_LINK" ] || [ -f "$BAI_LINK" ]; then
        rm -f "$BAI_LINK"
    fi
    ln -s "$BAI_SCRIPT" "$BAI_LINK"

    echo -e "${GREEN}✅ Команда 'bai' установлена глобально${NC}"
else
    echo -e "${RED}❌ Скрипт bai не найден в $PROJECT_DIR${NC}"
fi

# ─── 6. Create backups directory ─────────────────

mkdir -p "$PROJECT_DIR/backups"

# ─── 7. Build and start ─────────────────────────

echo ""
echo -e "${YELLOW}🔨 Сборка и запуск контейнеров...${NC}"
docker compose build
docker compose up -d

echo ""
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅ Установка завершена!${NC}"
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo ""
echo -e "Доступные команды:"
echo -e "  ${GREEN}bai status${NC}    — статус сервисов"
echo -e "  ${GREEN}bai logs${NC}      — логи бота"
echo -e "  ${GREEN}bai update${NC}    — обновить бота"
echo -e "  ${GREEN}bai help${NC}      — все команды"
echo ""

# Show status
docker compose ps
