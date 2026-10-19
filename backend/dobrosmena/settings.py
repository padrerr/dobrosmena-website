import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY','dev')
DEBUG = os.getenv('DEBUG','1') == '1'
ALLOWED_HOSTS = ['*']
INSTALLED_APPS = ['django.contrib.contenttypes','django.contrib.auth','django.contrib.sessions','django.contrib.staticfiles','rest_framework','core']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware']
ROOT_URLCONF = 'dobrosmena.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[Path('/frontend')],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request']}}]
WSGI_APPLICATION = 'dobrosmena.wsgi.application'
DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','NAME':os.getenv('POSTGRES_DB','dobrosmena'),'USER':os.getenv('POSTGRES_USER','dobrosmena'),'PASSWORD':os.getenv('POSTGRES_PASSWORD','dobrosmena_local'),'HOST':os.getenv('POSTGRES_HOST','localhost'),'PORT':os.getenv('POSTGRES_PORT','5432')}}
LANGUAGE_CODE='ru-ru'; TIME_ZONE='Asia/Krasnoyarsk'; USE_I18N=True; USE_TZ=True
STATIC_URL='static/'; STATICFILES_DIRS=[Path('/frontend/static')]
MEDIA_URL='/media/'; MEDIA_ROOT=BASE_DIR / 'media'
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('core.authentication.BearerAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ('core.permissions.IsAuthenticated',),
}
