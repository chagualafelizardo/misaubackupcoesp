from django.db import models

class Provincia(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    sigla = models.CharField(max_length=10, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'provincia'
        ordering = ['nome']
        verbose_name_plural = "Províncias"

    def __str__(self):
        return self.nome

class Doenca(models.Model):
    TIPO_CHOICES = (
        ('malaria', 'Malária'),
        ('colera', 'Cólera'),
        ('dengue', 'Dengue'),
        ('outra', 'Outra'),
    )
    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    descricao = models.TextField(blank=True)
    sintomas = models.TextField(blank=True, help_text="Lista de sintomas principais")
    orientacao = models.TextField(blank=True, help_text="O que fazer")

    class Meta:
        db_table = 'doenca'

    def __str__(self):
        return self.nome

class CasoDoenca(models.Model):
    provincia = models.ForeignKey(Provincia, on_delete=models.CASCADE, related_name='casos')
    doenca = models.ForeignKey(Doenca, on_delete=models.CASCADE, related_name='casos')
    data = models.DateField()
    quantidade = models.PositiveIntegerField()
    confirmados = models.PositiveIntegerField(default=0)
    curados = models.PositiveIntegerField(default=0)          # <-- NOVO
    obitos = models.PositiveIntegerField(default=0)           # <-- NOVO

    class Meta:
        db_table = 'caso_doenca'
        ordering = ['-data']
        unique_together = ('provincia', 'doenca', 'data')

    def __str__(self):
        return f"{self.provincia} - {self.doenca} - {self.data} ({self.quantidade})"

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
    ultimo_status = models.CharField(max_length=50, blank=True, help_text="Status da última execução")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'configuracao_api'
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_dado_display()})"

    def deve_executar(self):
        """Verifica se já passou o intervalo desde a última execução."""
        if not self.ultima_execucao:
            return True
        from django.utils import timezone
        delta = timezone.now() - self.ultima_execucao
        if self.intervalo == '1h':
            return delta.total_seconds() >= 3600
        elif self.intervalo == '6h':
            return delta.total_seconds() >= 21600
        elif self.intervalo == '12h':
            return delta.total_seconds() >= 43200
        elif self.intervalo == '24h':
            return delta.total_seconds() >= 86400
        elif self.intervalo == 'semanal':
            return delta.total_seconds() >= 604800
        return False
    
    def __str__(self):
        return f"{self.provincia}: {self.ocupados}/{self.total} leitos ({self.percentual_ocupacao}%)"