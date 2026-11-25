# ============================================
# Dockerfile - Punto Participa (Django + PostgreSQL)
# Se construye desde docker-compose.yml, con la raíz del repositorio como contexto
# ============================================

FROM python:3.12-slim

# Evita archivos .pyc y buffers de salida (logs en tiempo real)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias de sistema necesarias para psycopg2 y compilación
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g; s|http://security.debian.org|https://security.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gettext \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python primero (aprovecha cache de Docker)
# El contexto de construcción es la raíz del repositorio (ver docker-compose.yml)
COPY src/punto_participa_project/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY src/punto_participa_project/ .

# Script de arranque (espera a la BD, migra, colecta estáticos, levanta gunicorn).
# Va fuera de /app porque docker-compose monta el código encima de /app.
COPY maquinasVirtuales/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
