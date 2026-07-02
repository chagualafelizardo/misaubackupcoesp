# Desenvolvido por: Felizardo L. A. Chaguala para MISAU
# 1. Cria as migrações para o app saude
docker-compose exec web python manage.py makemigrations saude

# 2. Aplica TODAS as migrações pendentes (incluindo admin, auth, etc.)
docker-compose exec web python manage.py migrate

# 3. (Opcional) Crie um superusuário para acessar o admin
docker-compose exec web python manage.py createsuperuser

docker-compose down -v
docker-compose up -d
docker-compose exec web python manage.py makemigrations saude
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py populate   # se tiver o comando