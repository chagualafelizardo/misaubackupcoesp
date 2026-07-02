import pandas as pd
import xml.etree.ElementTree as ET
import requests
from django.utils import timezone
from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.db.models import Sum, Avg, Max
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Provincia, Doenca, CasoDoenca, Alerta, CoberturaVacinal, Vacina, Leito
from .forms import UploadDataForm, APIImportForm
from .models import ConfiguracaoAPI
from .forms import ConfiguracaoAPIForm


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
        'hoje': hoje,
        'ano_atual': hoje.year,
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

            try:
                if extensao in ['xlsx', 'xls']:
                    df = pd.read_excel(arquivo)
                elif extensao == 'csv':
                    df = pd.read_csv(arquivo)
                elif extensao == 'xml':
                    df = parse_xml(arquivo)
                else:
                    messages.error(request, 'Formato não suportado. Use .xlsx, .xls, .csv ou .xml.')
                    return render(request, 'saude/importar.html', {'form': form})

                if tipo == 'casos':
                    resultado = importar_casos(df)
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

            except Exception as e:
                messages.error(request, f"❌ Erro ao processar ficheiro: {str(e)}")

            return redirect('dashboard_restrito')
    else:
        form = UploadDataForm()

    return render(request, 'saude/importar.html', {'form': form})


@login_required
def buscar_dados_api(request):
    if request.method == 'POST':
        form = APIImportForm(request.POST)
        if form.is_valid():
            url_api = form.cleaned_data['url_api']
            token = form.cleaned_data.get('token', '')
            tipo_dado = form.cleaned_data['tipo_dado']

            try:
                headers = {'Authorization': f'Bearer {token}'} if token else {}
                response = requests.get(url_api, headers=headers, timeout=30)
                response.raise_for_status()

                dados = response.json()

                # Normaliza a resposta para uma lista de dicionários
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
                    resultado = importar_casos(df)
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

def importar_casos(df):
    contagem = 0
    erros = []
    for index, row in df.iterrows():
        try:
            prov = Provincia.objects.get(nome__iexact=row['provincia'].strip())
            doenca = Doenca.objects.get(nome__iexact=row['doenca'].strip())
            data = pd.to_datetime(row['data']).date()
            qtd = int(row['quantidade'])
            confirmados = int(row.get('confirmados', 0))
            CasoDoenca.objects.update_or_create(
                provincia=prov, doenca=doenca, data=data,
                defaults={'quantidade': qtd, 'confirmados': confirmados}
            )
            contagem += 1
        except Exception as e:
            erros.append(f"Linha {index+2}: {str(e)}")
    return {'sucesso': True, 'mensagem': f"{contagem} registos processados. Erros: {len(erros)}"}

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

# Funcionalidades para configuração de APIs para o consumo de dados pelo COESP
@login_required
def listar_apis(request):
    """Lista todas as configurações de API."""
    configuracoes = ConfiguracaoAPI.objects.all()
    return render(request, 'saude/apis/listar.html', {'configuracoes': configuracoes})

@login_required
def criar_api(request):
    """Cria uma nova configuração de API."""
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
    """Edita uma configuração existente."""
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
    """Remove uma configuração."""
    config = get_object_or_404(ConfiguracaoAPI, pk=pk)
    if request.method == 'POST':
        config.delete()
        messages.success(request, 'Configuração removida com sucesso!')
        return redirect('listar_apis')
    return render(request, 'saude/apis/confirmar_delete.html', {'config': config})

@login_required
def executar_api(request, pk):
    """Executa manualmente uma importação a partir de uma configuração."""
    config = get_object_or_404(ConfiguracaoAPI, pk=pk)
    if not config.ativo:
        messages.warning(request, 'Esta API está inativa. Ative-a primeiro.')
        return redirect('listar_apis')

    try:
        # Usa a função de importação já existente
        headers = {'Authorization': f'Bearer {config.token}'} if config.token else {}
        response = requests.get(config.url, headers=headers, timeout=30)
        response.raise_for_status()
        dados = response.json()

        # Converte para DataFrame e importa
        if isinstance(dados, list):
            df = pd.DataFrame(dados)
        elif isinstance(dados, dict) and 'results' in dados:
            df = pd.DataFrame(dados['results'])
        elif isinstance(dados, dict) and 'data' in dados:
            df = pd.DataFrame(dados['data'])
        else:
            raise ValueError('Formato de resposta não reconhecido.')

        # Importa conforme tipo
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
        messages.success(request, f"✅ Importação executada: {resultado['mensagem']}")

    except Exception as e:
        config.ultimo_status = f"Erro: {str(e)}"
        config.save()
        messages.error(request, f"❌ Erro na execução: {str(e)}")

    return redirect('listar_apis')

@login_required
def executar_todas_apis(request):
    """Executa todas as APIs ativas que precisam ser atualizadas."""
    configuracoes = ConfiguracaoAPI.objects.filter(ativo=True)
    executadas = 0
    for config in configuracoes:
        if config.deve_executar():
            # Reutiliza a lógica de execução (pode ser melhor extrair para uma função)
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

    messages.success(request, f"✅ {executadas} APIs executadas com sucesso.")
    return redirect('listar_apis')