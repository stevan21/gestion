@echo off
REM Script d'initialisation pour Windows

echo ======================================
echo Initialisation de Flux Gestion
echo ======================================

REM Vérifier Python
echo.
echo [*] Vérification de Python...
python --version
if errorlevel 1 (
    echo [!] Python n'est pas installé ou pas dans le PATH
    pause
    exit /b 1
)

REM Naviguer au dossier backend
cd backend

REM Créer l'environnement virtuel
echo [*] Création de l'environnement virtuel...
python -m venv venv
if errorlevel 1 (
    echo [!] Erreur lors de la création de l'environnement virtuel
    pause
    exit /b 1
)

REM Activer l'environnement virtuel
echo [*] Activation de l'environnement virtuel...
call venv\Scripts\activate.bat

REM Installer les dépendances
echo [*] Installation des dépendances...
pip install -r requirements.txt
if errorlevel 1 (
    echo [!] Erreur lors de l'installation des dépendances
    pause
    exit /b 1
)

REM Copier le fichier .env
if not exist .env (
    echo [*] Copie du fichier .env...
    copy .env.example .env
)

REM Appliquer les migrations
echo [*] Application des migrations...
python manage.py migrate
if errorlevel 1 (
    echo [!] Erreur lors de l'application des migrations
    pause
    exit /b 1
)

REM Charger les données de test
echo [*] Chargement des données de test...
python manage.py loaddata fixtures/categories.json

REM Créer un superutilisateur
echo [*] Création d'un superutilisateur (optionnel)...
python manage.py createsuperuser

echo.
echo ======================================
echo [OK] Initialisation réussie!
echo ======================================
echo.
echo Pour démarrer le serveur:
echo   cd backend
echo   venv\Scripts\activate
echo   python manage.py runserver
echo.
echo Dans un autre terminal, pour le frontend:
echo   cd frontend
echo   python -m http.server 8001
echo.
echo Accédez à l'application sur http://localhost:8001
echo.
pause
