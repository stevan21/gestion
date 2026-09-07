.PHONY: help install migrate test test-coverage lint format run-server run-frontend         deploy clean docker-build docker-up docker-down docker-logs backup restore         shell admin fixtures seed worker beat makemigrations showmigrations         collectstatic check requirements docs version

help:
	@echo "Flux Gestion - Available Commands"
	@echo "=================================="
	@echo "make install          - Install dependencies"
	@echo "make migrate          - Run database migrations"
	@echo "make test             - Run tests"
	@echo "make lint             - Lint code"
	@echo "make format           - Format code"
	@echo "make run-server       - Start Django development server"
	@echo "make run-frontend     - Start frontend development server"
	@echo "make run              - Start both frontend and backend"
	@echo "make deploy           - Deploy with Docker Compose"
	@echo "make clean            - Clean up temporary files"
	@echo "make docker-build     - Build Docker images"
	@echo "make docker-up        - Start Docker containers"
	@echo "make docker-down      - Stop Docker containers"
	@echo "make backup           - Create database backup"
	@echo "make restore          - Restore from backup"
	@echo "make shell            - Django shell"
	@echo "make admin            - Create superuser"
	@echo "make fixtures         - Load fixture data"
	@echo "make seed             - Generate a demonstration dataset"
	@echo "make worker           - Start a Celery worker"
	@echo "make beat             - Start the Celery scheduler"

install:
	@echo "Installing dependencies..."
	cd backend && \
	python -m venv venv && \
	. venv/bin/activate && \
	pip install -r requirements.txt

migrate:
	@echo "Running migrations..."
	cd backend && \
	. venv/bin/activate && \
	python manage.py migrate

test:
	@echo "Running tests..."
	cd backend && \
	. venv/bin/activate && \
	python manage.py test api

test-coverage:
	@echo "Running tests with coverage..."
	cd backend && \
	. venv/bin/activate && \
	coverage run --source='.' manage.py test api && \
	coverage report && \
	coverage html

lint:
	@echo "Linting code..."
	cd backend && \
	. venv/bin/activate && \
	flake8 api/ --max-line-length=120

format:
	@echo "Formatting code..."
	cd backend && \
	. venv/bin/activate && \
	black .

run-server:
	@echo "Starting Django development server..."
	cd backend && \
	. venv/bin/activate && \
	python manage.py runserver

run-frontend:
	@echo "Starting frontend development server..."
	cd frontend && \
	python -m http.server 8001

# run-server est bloquant : lancez le frontend dans un autre terminal.
run:
	@echo "Lancez 'make run-server' et 'make run-frontend' dans deux terminaux."
	@echo "Backend  : http://127.0.0.1:8000"
	@echo "Frontend : http://127.0.0.1:8001"

deploy:
	@echo "Deploying with Docker Compose..."
	bash deploy.sh

clean:
	@echo "Cleaning up..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".DS_Store" -delete
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache/ .coverage htmlcov/

docker-build:
	@echo "Building Docker images..."
	docker-compose build

docker-up:
	@echo "Starting Docker containers..."
	docker-compose up -d

docker-down:
	@echo "Stopping Docker containers..."
	docker-compose down

docker-logs:
	@echo "Showing Docker logs..."
	docker-compose logs -f

backup:
	@echo "Creating database backup..."
	@mkdir -p backups && \
	cp backend/db.sqlite3 backups/db_backup_$$(date +%Y%m%d_%H%M%S).sqlite3 && \
	echo "Backup created successfully"

restore:
	@echo "Select backup to restore:"
	@ls -lah backend/backups/
	@read -p "Enter backup filename: " backup_file; \
	cp backend/backups/$$backup_file backend/db.sqlite3 && \
	echo "Backup restored successfully"

shell:
	@echo "Opening Django shell..."
	cd backend && \
	. venv/bin/activate && \
	python manage.py shell

admin:
	@echo "Creating superuser..."
	cd backend && \
	. venv/bin/activate && \
	python manage.py createsuperuser

fixtures:
	@echo "Loading fixture data..."
	cd backend && \
	. venv/bin/activate && \
	python manage.py loaddata fixtures/categories.json

makemigrations:
	@echo "Creating migrations..."
	cd backend && \
	. venv/bin/activate && \
	python manage.py makemigrations

showmigrations:
	@echo "Showing migrations..."
	cd backend && \
	. venv/bin/activate && \
	python manage.py showmigrations

collectstatic:
	@echo "Collecting static files..."
	cd backend && \
	. venv/bin/activate && \
	python manage.py collectstatic --noinput

check:
	@echo "Running Django system checks..."
	cd backend && \
	. venv/bin/activate && \
	python manage.py check

requirements:
	@echo "Generating requirements.txt..."
	cd backend && \
	. venv/bin/activate && \
	pip freeze > requirements.txt

docs:
	@echo "API documentation is available in docs/API.md"

version:
	@echo "Flux Gestion v1.0.0"
