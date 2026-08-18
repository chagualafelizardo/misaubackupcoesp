from django.apps import AppConfig
import os
import sys


class SaudeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'saude'

    def ready(self):
        # Evita executar o agendador em migrações, testes ou comandos de shell
        if os.environ.get('RUN_MAIN') != 'true' and 'runserver' not in sys.argv:
            return

        # Importa aqui para evitar carregamento precoce
        from apscheduler.schedulers.background import BackgroundScheduler
        from django.conf import settings
        from django.utils import timezone
        import logging

        logger = logging.getLogger(__name__)

        def executar_apis_agendadas():
            """Função que será chamada periodicamente."""
            try:
                from .views import executar_todas_apis
                # Precisamos de um request fake ou usar o método diretamente
                # Como executar_todas_apis é uma view que espera request, 
                # vamos chamar a lógica interna sem o request
                from .models import ConfiguracaoAPI
                import requests
                import pandas as pd
                from .views import importar_casos, importar_alertas, importar_cobertura, importar_leitos

                configuracoes = ConfiguracaoAPI.objects.filter(ativo=True)
                executadas = 0
                for config in configuracoes:
                    if config.deve_executar():
                        try:
                            headers = {'Authorization': f'Bearer {config.token}'} if config.token else {}
                            response = requests.get(config.url, headers=headers, timeout=30)
                            response.raise_for_status()
                            dados = response.json()

                            if isinstance(dados, list):
                                df = pd.DataFrame(dados)
                            elif isinstance(dados, dict) and 'results' in dados:
                                df = pd.DataFrame(dados['results'])
                            elif isinstance(dados, dict) and 'data' in dados:
                                df = pd.DataFrame(dados['data'])
                            else:
                                raise ValueError('Formato de resposta não reconhecido.')

                            if config.tipo_dado == 'casos':
                                resultado = importar_casos(df)
                            elif config.tipo_dado == 'alertas':
                                resultado = importar_alertas(df)
                            elif config.tipo_dado == 'cobertura':
                                resultado = importar_cobertura(df)
                            elif config.tipo_dado == 'leitos':
                                resultado = importar_leitos(df)
                            else:
                                raise ValueError('Tipo de dados inválido.')

                            config.ultima_execucao = timezone.now()
                            config.ultimo_status = f"Sucesso: {resultado['mensagem']}"
                            config.save()
                            executadas += 1
                        except Exception as e:
                            config.ultimo_status = f"Erro: {str(e)}"
                            config.save()

                if executadas:
                    logger.info(f"APScheduler executou {executadas} APIs.")
                else:
                    logger.debug("APScheduler: nenhuma API precisou ser executada.")

            except Exception as e:
                logger.error(f"Erro no agendador: {str(e)}")

        # Inicia o agendador
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            executar_apis_agendadas,
            trigger='interval',
            minutes=5,  # A cada 5 minutos
            id='executar_apis_agendadas',
            replace_existing=True
        )
        scheduler.start()
        logger.info("✅ APScheduler iniciado com sucesso!")