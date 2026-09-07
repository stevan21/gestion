FROM python:3.11-slim

WORKDIR /app

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copier les fichiers requirements
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste de l'application
COPY . .

# Créer les répertoires statiques
RUN mkdir -p staticfiles media

# Exposer le port
EXPOSE 8000

# Commande par défaut
CMD ["gunicorn", "fluxgestion.wsgi:application", "--bind", "0.0.0.0:8000"]
