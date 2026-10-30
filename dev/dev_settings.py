"""Configurações locais carregadas apenas pelo Compose de desenvolvimento."""

from myfinance.settings import *  # noqa: F403

DEBUG = True
INSTALLED_APPS = ["daphne", *INSTALLED_APPS]  # noqa: F405
ASGI_APPLICATION = "dev_asgi.application"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://redis-myfin:6379/1",
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
