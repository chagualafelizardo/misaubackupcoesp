from django.apps import AppConfig
import os
import sys


class SaudeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'saude'

    def ready(self):
        # Evita iniciar o scheduler em processos secundários (ex: runserver reload)
        if os.environ.get('RUN_MAIN') != 'true' and 'runserver' not in sys.argv:
            return

        from apscheduler.schedulers.background import BackgroundScheduler
        import logging
        import traceback

        logger = logging.getLogger(__name__)

        def executar_apis_agendadas():
            # Importações LOCAIS para evitar conflitos de carregamento
            from .models import ConfiguracaoAPI
            from .views import processar_configuracao_api

            try:
                configuracoes = ConfiguracaoAPI.objects.filter(ativo=True)
                executadas = 0
                erros = 0

                for config in configuracoes:
                    # Verifica se o objeto tem o método 'deve_executar'
                    if not hasattr(config, 'deve_executar'):
                        logger.error(f"❌ Configuração {config.id} não tem método 'deve_executar'. Tipo: {type(config)}")
                        continue

                    if config.deve_executar():
                        try:
                            sucesso = processar_configuracao_api(config)
                            if sucesso:
                                executadas += 1
                            else:
                                erros += 1
                        except Exception as e:
                            # Captura exceções não tratadas
                            msg = f"Erro agendador: {str(e)}"
                            config.ultimo_status = msg[:254]
                            config.save(update_fields=['ultimo_status'])
                            erros += 1
                            logger.error(f"❌ API '{config.nome}': {msg}")
                            logger.error(traceback.format_exc())

                if executadas:
                    logger.info(f"✅ APScheduler executou {executadas} API(s) com sucesso.")
                if erros:
                    logger.warning(f"⚠️ APScheduler registou {erros} erro(s) na execução.")
                if not executadas and not erros:
                    logger.debug("APScheduler: nenhuma API precisou ser executada.")

            except Exception as e:
                logger.error(f"❌ Erro crítico no agendador: {str(e)}")
                logger.error(traceback.format_exc())

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            executar_apis_agendadas,
            trigger='interval',
            minutes=5,
            id='executar_apis_agendadas',
            replace_existing=True
        )
        scheduler.start()
        logger.info("✅ APScheduler iniciado com sucesso!")