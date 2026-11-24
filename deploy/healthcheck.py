"""Readiness do Django e confirmação do slot servido pelo Nginx."""
import http.client
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myfinance.settings')
import django

django.setup()
from django.conf import settings
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute('SELECT 1')
    if cursor.fetchone()[0] != 1:
        raise SystemExit('Banco indisponível.')

host = next((h.lstrip('.') for h in settings.ALLOWED_HOSTS if h != '*'), 'localhost')
proxy_slot = sys.argv[1] if len(sys.argv) > 1 else None
client = http.client.HTTPConnection('172.18.0.5' if proxy_slot else '127.0.0.1',
                                    80 if proxy_slot else 8000, timeout=2)
try:
    client.request('GET', '/', headers={'Host': host})
    response = client.getresponse()
    if not 200 <= response.status < 400:
        raise SystemExit(f'Aplicação ainda não está pronta: HTTP {response.status}.')
    if proxy_slot and response.getheader('X-Myfinance-Slot') != proxy_slot:
        raise SystemExit('Aguardando o Nginx ativar o novo slot...')
except OSError:
    raise SystemExit('Aguardando a aplicação aceitar conexões...')
finally:
    client.close()
