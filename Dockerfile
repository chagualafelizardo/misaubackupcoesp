FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=misau_backend.settings

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    cron \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY cronjob /etc/cron.d/django-cron
RUN chmod 0644 /etc/cron.d/django-cron && crontab /etc/cron.d/django-cron

RUN touch /var/log/django_cron.log && chmod 0666 /var/log/django_cron.log

EXPOSE 8000

# Inicia cron e depois o servidor Django
CMD ["sh", "-c", "service cron start && python manage.py runserver 0.0.0.0:8000"]