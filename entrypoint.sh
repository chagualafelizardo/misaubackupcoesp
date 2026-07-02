#!/bin/sh
set -e

echo "Iniciando cron..."
service cron start
echo "Cron iniciado com sucesso!"

echo "Iniciando servidor Django..."
exec "$@"