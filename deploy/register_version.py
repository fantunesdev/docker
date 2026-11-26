"""Registra a versão de uma imagem aprovada pelo CI; pode ser repetido."""
import os
import re
import sys

import django

commit = sys.argv[1]
if not re.fullmatch(r'[0-9a-f]{40}', commit):
    raise SystemExit('SHA de deploy inválido.')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myfinance.settings')
django.setup()

from django.utils import timezone
from statement.models import Version

version = f'v2.0.g{commit[:12]}'
latest = Version.objects.order_by('-id').first()
if latest is None or latest.version != version:
    Version.objects.create(version=version, date=timezone.localdate())
print(f'Versão registrada: {version} ({commit})')
