"""
Django settings for config project.
"""
from pathlib import Path
import os
from dotenv import load_dotenv # Importar librería


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-0&h7!*(2wjje&%rbw!%xt#oz+kakt1%m&m$r62u&1cb=1d^h_n'

# Cargar variables de entorno desde el archivo .env
load_dotenv(BASE_DIR / '.env')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Lee la lista de hosts separados por coma
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '127.0.0.1').split(',')

# Modelo de usuario personalizado
AUTH_USER_MODEL = 'users.User'

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # Requerido por allauth
    
    # Apps de terceros
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    # Mis Apps
    'users',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware', # Allauth middleware
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# --- MODIFICA LA SECCIÓN DE BASE DE DATOS ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / os.getenv('DATABASE_NAME', 'db.sqlite3'),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# Internationalization
LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Cierra sesión inmediatamente sin preguntar confirmación
ACCOUNT_LOGOUT_ON_GET = True

# Salta la pantalla intermedia de confirmación de Google
SOCIALACCOUNT_LOGIN_ON_GET = True


# ==========================================
# CONFIGURACIÓN DE ALLAUTH (LOGIN SOLO POR EMAIL)
# ==========================================

SITE_ID = 2

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
ACCOUNT_LOGOUT_ON_GET = True

# --- ESTO ES LO QUE OBLIGA A USAR EMAIL ---
ACCOUNT_AUTHENTICATION_METHOD = 'email'  # <--- Solo Email
ACCOUNT_EMAIL_REQUIRED = True            # <--- Email obligatorio
ACCOUNT_USERNAME_REQUIRED = False        # <--- No pedir usuario
ACCOUNT_EMAIL_VERIFICATION = 'optional'  # <--- No bloquear si no ha confirmado

SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"

# Configuración del Formulario de Registro
ACCOUNT_SIGNUP_FIELDS = ['email', 'password1'] 
ACCOUNT_FORMS = {
    'signup': 'users.forms.CustomSignupForm',
}



# ==========================================
# CONFIGURACIÓN DE CORREO (SOLO DESARROLLO)
# ==========================================
# Si no está definido en el .env (como en producción), no usará el de consola
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')

# Configuración específica de Google
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'OAUTH_PKCE_ENABLED': True,
    }
}