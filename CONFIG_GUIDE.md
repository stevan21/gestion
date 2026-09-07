# Configuration Files Guide for Flux Gestion

## Overview

This directory contains configuration files for various deployment and development scenarios.

### Environment Files

#### `.env` (Development)
- Used for local development
- Contains debug settings and development database configuration
- Never commit sensitive data to version control

#### `.env.production`
- Template for production environment
- Should be configured with real values before deployment
- Contains production database credentials and security settings

### Deployment Configurations

#### `docker-compose.yml`
- Multi-container setup for development
- Services: PostgreSQL, Redis, Django backend, Frontend, Nginx reverse proxy
- Usage: `docker-compose up -d`

#### `Dockerfile`
- Containerizes the Django backend
- Based on Python 3.11-slim
- Uses Gunicorn for WSGI server

#### `nginx.conf`
- Reverse proxy configuration
- Handles static/media files
- Proxies API requests to Django
- Production-ready HTTPS configuration template

#### `frontend/nginx.conf`
- Nginx configuration for frontend SPA
- Enables SPA routing (try_files)
- Caches static assets

### Server Configurations

#### `backend/gunicorn_config.py`
- Gunicorn WSGI server configuration
- Lives in `backend/` because that is the process working directory
- Worker count defaults to `2 x CPU + 1`, overridable via `GUNICORN_WORKERS`
- Bind address, thread count and log level are read from the environment
- Used by `run_server.sh`, `docker-compose.yml` and the systemd unit

#### `fluxgestion.service`
- Systemd service file for Linux
- Enables auto-start on system boot
- Managed via: `systemctl start fluxgestion`

#### `supervisord.conf`
- Supervisord process manager configuration
- Manages Django, Celery beat, and Celery worker processes
- Alternative to systemd for process management

### Scripts

#### `init.sh` / `init.bat`
- Initialize project for development
- Creates virtual environment, installs dependencies, runs migrations
- Usage: `bash init.sh` or `init.bat`

#### `deploy.sh`
- Deploy project using Docker Compose
- Builds images, runs migrations, loads fixtures
- Usage: `bash deploy.sh`

#### `run_server.sh`
- Start Django server with Gunicorn
- Handles migrations and static file collection
- Usage: `bash run_server.sh`

#### `run_tests.sh`
- Run test suite with coverage reporting
- Usage: `bash run_tests.sh`

#### `maintenance.sh`
- Interactive maintenance tool
- Tasks: cache clearing, database reset, backups, testing, linting
- Usage: `bash maintenance.sh`

### Testing Configuration

#### `backend/conftest.py`
- Bootstraps Django so the suite can also be run under pytest
- The supported entry point remains `python manage.py test api`
- Django builds a throwaway test database automatically

### Backend Modules

#### `api/`
- Django REST API application
- Contains models, views, serializers, permissions
- Signal handlers for model events
- Custom managers, validators, filters

#### `fluxgestion/`
- Main Django project configuration
- Settings for development and production
- URL routing and WSGI/ASGI configuration
- Celery configuration for async tasks

### Frontend Configuration

#### `frontend/`
- Vanilla JavaScript SPA
- HTML, CSS, and JavaScript modules
- Chart.js integration for visualizations
- RESTful API client

## Quick Start

### Development Setup
```bash
# Clone repository
git clone <repository>
cd fluxgestion

# Run initialization script
bash init.sh

# Start backend
cd backend
python manage.py runserver

# In another terminal, start frontend
cd frontend
python -m http.server 8001
```

### Docker Deployment
```bash
# Build and start all services
bash deploy.sh

# Access services
# Frontend: http://localhost
# API: http://localhost/api/
# Admin: http://localhost/admin/
```

### Production Deployment
```bash
# Update environment configuration
vi backend/.env.production

# Build Docker image
docker build -t fluxgestion:latest .

# Run with production settings
docker run -d \
  --env-file backend/.env.production \
  -p 8000:8000 \
  fluxgestion:latest
```

## Environment Variables Reference

### Django Core
- `DEBUG`: Enable debug mode (development only)
- `SECRET_KEY`: Django secret key (change in production)
- `ALLOWED_HOSTS`: Comma-separated host list
- `LANGUAGE_CODE`: Language locale (default: fr-fr)
- `TIME_ZONE`: Timezone (default: Europe/Paris)

### Database
- `DB_ENGINE`: Database backend (default: sqlite3)
- `DB_NAME`: Database name/path
- `DB_USER`: Database username (PostgreSQL)
- `DB_PASSWORD`: Database password (PostgreSQL)
- `DB_HOST`: Database host (PostgreSQL)
- `DB_PORT`: Database port (PostgreSQL)

### Security
- `SECURE_SSL_REDIRECT`: Force HTTPS (production)
- `SESSION_COOKIE_SECURE`: Secure cookie flag
- `CSRF_COOKIE_SECURE`: CSRF cookie secure flag

### API & CORS
- `CORS_ALLOWED_ORIGINS`: Comma-separated CORS origins
- `REST_FRAMEWORK_*`: DRF-specific settings

### Email
- `EMAIL_BACKEND`: Email backend
- `EMAIL_HOST`: SMTP server
- `EMAIL_PORT`: SMTP port
- `EMAIL_HOST_USER`: Email username
- `EMAIL_HOST_PASSWORD`: Email password
- `EMAIL_USE_TLS`: Use TLS for email

## Troubleshooting

### Database Issues
```bash
# Check migrations
python manage.py showmigrations

# Create missing migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Reset database (development only)
rm db.sqlite3
python manage.py migrate
```

### Static Files
```bash
# Collect static files
python manage.py collectstatic --noinput

# Clear static file cache
python manage.py collectstatic --clear --noinput
```

### Cache Issues
```bash
# Clear cache in Django shell
python manage.py shell -c "from django.core.cache import cache; cache.clear()"
```

### Permission Issues
```bash
# Fix file permissions in Docker
docker exec <container_id> chmod -R 755 /app
```

## Security Checklist for Production

- [ ] Change `SECRET_KEY` to a strong random value
- [ ] Set `DEBUG = False`
- [ ] Configure real database (PostgreSQL recommended)
- [ ] Set up HTTPS/SSL certificate
- [ ] Configure allowed hosts
- [ ] Enable CSRF protection
- [ ] Set secure cookie flags
- [ ] Configure CORS properly
- [ ] Use environment variables for secrets
- [ ] Set up proper logging
- [ ] Configure backup strategy
- [ ] Test disaster recovery

## Useful Commands

```bash
# Create Django superuser
python manage.py createsuperuser

# Load fixture data
python manage.py seed_demo --months 6

# Run tests with coverage
coverage run --source='.' manage.py test api
coverage report

# Format code
black .

# Lint code
flake8 .

# Find and update database constraints
python manage.py inspectdb

# Generate Django documentation
python manage.py help
```

## Support & Documentation

- Django: https://docs.djangoproject.com/
- Django REST Framework: https://www.django-rest-framework.org/
- Docker: https://docs.docker.com/
- Gunicorn: https://gunicorn.org/
- Celery: https://docs.celeryproject.io/
