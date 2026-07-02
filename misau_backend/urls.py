"""
URL configuration for misaucoespbackend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path
from saude.views import (
    dashboard, login_view, logout_view, dashboard_restrito,
    importar_dados, buscar_dados_api,
    listar_apis, criar_api, editar_api, deletar_api, executar_api, executar_todas_apis
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard, name='dashboard'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('painel/', dashboard_restrito, name='dashboard_restrito'),
    path('importar/', importar_dados, name='importar_dados'),
    path('api-importar/', buscar_dados_api, name='api_importar'),
    path('apis/', listar_apis, name='listar_apis'),
    path('apis/criar/', criar_api, name='criar_api'),
    path('apis/editar/<int:pk>/', editar_api, name='editar_api'),
    path('apis/deletar/<int:pk>/', deletar_api, name='deletar_api'),
    path('apis/executar/<int:pk>/', executar_api, name='executar_api'),
    path('apis/executar-todas/', executar_todas_apis, name='executar_todas_apis'),
]