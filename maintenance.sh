#!/bin/bash
# Maintenance script for Flux Gestion

set -e

echo "======================================"
echo "Maintenance Tasks for Flux Gestion"
echo "======================================"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Navigate to backend
cd backend

# Activate virtual environment
source venv/bin/activate || . venv/Scripts/activate

# Function to display menu
show_menu() {
    echo ""
    echo "Select maintenance task:"
    echo "1) Clear cache"
    echo "2) Clear database (DROP ALL TABLES)"
    echo "3) Recreate database"
    echo "4) Run migrations"
    echo "5) Create backup"
    echo "6) Restore backup"
    echo "7) Run tests"
    echo "8) Lint code"
    echo "9) Format code"
    echo "10) Update dependencies"
    echo "0) Exit"
    echo ""
}

# Function to clear cache
clear_cache() {
    echo -e "${YELLOW}[*] Clearing cache...${NC}"
    python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared successfully')"
}

# Function to reset database
reset_database() {
    read -p "Are you sure? This will delete all data. Type 'yes' to confirm: " confirm
    if [ "$confirm" = "yes" ]; then
        echo -e "${RED}[*] Resetting database...${NC}"
        python manage.py flush --no-input
        echo -e "${GREEN}[OK] Database reset${NC}"
    else
        echo "Cancelled"
    fi
}

# Function to recreate database
recreate_database() {
    echo -e "${YELLOW}[*] Recreating database...${NC}"
    rm -f db.sqlite3
    python manage.py migrate
    python manage.py loaddata fixtures/categories.json
    echo -e "${GREEN}[OK] Database recreated${NC}"
}

# Function to run migrations
run_migrations() {
    echo -e "${YELLOW}[*] Running migrations...${NC}"
    python manage.py migrate
    echo -e "${GREEN}[OK] Migrations completed${NC}"
}

# Function to backup database
backup_database() {
    BACKUP_DIR="backups"
    mkdir -p $BACKUP_DIR
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/db_backup_$TIMESTAMP.sqlite3"
    
    echo -e "${YELLOW}[*] Creating backup...${NC}"
    cp db.sqlite3 "$BACKUP_FILE"
    echo -e "${GREEN}[OK] Backup created: $BACKUP_FILE${NC}"
}

# Function to restore backup
restore_backup() {
    echo "Available backups:"
    ls -lah backups/
    read -p "Enter backup filename to restore: " backup_file
    
    if [ -f "backups/$backup_file" ]; then
        read -p "Are you sure? This will overwrite current database. Type 'yes' to confirm: " confirm
        if [ "$confirm" = "yes" ]; then
            echo -e "${YELLOW}[*] Restoring backup...${NC}"
            cp "backups/$backup_file" db.sqlite3
            echo -e "${GREEN}[OK] Backup restored${NC}"
        fi
    else
        echo -e "${RED}[!] Backup file not found${NC}"
    fi
}

# Function to run tests
run_tests() {
    echo -e "${YELLOW}[*] Running tests...${NC}"
    python manage.py test api
}

# Function to lint code
lint_code() {
    echo -e "${YELLOW}[*] Linting code...${NC}"
    if command -v flake8 &> /dev/null; then
        flake8 api/ --max-line-length=120
    else
        echo "flake8 not installed. Install with: pip install flake8"
    fi
}

# Function to format code
format_code() {
    echo -e "${YELLOW}[*] Formatting code...${NC}"
    if command -v black &> /dev/null; then
        black api/
    else
        echo "black not installed. Install with: pip install black"
    fi
}

# Function to update dependencies
update_dependencies() {
    echo -e "${YELLOW}[*] Updating dependencies...${NC}"
    pip install --upgrade -r requirements.txt
}

# Main loop
while true; do
    show_menu
    read -p "Enter your choice: " choice
    
    case $choice in
        1) clear_cache ;;
        2) reset_database ;;
        3) recreate_database ;;
        4) run_migrations ;;
        5) backup_database ;;
        6) restore_backup ;;
        7) run_tests ;;
        8) lint_code ;;
        9) format_code ;;
        10) update_dependencies ;;
        0) echo "Exiting..."; exit 0 ;;
        *) echo -e "${RED}Invalid choice${NC}" ;;
    esac
done
