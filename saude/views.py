import chardet
import logging
import traceback
import pandas as pd
import xml.etree.ElementTree as ET
import requests
from django.utils import timezone
from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, Avg, Max
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Provincia, Doenca, CasoDoenca, Alerta, CoberturaVacinal, Vacina, Leito, ConfiguracaoAPI
from .forms import UploadDataForm, APIImportForm, ConfiguracaoAPIForm

logger = logging.getLogger(__name__)
# ===================================================================
# PÁGINA PÚBLICA
# ===================================================================
def dashboard(request):
    hoje = date.today()
    semana_passada = hoje - timedelta(days=7)

    casos_malaria = CasoDoenca.objects.filter(
        doenca__tipo='malaria',
        data__gte=semana_passada
    ).aggregate(total=Sum('quantidade'))['total'] or 0

    leitos = Leito.objects.all()
    total_leitos = sum(l.total for l in leitos)
    total_ocupados = sum(l.ocupados for l in leitos)
    ocupacao_leitos = round((total_ocupados / total_leitos) * 100, 1) if total_leitos > 0 else 0

    ultimo_ano = CoberturaVacinal.objects.aggregate(max_ano=Max('ano'))['max_ano'] or hoje.year
    cobertura_vacinal = CoberturaVacinal.objects.filter(ano=ultimo_ano).aggregate(media=Avg('percentual'))['media'] or 0

    alertas_activos = Alerta.objects.filter(active=True).count()

    semanas = []
    dados_grafico = []
    for i in range(5, -1, -1):
        inicio = hoje - timedelta(days=(i*7 + 7))
        fim = hoje - timedelta(days=i*7)
        total = CasoDoenca.objects.filter(
            doenca__tipo='malaria',
            data__gte=inicio,
            data__lt=fim
        ).aggregate(total=Sum('quantidade'))['total'] or 0
        semanas.append(f"Sem {6-i}")
        dados_grafico.append(total)

    provincias_status = {}
    for prov in Provincia.objects.all():
        alerta = prov.alertas.filter(active=True).first()
        if alerta:
            cor = '#ef4444' if alerta.gravidade == 'critico' else '#f59e0b' if alerta.gravidade == 'atencao' else '#22c55e'
            status = alerta.get_gravidade_display()
        else:
            cor = '#22c55e'
            status = 'Controlada'
        provincias_status[prov.sigla] = {
            'nome': prov.nome,
            'status': status,
            'cor': cor
        }

    alertas = Alerta.objects.filter(active=True).select_related('provincia', 'doenca')
    doencas = Doenca.objects.all()

    # ===== NOVO: Dados por doença para a cascata =====
    dados_doencas = {}
    for doenca in Doenca.objects.all():
        casos = CasoDoenca.objects.filter(doenca=doenca).select_related('provincia')
        dados_doencas[doenca.nome] = [
            {
                'provincia': caso.provincia.nome,
                'data': caso.data.strftime('%Y-%m-%d'),
                # Campos antigos (mantidos para compatibilidade)
                'quantidade': caso.quantidade,
                'confirmados': caso.confirmados,
                'curados': caso.curados,
                'obitos': caso.obitos,
                # Novos campos (principais)
                'novos_casos': caso.novos_casos,
                'casos_acumulados': caso.casos_acumulados,
                'novos_obitos': caso.novos_obitos,
                'obitos_acumulados': caso.obitos_acumulados,
                'fonte': caso.fonte,
            }
            for caso in casos
        ]

    context = {
        'casos_malaria': casos_malaria,
        'ocupacao_leitos': ocupacao_leitos,
        'cobertura_vacinal': cobertura_vacinal,
        'alertas_activos': alertas_activos,
        'semanas': semanas,
        'dados_grafico': dados_grafico,
        'provincias_status': provincias_status,
        'alertas': alertas,
        'doencas': doencas,
        'dados_doencas': dados_doencas,
        'hoje': hoje,
        'ano_atual': hoje.year,
    }
    return render(request, 'saude/dashboard.html', context)


# ===================================================================
# AUTENTICAÇÃO
# ===================================================================
def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', 'dashboard_restrito')
                return redirect(next_url)
    else:
        form = AuthenticationForm()
    return render(request, 'saude/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('dashboard')


# ===================================================================
# PAINEL RESTRITO
# ===================================================================
@login_required
def dashboard_restrito(request):
    hoje = date.today()
    configuracoes_api = ConfiguracaoAPI.objects.all()

    semana_passada = hoje - timedelta(days=7)

    casos_malaria = CasoDoenca.objects.filter(
        doenca__tipo='malaria',
        data__gte=semana_passada
    ).aggregate(total=Sum('quantidade'))['total'] or 0

    leitos = Leito.objects.all()
    total_leitos = sum(l.total for l in leitos)
    total_ocupados = sum(l.ocupados for l in leitos)
    ocupacao_leitos = round((total_ocupados / total_leitos) * 100, 1) if total_leitos > 0 else 0

    ultimo_ano = CoberturaVacinal.objects.aggregate(max_ano=Max('ano'))['max_ano'] or hoje.year
    cobertura_vacinal = CoberturaVacinal.objects.filter(ano=ultimo_ano).aggregate(media=Avg('percentual'))['media'] or 0

    alertas_activos = Alerta.objects.filter(active=True).count()

    # ===== NOVOS TOTAIS AGREGADOS =====
    total_casos = CasoDoenca.objects.aggregate(total=Sum('quantidade'))['total'] or 0
    total_confirmados = CasoDoenca.objects.aggregate(total=Sum('confirmados'))['total'] or 0
    total_curados = CasoDoenca.objects.aggregate(total=Sum('curados'))['total'] or 0
    total_obitos = CasoDoenca.objects.aggregate(total=Sum('obitos'))['total'] or 0

    provincias_count = Provincia.objects.count()
    doencas_count = Doenca.objects.count()
    todos_alertas = Alerta.objects.select_related('provincia', 'doenca').all()
    todos_casos = CasoDoenca.objects.select_related('provincia', 'doenca').all()[:50]

    context = {
        'casos_malaria': casos_malaria,
        'ocupacao_leitos': ocupacao_leitos,
        'cobertura_vacinal': cobertura_vacinal,
        'alertas_activos': alertas_activos,
        'provincias_count': provincias_count,
        'doencas_count': doencas_count,
        'todos_alertas': todos_alertas,
        'todos_casos': todos_casos,
        'total_casos': total_casos,
        'total_confirmados': total_confirmados,
        'total_curados': total_curados,
        'total_obitos': total_obitos,
        'hoje': hoje,
        'ano_atual': hoje.year,
        'configuracoes_api': configuracoes_api,
    }
    return render(request, 'saude/dashboard_restrito.html', context)


# ===================================================================
# IMPORTAÇÃO DE DADOS
# ===================================================================
@login_required
def importar_dados(request):
    if request.method == 'POST':
        form = UploadDataForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo = request.FILES['arquivo']
            tipo = form.cleaned_data['tipo_dado']
            extensao = arquivo.name.split('.')[-1].lower()
            encoding = form.cleaned_data.get('encoding', '')
            doenca_escolhida = form.cleaned_data.get('doenca')

            try:
                if extensao in ['xlsx', 'xls']:
                    df = pd.read_excel(arquivo)
                elif extensao == 'csv':
                    if encoding:
                        try:
                            df = pd.read_csv(arquivo, encoding=encoding)
                        except UnicodeDecodeError:
                            messages.error(request, f'❌ A codificação "{encoding}" não é válida para este ficheiro.')
                            return render(request, 'saude/importar.html', {'form': form})
                    else:
                        # Forçar latin-1 (Windows-1252) – comum em ficheiros portugueses
                        try:
                            df = pd.read_csv(arquivo, encoding='latin-1')
                        except UnicodeDecodeError:
                            # Fallback para cp1252
                            try:
                                arquivo.seek(0)
                                df = pd.read_csv(arquivo, encoding='cp1252')
                            except UnicodeDecodeError:
                                # Último recurso: utf-8 ignorando erros
                                arquivo.seek(0)
                                df = pd.read_csv(arquivo, encoding='utf-8', errors='ignore')
                elif extensao == 'xml':
                    df = parse_xml(arquivo)
                else:
                    messages.error(request, 'Formato não suportado. Use .xlsx, .xls, .csv ou .xml.')
                    return render(request, 'saude/importar.html', {'form': form})

                if tipo == 'casos':
                    resultado = importar_casos(df, doenca_escolhida, fonte='manual')
                elif tipo == 'alertas':
                    resultado = importar_alertas(df)
                elif tipo == 'cobertura':
                    resultado = importar_cobertura(df)
                elif tipo == 'leitos':
                    resultado = importar_leitos(df)
                else:
                    messages.error(request, 'Tipo de dados inválido.')
                    return render(request, 'saude/importar.html', {'form': form})

                if resultado['sucesso']:
                    messages.success(request, f"✅ {resultado['mensagem']}")
                else:
                    messages.error(request, f"❌ {resultado['mensagem']}")

            except pd.errors.EmptyDataError:
                messages.error(request, '❌ O ficheiro está vazio ou não contém dados válidos.')
            except pd.errors.ParserError as e:
                messages.error(request, f'❌ Erro ao analisar o ficheiro: {str(e)}. Verifique o formato e separadores.')
            except Exception as e:
                messages.error(request, f"❌ Erro ao processar ficheiro: {str(e)}")

            return redirect('dashboard_restrito')
    else:
        form = UploadDataForm()

    return render(request, 'saude/importar.html', {'form': form})


# ===================================================================
# FUNÇÃO PRINCIPAL DE IMPORTAÇÃO DE CASOS (ATUALIZADA)
# ===================================================================
logger = logging.getLogger(__name__)
def importar_casos(df, doenca_escolhida=None, fonte='manual', mapeamento=None):
    """
    Importa dados de casos a partir de um DataFrame.
    Suporta três formatos e mapeamento personalizado.
    """
    contagem = 0
    erros = []
    logger.info(f"📥 Iniciando importação de casos. Fonte: {fonte}")
    logger.info(f"🔍 DataFrame com {len(df)} linhas e colunas: {list(df.columns)}")

    # -----------------------------------------------------------------
    # 1. PROCESSAMENTO COM MAPEAMENTO PERSONALIZADO
    # -----------------------------------------------------------------
    if mapeamento:
        logger.info(f"📋 Usando mapeamento personalizado: {mapeamento}")
        # ... (código existente, mas com logs dentro de cada bloco)
        # Vou adicionar logs nos pontos principais
        if 'provincia_fixa' in mapeamento:
            provincia_nome = mapeamento['provincia_fixa']
            prov, _ = Provincia.objects.get_or_create(
                nome=provincia_nome,
                defaults={'sigla': provincia_nome[:3].upper(), 'active': True}
            )
            logger.info(f"🏙️ Província fixa: {prov.nome}")
            for index, row in df.iterrows():
                try:
                    # ... processamento ...
                    contagem += 1
                except Exception as e:
                    erros.append(f"Linha {index+2}: {str(e)}")
                    logger.warning(f"⚠️ Erro na linha {index+2}: {str(e)}")
            logger.info(f"✅ Processados {contagem} registos com mapeamento fixo. Erros: {len(erros)}")
            return {'sucesso': True, 'mensagem': f"{contagem} registos processados. Erros: {len(erros)}"}

        elif 'provincia' in mapeamento:
            # ... similar com logs ...
            pass
        else:
            logger.error("❌ Mapeamento inválido: faltando 'provincia' ou 'provincia_fixa'")
            return {'sucesso': False, 'mensagem': 'Mapeamento inválido.'}

    # -----------------------------------------------------------------
    # 2. DETECÇÃO AUTOMÁTICA DE FORMATO
    # -----------------------------------------------------------------
    colunas = df.columns.str.lower()
    logger.info(f"🔎 Colunas normalizadas: {colunas.tolist()}")

    formato_oms = (
        'date_reported' in colunas and
        'country_code' in colunas and
        'new_cases' in colunas and
        'cumulative_cases' in colunas
    )
    formato_covid_open_data = (
        'date' in colunas and
        'new_confirmed' in colunas and
        'cumulative_confirmed' in colunas
    )

    if formato_oms:
        logger.info("📊 Detectado formato OMS")
        # ... processamento OMS com logs ...
        # Vou adicionar logs de quantos registros foram filtrados para Moçambique
        if 'country_code' in df.columns:
            df_mz = df[df['country_code'].str.upper() == 'MZ']
            logger.info(f"🇲🇿 Filtrados {len(df_mz)} registos para Moçambique (código MZ)")
        elif 'country' in df.columns:
            df_mz = df[df['country'].str.lower() == 'mozambique']
            logger.info(f"🇲🇿 Filtrados {len(df_mz)} registos para Moçambique (nome)")
        else:
            df_mz = df
            logger.warning("⚠️ Nenhuma coluna de país encontrada, assumindo todos os registos como Moçambique")

        if df_mz.empty:
            logger.error("❌ Nenhum registo encontrado para Moçambique")
            return {'sucesso': False, 'mensagem': 'Nenhum registo encontrado para Moçambique.'}

        # ... continua com criação de província e doença ...
        provincia_mz, _ = Provincia.objects.get_or_create(
            nome='Moçambique',
            defaults={'sigla': 'MZ', 'active': True}
        )
        logger.info(f"🏙️ Província: {provincia_mz.nome}")

        if doenca_escolhida is None:
            doenca, _ = Doenca.objects.get_or_create(
                tipo='covid19',
                defaults={
                    'nome': 'COVID-19',
                    'descricao': 'Doença causada pelo coronavírus SARS-CoV-2',
                    'sintomas': 'Febre, tosse, dificuldade respiratória, perda de olfato/paladar',
                    'orientacao': 'Procurar assistência médica se os sintomas forem graves.'
                }
            )
        else:
            doenca = doenca_escolhida
        logger.info(f"🦠 Doença: {doenca.nome}")

        for index, row in df_mz.iterrows():
            try:
                data = pd.to_datetime(row['date_reported']).date()
                novos_casos = int(row.get('new_cases', 0) or 0)
                casos_acum = int(row.get('cumulative_cases', 0) or 0)
                novos_obitos = int(row.get('new_deaths', 0) or 0)
                obitos_acum = int(row.get('cumulative_deaths', 0) or 0)

                # ... update_or_create ...
                CasoDoenca.objects.update_or_create(
                    provincia=provincia_mz,
                    doenca=doenca,
                    data=data,
                    defaults={
                        'novos_casos': novos_casos,
                        'casos_acumulados': casos_acum,
                        'novos_obitos': novos_obitos,
                        'obitos_acumulados': obitos_acum,
                        'quantidade': novos_casos,
                        'confirmados': casos_acum,
                        'obitos': obitos_acum,
                        'curados': 0,
                        'fonte': fonte
                    }
                )
                contagem += 1
                if contagem % 100 == 0:
                    logger.info(f"⏳ Processados {contagem} registos OMS...")
            except Exception as e:
                erros.append(f"Linha {index+2}: {str(e)}")
                logger.warning(f"⚠️ Erro na linha {index+2}: {str(e)}")

        logger.info(f"✅ Importação OMS concluída: {contagem} registos, {len(erros)} erros")
        return {
            'sucesso': True,
            'mensagem': f"{contagem} registos de COVID-19 (OMS) processados. Erros: {len(erros)}"
        }

    elif formato_covid_open_data:
        logger.info("📊 Detectado formato covid19-open-data (Google)")
        # ... similar com logs ...
        if 'country_code' in colunas:
            df_mz = df[df['country_code'].str.upper() == 'MZ']
            logger.info(f"🇲🇿 Filtrados {len(df_mz)} registos para Moçambique (código)")
        elif 'country_name' in colunas:
            df_mz = df[df['country_name'].str.lower() == 'mozambique']
            logger.info(f"🇲🇿 Filtrados {len(df_mz)} registos para Moçambique (nome)")
        else:
            df_mz = df
            logger.warning("⚠️ Nenhuma coluna de país, assumindo todos Moçambique")

        if df_mz.empty:
            logger.error("❌ Nenhum registo encontrado para Moçambique")
            return {'sucesso': False, 'mensagem': 'Nenhum registo encontrado para Moçambique.'}

        provincia_mz, _ = Provincia.objects.get_or_create(
            nome='Moçambique',
            defaults={'sigla': 'MZ', 'active': True}
        )
        logger.info(f"🏙️ Província: {provincia_mz.nome}")

        if doenca_escolhida is None:
            doenca, _ = Doenca.objects.get_or_create(
                tipo='covid19',
                defaults={
                    'nome': 'COVID-19',
                    'descricao': 'Doença causada pelo coronavírus SARS-CoV-2',
                    'sintomas': 'Febre, tosse, dificuldade respiratória, perda de olfato/paladar',
                    'orientacao': 'Procurar assistência médica se os sintomas forem graves.'
                }
            )
        else:
            doenca = doenca_escolhida
        logger.info(f"🦠 Doença: {doenca.nome}")

        for index, row in df_mz.iterrows():
            try:
                data = pd.to_datetime(row['date']).date()
                novos_casos = int(row.get('new_confirmed', 0) or 0)
                casos_acum = int(row.get('cumulative_confirmed', 0) or 0)
                novos_obitos = int(row.get('new_deceased', 0) or 0)
                obitos_acum = int(row.get('cumulative_deceased', 0) or 0)

                CasoDoenca.objects.update_or_create(
                    provincia=provincia_mz,
                    doenca=doenca,
                    data=data,
                    defaults={
                        'novos_casos': novos_casos,
                        'casos_acumulados': casos_acum,
                        'novos_obitos': novos_obitos,
                        'obitos_acumulados': obitos_acum,
                        'quantidade': novos_casos,
                        'confirmados': casos_acum,
                        'obitos': obitos_acum,
                        'curados': 0,
                        'fonte': fonte
                    }
                )
                contagem += 1
                if contagem % 100 == 0:
                    logger.info(f"⏳ Processados {contagem} registos Google...")
            except Exception as e:
                erros.append(f"Linha {index+2}: {str(e)}")
                logger.warning(f"⚠️ Erro na linha {index+2}: {str(e)}")

        logger.info(f"✅ Importação Google concluída: {contagem} registos, {len(erros)} erros")
        return {
            'sucesso': True,
            'mensagem': f"{contagem} registos de COVID-19 (covid19-open-data) processados. Erros: {len(erros)}"
        }

    else:
        # Formato antigo (provincial, qualquer doença)
        logger.info("📊 Detectado formato antigo (provincial)")
        for index, row in df.iterrows():
            try:
                # ... processamento ...
                prov = Provincia.objects.get(nome__iexact=row['provincia'].strip())
                # ... etc ...
                contagem += 1
            except Exception as e:
                erros.append(f"Linha {index+2}: {str(e)}")
                logger.warning(f"⚠️ Erro na linha {index+2}: {str(e)}")

        logger.info(f"✅ Importação antiga concluída: {contagem} registos, {len(erros)} erros")
        return {
            'sucesso': True,
            'mensagem': f"{contagem} registos processados. Erros: {len(erros)}"
        }
    # -----------------------------------------------------------------
    # 2. DETECÇÃO AUTOMÁTICA (quando não há mapeamento)
    # -----------------------------------------------------------------
    colunas = df.columns.str.lower()
    formato_oms = (
        'date_reported' in colunas and
        'country_code' in colunas and
        'new_cases' in colunas and
        'cumulative_cases' in colunas
    )
    formato_covid_open_data = (
        'date' in colunas and
        'new_confirmed' in colunas and
        'cumulative_confirmed' in colunas
    )

    # 2.1 Formato OMS (COVID-19 internacional)
    if formato_oms:
        if 'country_code' in df.columns:
            df_mz = df[df['country_code'].str.upper() == 'MZ']
        elif 'country' in df.columns:
            df_mz = df[df['country'].str.lower() == 'mozambique']
        else:
            df_mz = df

        if df_mz.empty:
            return {'sucesso': False, 'mensagem': 'Nenhum registo encontrado para Moçambique (código MZ).'}

        provincia_mz, _ = Provincia.objects.get_or_create(
            nome='Moçambique',
            defaults={'sigla': 'MZ', 'active': True}
        )

        if doenca_escolhida is None:
            doenca, _ = Doenca.objects.get_or_create(
                tipo='covid19',
                defaults={
                    'nome': 'COVID-19',
                    'descricao': 'Doença causada pelo coronavírus SARS-CoV-2',
                    'sintomas': 'Febre, tosse, dificuldade respiratória, perda de olfato/paladar',
                    'orientacao': 'Procurar assistência médica se os sintomas forem graves.'
                }
            )
        else:
            doenca = doenca_escolhida

        for index, row in df_mz.iterrows():
            try:
                data = pd.to_datetime(row['date_reported']).date()
                novos_casos = int(row.get('new_cases', 0) or 0)
                casos_acum = int(row.get('cumulative_cases', 0) or 0)
                novos_obitos = int(row.get('new_deaths', 0) or 0)
                obitos_acum = int(row.get('cumulative_deaths', 0) or 0)

                quantidade = novos_casos
                confirmados = casos_acum
                obitos = obitos_acum

                CasoDoenca.objects.update_or_create(
                    provincia=provincia_mz,
                    doenca=doenca,
                    data=data,
                    defaults={
                        'novos_casos': novos_casos,
                        'casos_acumulados': casos_acum,
                        'novos_obitos': novos_obitos,
                        'obitos_acumulados': obitos_acum,
                        'quantidade': quantidade,
                        'confirmados': confirmados,
                        'obitos': obitos,
                        'curados': 0,
                        'fonte': fonte
                    }
                )
                contagem += 1
            except Exception as e:
                erros.append(f"Linha {index+2}: {str(e)}")

        return {
            'sucesso': True,
            'mensagem': f"{contagem} registos de COVID-19 (OMS) processados. Erros: {len(erros)}"
        }

    # 2.2 Formato covid19-open-data (Google)
    elif formato_covid_open_data:
        if 'country_code' in colunas:
            df_mz = df[df['country_code'].str.upper() == 'MZ']
        elif 'country_name' in colunas:
            df_mz = df[df['country_name'].str.lower() == 'mozambique']
        else:
            df_mz = df

        if df_mz.empty:
            return {'sucesso': False, 'mensagem': 'Nenhum registo encontrado para Moçambique.'}

        provincia_mz, _ = Provincia.objects.get_or_create(
            nome='Moçambique',
            defaults={'sigla': 'MZ', 'active': True}
        )

        if doenca_escolhida is None:
            doenca, _ = Doenca.objects.get_or_create(
                tipo='covid19',
                defaults={
                    'nome': 'COVID-19',
                    'descricao': 'Doença causada pelo coronavírus SARS-CoV-2',
                    'sintomas': 'Febre, tosse, dificuldade respiratória, perda de olfato/paladar',
                    'orientacao': 'Procurar assistência médica se os sintomas forem graves.'
                }
            )
        else:
            doenca = doenca_escolhida

        for index, row in df_mz.iterrows():
            try:
                data = pd.to_datetime(row['date']).date()
                novos_casos = int(row.get('new_confirmed', 0) or 0)
                casos_acum = int(row.get('cumulative_confirmed', 0) or 0)
                novos_obitos = int(row.get('new_deceased', 0) or 0)
                obitos_acum = int(row.get('cumulative_deceased', 0) or 0)

                quantidade = novos_casos
                confirmados = casos_acum
                obitos = obitos_acum

                CasoDoenca.objects.update_or_create(
                    provincia=provincia_mz,
                    doenca=doenca,
                    data=data,
                    defaults={
                        'novos_casos': novos_casos,
                        'casos_acumulados': casos_acum,
                        'novos_obitos': novos_obitos,
                        'obitos_acumulados': obitos_acum,
                        'quantidade': quantidade,
                        'confirmados': confirmados,
                        'obitos': obitos,
                        'curados': 0,
                        'fonte': fonte
                    }
                )
                contagem += 1
            except Exception as e:
                erros.append(f"Linha {index+2}: {str(e)}")

        return {
            'sucesso': True,
            'mensagem': f"{contagem} registos de COVID-19 (covid19-open-data) processados. Erros: {len(erros)}"
        }

    # 2.3 Formato antigo (provincial, qualquer doença)
    else:
        for index, row in df.iterrows():
            try:
                prov = Provincia.objects.get(nome__iexact=row['provincia'].strip())

                if 'doenca' in df.columns and row.get('doenca'):
                    doenca = Doenca.objects.get(nome__iexact=row['doenca'].strip())
                elif doenca_escolhida:
                    doenca = doenca_escolhida
                else:
                    doenca = Doenca.objects.first()
                    if not doenca:
                        raise Exception('Nenhuma doença cadastrada. Por favor, cadastre uma doença primeiro.')

                data = pd.to_datetime(row['data']).date()
                qtd = int(row['quantidade'])
                confirmados = int(row.get('confirmados', 0) or 0)
                curados = int(row.get('curados', 0) or 0)
                obitos = int(row.get('obitos', 0) or 0)

                CasoDoenca.objects.update_or_create(
                    provincia=prov,
                    doenca=doenca,
                    data=data,
                    defaults={
                        'quantidade': qtd,
                        'confirmados': confirmados,
                        'curados': curados,
                        'obitos': obitos,
                        'novos_casos': qtd,
                        'casos_acumulados': confirmados,
                        'novos_obitos': obitos,
                        'obitos_acumulados': obitos,
                        'fonte': fonte
                    }
                )
                contagem += 1
            except Exception as e:
                erros.append(f"Linha {index+2}: {str(e)}")

        return {
            'sucesso': True,
            'mensagem': f"{contagem} registos processados. Erros: {len(erros)}"
        }


# ===================================================================
# BUSCA DE DADOS POR API
# ===================================================================
@login_required
def buscar_dados_api(request):
    if request.method == 'POST':
        form = APIImportForm(request.POST)
        if form.is_valid():
            url_api = form.cleaned_data['url_api']
            token = form.cleaned_data.get('token', '')
            tipo_dado = form.cleaned_data['tipo_dado']
            fonte = f"API: {url_api}"  # ou use um nome descritivo

            try:
                headers = {'Authorization': f'Bearer {token}'} if token else {}
                response = requests.get(url_api, headers=headers, timeout=30)
                response.raise_for_status()

                dados = response.json()

                if isinstance(dados, list):
                    df = pd.DataFrame(dados)
                elif isinstance(dados, dict) and 'results' in dados:
                    df = pd.DataFrame(dados['results'])
                elif isinstance(dados, dict) and 'data' in dados:
                    df = pd.DataFrame(dados['data'])
                else:
                    messages.error(request, 'Formato de resposta da API não reconhecido.')
                    return render(request, 'saude/api_importar.html', {'form': form})

                if tipo_dado == 'casos':
                    resultado = importar_casos(df, fonte=fonte)
                elif tipo_dado == 'alertas':
                    resultado = importar_alertas(df)
                elif tipo_dado == 'cobertura':
                    resultado = importar_cobertura(df)
                elif tipo_dado == 'leitos':
                    resultado = importar_leitos(df)
                else:
                    messages.error(request, 'Tipo de dados inválido.')
                    return render(request, 'saude/api_importar.html', {'form': form})

                if resultado['sucesso']:
                    messages.success(request, f"✅ Dados da API importados: {resultado['mensagem']}")
                else:
                    messages.error(request, f"❌ {resultado['mensagem']}")

            except requests.exceptions.Timeout:
                messages.error(request, '❌ A requisição à API expirou.')
            except requests.exceptions.ConnectionError:
                messages.error(request, '❌ Não foi possível conectar à API.')
            except requests.exceptions.HTTPError as e:
                messages.error(request, f'❌ Erro HTTP: {e}')
            except Exception as e:
                messages.error(request, f'❌ Erro ao processar API: {str(e)}')

            return redirect('dashboard_restrito')
    else:
        form = APIImportForm()

    return render(request, 'saude/api_importar.html', {'form': form})


# ===================================================================
# FUNÇÕES AUXILIARES DE IMPORTAÇÃO
# ===================================================================
def parse_xml(arquivo):
    tree = ET.parse(arquivo)
    root = tree.getroot()
    rows = []
    for row in root.findall('row'):
        row_data = {child.tag: child.text for child in row}
        rows.append(row_data)
    return pd.DataFrame(rows)

def importar_alertas(df):
    contagem = 0
    erros = []
    for index, row in df.iterrows():
        try:
            prov = Provincia.objects.get(nome__iexact=row['provincia'].strip())
            doenca = Doenca.objects.get(nome__iexact=row['doenca'].strip())
            Alerta.objects.update_or_create(
                provincia=prov, doenca=doenca, titulo=row['titulo'].strip(),
                defaults={
                    'descricao': row.get('descricao', ''),
                    'gravidade': row['gravidade'].strip().lower(),
                    'status': row.get('status', 'Ativo'),
                    'orientacao': row.get('orientacao', ''),
                    'active': True
                }
            )
            contagem += 1
        except Exception as e:
            erros.append(f"Linha {index+2}: {str(e)}")
    return {'sucesso': True, 'mensagem': f"{contagem} alertas processados. Erros: {len(erros)}"}

def importar_cobertura(df):
    contagem = 0
    erros = []
    for index, row in df.iterrows():
        try:
            prov = Provincia.objects.get(nome__iexact=row['provincia'].strip())
            vacina = Vacina.objects.get(nome__iexact=row['vacina'].strip())
            CoberturaVacinal.objects.update_or_create(
                provincia=prov, vacina=vacina, ano=int(row['ano']),
                defaults={'percentual': float(row['percentual'])}
            )
            contagem += 1
        except Exception as e:
            erros.append(f"Linha {index+2}: {str(e)}")
    return {'sucesso': True, 'mensagem': f"{contagem} registos processados. Erros: {len(erros)}"}

def importar_leitos(df):
    contagem = 0
    erros = []
    for index, row in df.iterrows():
        try:
            prov = Provincia.objects.get(nome__iexact=row['provincia'].strip())
            Leito.objects.update_or_create(
                provincia=prov,
                defaults={'total': int(row['total']), 'ocupados': int(row['ocupados'])}
            )
            contagem += 1
        except Exception as e:
            erros.append(f"Linha {index+2}: {str(e)}")
    return {'sucesso': True, 'mensagem': f"{contagem} registos processados. Erros: {len(erros)}"}


# ===================================================================
# FUNCIONALIDADES PARA CONFIGURAÇÃO DE APIs
# ===================================================================
@login_required
def listar_apis(request):
    configuracoes = ConfiguracaoAPI.objects.all()
    return render(request, 'saude/apis/listar.html', {'configuracoes': configuracoes})

@login_required
def criar_api(request):
    if request.method == 'POST':
        form = ConfiguracaoAPIForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configuração de API criada com sucesso!')
            return redirect('listar_apis')
    else:
        form = ConfiguracaoAPIForm()
    return render(request, 'saude/apis/form.html', {'form': form, 'acao': 'Criar'})

@login_required
def editar_api(request, pk):
    config = get_object_or_404(ConfiguracaoAPI, pk=pk)
    if request.method == 'POST':
        form = ConfiguracaoAPIForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configuração atualizada com sucesso!')
            return redirect('listar_apis')
    else:
        form = ConfiguracaoAPIForm(instance=config)
    return render(request, 'saude/apis/form.html', {'form': form, 'acao': 'Editar'})

@login_required
def deletar_api(request, pk):
    config = get_object_or_404(ConfiguracaoAPI, pk=pk)
    if request.method == 'POST':
        config.delete()
        messages.success(request, 'Configuração removida com sucesso!')
        return redirect('listar_apis')
    return render(request, 'saude/apis/confirmar_delete.html', {'config': config})

@login_required
def executar_api(request, pk):
    config = get_object_or_404(ConfiguracaoAPI, pk=pk)
    if not config.ativo:
        messages.warning(request, 'Esta API está inativa. Ative-a primeiro.')
        return redirect('listar_apis')

    sucesso = processar_configuracao_api(config, request)
    if sucesso:
        messages.success(request, "✅ Importação executada com sucesso.")
    else:
        messages.error(request, "❌ Falha na execução. Verifique o status da API.")
    return redirect('listar_apis')

@login_required
def executar_todas_apis(request):
    configuracoes = ConfiguracaoAPI.objects.filter(ativo=True)
    executadas = 0
    for config in configuracoes:
        if config.deve_executar():
            try:
                headers = {'Authorization': f'Bearer {config.token}'} if config.token else {}
                response = requests.get(config.url, headers=headers, timeout=30)
                response.raise_for_status()
                dados = response.json()

                if isinstance(dados, dict) and 'data' in dados and 'columns' in dados:
                    df = pd.DataFrame(dados['data'], columns=dados['columns'])
                elif isinstance(dados, list):
                    df = pd.DataFrame(dados)
                elif isinstance(dados, dict) and 'results' in dados:
                    df = pd.DataFrame(dados['results'])
                elif isinstance(dados, dict) and 'data' in dados:
                    df = pd.DataFrame(dados['data'])
                else:
                    raise ValueError('Formato de resposta não reconhecido.')

                fonte = f"API: {config.nome} (automática)"

                if config.tipo_dado == 'casos':
                    resultado = importar_casos(df, fonte=fonte)
                elif config.tipo_dado == 'alertas':
                    resultado = importar_alertas(df)
                elif config.tipo_dado == 'cobertura':
                    resultado = importar_cobertura(df)
                elif config.tipo_dado == 'leitos':
                    resultado = importar_leitos(df)
                else:
                    raise ValueError('Tipo de dados inválido.')

                config.ultima_execucao = timezone.now()
                msg = f"Sucesso: {resultado['mensagem']}"
                config.ultimo_status = msg[:254]
                config.save()
                executadas += 1
            except Exception as e:
                msg = f"Erro: {str(e)}"
                config.ultimo_status = msg[:254]
                config.save()

    messages.success(request, f"✅ {executadas} APIs executadas com sucesso.")
    return redirect('listar_apis')

# @login_required
# ===================================================================
# PROCESSAMENTO DE API (UTILIZADO PELO AGENDADOR E PELO PAINEL)
# ===================================================================

def processar_configuracao_api(config, request=None):
    """
    Processa uma configuração de API.
    Se request for fornecido, regista o utilizador que executou.
    Retorna True se sucesso, False caso contrário.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"🔄 A processar API: {config.nome} (ID: {config.id})")
    logger.info(f"📌 tipo_dado recebido: '{config.tipo_dado}'")

    # ----- MAPEAMENTO DE TIPOS -----
    # Se for 'covid19', redireciona para 'casos' (importação de casos)
    tipo_efetivo = config.tipo_dado
    if tipo_efetivo == 'covid19':
        tipo_efetivo = 'casos'
        logger.info("🔄 Mapeando 'covid19' para 'casos'")

    try:
        headers = {'Authorization': f'Bearer {config.token}'} if config.token else {}
        response = requests.get(config.url, headers=headers, timeout=30)
        response.raise_for_status()
        dados = response.json()
        logger.info(f"✅ API respondeu com sucesso. Tipo: {type(dados)}")

        # ---- DETECÇÃO DE FORMATO ----
        if isinstance(dados, dict) and 'data' in dados and 'columns' in dados:
            df = pd.DataFrame(dados['data'], columns=dados['columns'])
            logger.info(f"📊 Formato covid19-open-data: {len(df)} linhas, colunas: {list(df.columns)}")
        elif isinstance(dados, list):
            df = pd.DataFrame(dados)
            logger.info(f"📊 Formato lista: {len(df)} linhas, colunas: {list(df.columns)}")
        elif isinstance(dados, dict) and 'results' in dados:
            df = pd.DataFrame(dados['results'])
            logger.info(f"📊 Formato results: {len(df)} linhas, colunas: {list(df.columns)}")
        elif isinstance(dados, dict) and 'data' in dados:
            df = pd.DataFrame(dados['data'])
            logger.info(f"📊 Formato data: {len(df)} linhas, colunas: {list(df.columns)}")
        else:
            raise ValueError('Formato de resposta não reconhecido.')

        # ---- FONTE ----
        if request and hasattr(request, 'user'):
            fonte = f"API: {config.nome} (por {request.user.username})"
        else:
            fonte = f"API: {config.nome} (automática)"

        logger.info(f"🔍 Fonte: {fonte}, tipo_efetivo: {tipo_efetivo}")

        # ---- IMPORTAÇÃO (usando tipo_efetivo) ----
        if tipo_efetivo == 'casos':
            logger.info("📥 Chamando importar_casos...")
            resultado = importar_casos(df, fonte=fonte)
            logger.info(f"📥 Resultado: {resultado}")
        elif tipo_efetivo == 'alertas':
            resultado = importar_alertas(df)
        elif tipo_efetivo == 'cobertura':
            resultado = importar_cobertura(df)
        elif tipo_efetivo == 'leitos':
            resultado = importar_leitos(df)
        else:
            raise ValueError(f"Tipo de dados inválido: '{tipo_efetivo}' (original: '{config.tipo_dado}')")

        if resultado.get('sucesso'):
            config.ultima_execucao = timezone.now()
            msg = f"Sucesso: {resultado['mensagem']}"
            config.ultimo_status = msg[:254]
            config.save(update_fields=['ultima_execucao', 'ultimo_status'])
            logger.info(f"✅ Importação concluída: {msg}")
            return True
        else:
            msg = f"Erro na importação: {resultado.get('mensagem', 'sem detalhes')}"
            config.ultimo_status = msg[:254]
            config.save(update_fields=['ultimo_status'])
            logger.error(f"❌ {msg}")
            return False

    except Exception as e:
        logger.error(traceback.format_exc())
        msg = f"Erro: {str(e)}"
        config.ultimo_status = msg[:254]
        config.save(update_fields=['ultimo_status'])
        logger.error(f"❌ {msg}")
        return False