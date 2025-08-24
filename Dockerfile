FROM python:3.13-alpine

# Dependências
RUN apk update && apk add --no-cache \
    gcc \
    libc-dev \
    libffi-dev \
    linux-headers \
    musl-dev \
    build-base \
    mariadb-connector-c-dev \
    mariadb-dev \
    postgresql-dev \
    vim \
    curl

# Instalação do Poetry
ENV POETRY_VERSION=1.8.2
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

WORKDIR /myfinance

# Copia primeiro só pyproject + lock p/ cache de dependências
COPY myfinance/pyproject.toml myfinance/poetry.lock* /myfinance/

RUN poetry config virtualenvs.create false \
  && poetry install --no-ansi --no-root

# Agora copia o restante do código
COPY myfinance /myfinance

CMD ["sh"]
