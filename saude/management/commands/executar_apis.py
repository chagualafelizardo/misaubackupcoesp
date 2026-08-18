import requests
import pandas as pd
from django.core.management.base import BaseCommand
from django.utils import timezone
from saude.models import ConfiguracaoAPI
from saude.views import importar_casos, importar_alertas, importar_cobertura, importar_leitos


class Command(BaseCommand):
    help = 'Executa todas as configurações de API que necessitam de atualização'

    def handle(self, *args, **options):
        configuracoes = ConfiguracaoAPI.objects.filter(ativo=True)
        executadas = 0
        erros = 0

        self.stdout.write(f"🔍 Verificando {configuracoes.count()} APIs ativas...")

        for config in configuracoes:
            if config.deve_executar():
                self.stdout.write(f"🔄 Executando: {config.nome}")
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
                    self.stdout.write(self.style.SUCCESS(f"✅ {config.nome}: {resultado['mensagem']}"))

                except Exception as e:
                    config.ultimo_status = f"Erro: {str(e)}"
                    config.save()
                    erros += 1
                    self.stdout.write(self.style.ERROR(f"❌ {config.nome}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f"📊 Resumo: {executadas} execuções, {erros} erros."))