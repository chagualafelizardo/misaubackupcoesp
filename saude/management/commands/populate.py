from django.core.management.base import BaseCommand
from saude.models import *
from datetime import date, timedelta
import random

class Command(BaseCommand):
    help = 'Popula o banco com dados de exemplo para o MISAU'

    def handle(self, *args, **options):
        self.stdout.write('Criando dados iniciais...')

        # Províncias
        provincias = [
            {'nome': 'Maputo Cidade', 'sigla': 'MPM'},
            {'nome': 'Maputo', 'sigla': 'MPT'},
            {'nome': 'Gaza', 'sigla': 'GAZ'},
            {'nome': 'Inhambane', 'sigla': 'INH'},
            {'nome': 'Sofala', 'sigla': 'SOF'},
            {'nome': 'Manica', 'sigla': 'MAN'},
            {'nome': 'Tete', 'sigla': 'TET'},
            {'nome': 'Zambézia', 'sigla': 'ZAM'},
            {'nome': 'Nampula', 'sigla': 'NMP'},
            {'nome': 'Cabo Delgado', 'sigla': 'CAB'},
            {'nome': 'Niassa', 'sigla': 'NIA'},
        ]
        for p in provincias:
            obj, created = Provincia.objects.get_or_create(nome=p['nome'], sigla=p['sigla'])
            self.stdout.write(f'Província {obj.nome} {"criada" if created else "já existente"}.')

        doencas = [
            {'nome': 'Malária', 'tipo': 'malaria', 'sintomas': 'Febre alta, calafrios\nDores no corpo e dor de cabeça\nNáuseas, vómitos', 'orientacao': 'Teste rápido gratuito no posto de saúde + tratamento imediato.'},
            {'nome': 'Cólera', 'tipo': 'colera', 'sintomas': 'Diarreia aquosa abundante\nVómitos\nSede excessiva e fraqueza', 'orientacao': 'Hidratação oral (soro caseiro) e procure a unidade sanitária mais próxima.'},
        ]
        for d in doencas:
            obj, created = Doenca.objects.get_or_create(nome=d['nome'], defaults=d)
            self.stdout.write(f'Doença {obj.nome} {"criada" if created else "já existente"}.')

        # Casos de malária (últimas 6 semanas, em algumas províncias)
        malaria = Doenca.objects.get(tipo='malaria')
        provs = Provincia.objects.all()[:6]
        for prov in provs:
            for i in range(6):
                data = date.today() - timedelta(days=(i*7))
                qtd = random.randint(800, 2800)
                CasoDoenca.objects.get_or_create(
                    provincia=prov,
                    doenca=malaria,
                    data=data,
                    defaults={'quantidade': qtd, 'confirmados': int(qtd*0.8)}
                )
            self.stdout.write(f'Casos de malária criados para {prov.nome}')

        # Alertas (agora usando nomes de doenças, não tipos)
        alertas = [
            {'prov': 'CAB', 'doenca_nome': 'Cólera', 'titulo': 'Cólera e desnutrição em distritos de deslocados', 'gravidade': 'critico', 'status': 'Resposta em curso', 'orientacao': 'Ver recomendações'},
            {'prov': 'SOF', 'doenca_nome': 'Malária', 'titulo': 'Aumento de malária grave (Beira, Nhamatanda)', 'gravidade': 'atencao', 'status': 'Monitoramento', 'orientacao': 'Uso de mosquiteiro'},
            {'prov': 'ZAM', 'doenca_nome': 'Cólera', 'titulo': 'Surtos de cólera em Mopeia', 'gravidade': 'atencao', 'status': 'Campanha de vacinação', 'orientacao': 'Lavar mãos'},
        ]
        for a in alertas:
            prov = Provincia.objects.get(sigla=a['prov'])
            doenca = Doenca.objects.get(nome=a['doenca_nome'])
            Alerta.objects.get_or_create(
                provincia=prov,
                doenca=doenca,
                titulo=a['titulo'],
                defaults={
                    'descricao': a['titulo'],
                    'gravidade': a['gravidade'],
                    'status': a['status'],
                    'orientacao': a['orientacao'],
                    'active': True
                }
            )
            self.stdout.write(f'Alerta {a["titulo"]} criado.')

        # Leitos (exemplo)
        for prov in Provincia.objects.all()[:5]:
            Leito.objects.get_or_create(
                provincia=prov,
                defaults={'total': random.randint(50, 200), 'ocupados': random.randint(20, 150)}
            )
            self.stdout.write(f'Leitos criados para {prov.nome}')

        # Vacinas e cobertura
        vacina, _ = Vacina.objects.get_or_create(
            nome='BCG',
            defaults={'descricao': 'Vacina contra tuberculose', 'doses_recomendadas': 1, 'idade_minima': 0}
        )
        for prov in Provincia.objects.all()[:5]:
            CoberturaVacinal.objects.get_or_create(
                provincia=prov,
                vacina=vacina,
                ano=date.today().year,
                defaults={'percentual': round(random.uniform(70, 95), 1)}
            )
            self.stdout.write(f'Cobertura vacinal criada para {prov.nome}')

        self.stdout.write(self.style.SUCCESS('Dados populados com sucesso!'))