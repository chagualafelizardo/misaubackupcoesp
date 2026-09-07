from django.db import models
from django.utils import timezone


# ===================================================================
# PROVÍNCIA
# ===================================================================

class Provincia(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    sigla = models.CharField(max_length=10, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'provincia'
        ordering = ['nome']
        verbose_name = 'Província'
        verbose_name_plural = 'Províncias'

    def __str__(self):
        return self.nome


# ===================================================================
# DOENÇA
# ===================================================================

class Doenca(models.Model):
    TIPO_CHOICES = (
        ('malaria', 'Malária'),
        ('colera', 'Cólera'),
        ('covid19', 'COVID-19'),
        ('outra', 'Outra'),
    )

    nome = models.CharField(max_length=100, unique=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    descricao = models.TextField(blank=True)
    sintomas = models.TextField(blank=True, help_text="Lista de sintomas principais")
    orientacao = models.TextField(blank=True, help_text="O que fazer")

    class Meta:
        db_table = 'doenca'
        verbose_name = 'Doença'
        verbose_name_plural = 'Doenças'

    def __str__(self):
        return self.nome


# ===================================================================
# CASO DE DOENÇA (modelo epidemiológico geral)
# ===================================================================

class CasoDoenca(models.Model):
    """
    Registo epidemiológico que serve para qualquer doença.
    Inclui campos para séries temporais (novos e acumulados),
    mantendo compatibilidade com a estrutura anterior.
    """
    provincia = models.ForeignKey(Provincia, on_delete=models.CASCADE, related_name='casos')
    doenca = models.ForeignKey(Doenca, on_delete=models.CASCADE, related_name='casos')

    data = models.DateField(db_index=True)

    # ----- Novos campos gerais (para todas as doenças) -----
    novos_casos = models.PositiveIntegerField(default=0, help_text="Novos casos no período")
    casos_acumulados = models.PositiveIntegerField(default=0, help_text="Total acumulado desde o início")
    novos_obitos = models.PositiveIntegerField(default=0, help_text="Novos óbitos no período")
    obitos_acumulados = models.PositiveIntegerField(default=0, help_text="Total de óbitos acumulados")

    # ----- Campos herdados (para não quebrar o sistema atual) -----
    quantidade = models.PositiveIntegerField(default=0)      # equivalente a novos_casos
    confirmados = models.PositiveIntegerField(default=0)     # pode representar casos acumulados
    curados = models.PositiveIntegerField(default=0)         # recuperados (futuramente)
    obitos = models.PositiveIntegerField(default=0)          # óbitos totais (redundante com obitos_acumulados)

    # ----- Origem dos dados -----
    fonte = models.CharField(max_length=100, default='manual', help_text="Fonte dos dados (ex: WHO, MISAU, CSV)")

    class Meta:
        db_table = 'caso_doenca'
        ordering = ['-data']
        unique_together = ('provincia', 'doenca', 'data')
        indexes = [
            models.Index(fields=['doenca', 'data']),
            models.Index(fields=['provincia', 'data']),
        ]

    def __str__(self):
        return f"{self.provincia} - {self.doenca} - {self.data} (novos: {self.novos_casos}, acum: {self.casos_acumulados})"


# ===================================================================
# ALERTA
# ===================================================================

class Alerta(models.Model):
    GRAVIDADE_CHOICES = (
        ('critico', 'Crítico'),
        ('atencao', 'Atenção'),
        ('informacao', 'Informação'),
    )

    provincia = models.ForeignKey(Provincia, on_delete=models.CASCADE, related_name='alertas')
    doenca = models.ForeignKey(Doenca, on_delete=models.CASCADE, related_name='alertas')
    titulo = models.CharField(max_length=200)
    descricao = models.TextField()
    gravidade = models.CharField(max_length=20, choices=GRAVIDADE_CHOICES)
    status = models.CharField(max_length=50, default='Ativo')
    orientacao = models.TextField(blank=True, help_text="Recomendações ou link")
    data_inicio = models.DateField(auto_now_add=True)
    data_fim = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'alerta'
        ordering = ['-gravidade', '-data_inicio']

    def __str__(self):
        return f"{self.get_gravidade_display()}: {self.titulo} ({self.provincia})"


# ===================================================================
# VACINA
# ===================================================================

class Vacina(models.Model):
    nome = models.CharField(max_length=100)
    descricao = models.TextField()
    doses_recomendadas = models.PositiveIntegerField()
    idade_minima = models.PositiveIntegerField(help_text="Idade mínima em meses", default=0)
    idade_maxima = models.PositiveIntegerField(help_text="Idade máxima em meses", null=True, blank=True)

    class Meta:
        db_table = 'vacina'

    def __str__(self):
        return self.nome


# ===================================================================
# COBERTURA VACINAL
# ===================================================================

class CoberturaVacinal(models.Model):
    provincia = models.ForeignKey(Provincia, on_delete=models.CASCADE, related_name='coberturas')
    vacina = models.ForeignKey(Vacina, on_delete=models.CASCADE, related_name='coberturas')
    ano = models.PositiveIntegerField()
    percentual = models.DecimalField(max_digits=5, decimal_places=2)
    meta = models.DecimalField(max_digits=5, decimal_places=2, default=90.00)

    class Meta:
        db_table = 'cobertura_vacinal'
        unique_together = ('provincia', 'vacina', 'ano')
        ordering = ['-ano']

    def __str__(self):
        return f"{self.provincia} - {self.vacina} ({self.ano}): {self.percentual}%"


# ===================================================================
# LEITO
# ===================================================================

class Leito(models.Model):
    provincia = models.ForeignKey(Provincia, on_delete=models.CASCADE, related_name='leitos')
    total = models.PositiveIntegerField()
    ocupados = models.PositiveIntegerField()
    data_atualizacao = models.DateField(auto_now=True)

    class Meta:
        db_table = 'leito'

    @property
    def percentual_ocupacao(self):
        if self.total > 0:
            return round((self.ocupados / self.total) * 100, 1)
        return 0.0

    def __str__(self):
        return f"{self.provincia}: {self.ocupados}/{self.total} leitos ({self.percentual_ocupacao}%)"


# ===================================================================
# CONFIGURAÇÃO DE API
# ===================================================================

class ConfiguracaoAPI(models.Model):
    INTERVALO_CHOICES = (
        ('1h', 'A cada 1 hora'),
        ('6h', 'A cada 6 horas'),
        ('12h', 'A cada 12 horas'),
        ('24h', 'Diariamente'),
        ('semanal', 'Semanalmente'),
    )
    TIPO_CHOICES = (
        ('casos', 'Casos de Doenças'),
        ('covid19', 'COVID-19'),
        ('alertas', 'Alertas'),
        ('cobertura', 'Cobertura Vacinal'),
        ('leitos', 'Leitos'),
    )

    nome = models.CharField(max_length=100, help_text="Nome descritivo para identificação")
    url = models.URLField(help_text="URL da API que retorna dados em JSON")
    token = models.CharField(max_length=255, blank=True, help_text="Token de autenticação (Bearer)")
    tipo_dado = models.CharField(max_length=20, choices=TIPO_CHOICES)
    intervalo = models.CharField(max_length=10, choices=INTERVALO_CHOICES, default='24h')
    ativo = models.BooleanField(default=True)
    ultima_execucao = models.DateTimeField(null=True, blank=True)
    ultimo_status = models.CharField(max_length=500, blank=True, help_text="Status da última execução")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    # ===== NOVO CAMPO =====
    # Aqui devemos personalizar os campos que devem ser captados por cada doenca, seja por APi/JSON ou por importacao de .excel, .csv, .xml
    mapeamento = models.JSONField(
        default=dict,
        blank=True,
        help_text='Mapeamento personalizado: {"data": "coluna_data", "novos_casos": "coluna_novos"}'
    )

    class Meta:
        db_table = 'configuracao_api'
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_dado_display()})"

    def deve_executar(self):
        """Verifica se já passou o intervalo desde a última execução."""
        if not self.ultima_execucao:
            return True

        delta = timezone.now() - self.ultima_execucao
        intervalos = {
            '1h': 3600,
            '6h': 21600,
            '12h': 43200,
            '24h': 86400,
            'semanal': 604800,
        }
        segundos = intervalos.get(self.intervalo)
        if segundos is None:
            return False
        return delta.total_seconds() >= segundos

class DadosClima(models.Model):
    provincia = models.ForeignKey(Provincia, on_delete=models.CASCADE, related_name='clima')
    data = models.DateField(db_index=True)
    temperatura_max = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    temperatura_min = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    precipitacao = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Precipitação em mm")
    umidade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Umidade relativa %")
    vento_velocidade = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="Velocidade do vento (km/h ou m/s)")
    tempestade = models.BooleanField(default=False, help_text="Indica se há previsão de tempestade")
    descricao = models.CharField(max_length=200, blank=True, help_text="Descrição do tempo (ex: 'Céu limpo', 'Chuva forte')")
    fonte = models.CharField(max_length=100, default='API')

    class Meta:
        db_table = 'dados_clima'
        ordering = ['-data']
        unique_together = ('provincia', 'data')

    def __str__(self):
        return f"{self.provincia} - {self.data} - Temp: {self.temperatura_max}°C"
    