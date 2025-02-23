#!/bin/sh

python manage.py makemigrations atividades
python manage.py migrate atividades
python manage.py makemigrations login
python manage.py migrate login
python manage.py collectstatic --no-input

gunicorn produtividade.wsgi:application --bind 0.0.0.0:8000

# Descomente a linha abaixo para impedir que o container caia em caso de erro
tail -f /dev/null
