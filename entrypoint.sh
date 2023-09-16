#!/bin/sh

python manage.py makemigrations statement
python manage.py migrate statement
python manage.py makemigrations login
python manage.py migrate login
python manage.py collectstatic --no-input

gunicorn financeiro.wsgi:application --bind 0.0.0.0:8000
