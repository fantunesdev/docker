#!/bin/sh

python manage.py makemigrations statement
python manage.py migrate statement 0001_initial --fake
python manage.py migrate statement 0002_version --fake
python manage.py migrate statement 0003_alter_version_options --fake
python manage.py migrate statement 0004_account_file_handler_conf_card_file_handler_conf --fake
python manage.py migrate statement 0005_fixedexpenses --fake
python manage.py migrate statement 0006_dream_alter_version_options_version_date_portion --fake
python manage.py migrate statement
python manage.py makemigrations login
python manage.py migrate login
python manage.py collectstatic --no-input

gunicorn myfinance.wsgi:application --bind 0.0.0.0:8000
