from django import forms
from .models import ConfiguracaoAPI

class UploadDataForm(forms.Form):
    TIPO_CHOICES = (
        ('casos', 'Casos de Doenças'),
        ('alertas', 'Alertas'),
        ('cobertura', 'Cobertura Vacinal'),
        ('leitos', 'Leitos'),
    )
    tipo_dado = forms.ChoiceField(choices=TIPO_CHOICES, label='Tipo de dados')
    arquivo = forms.FileField(label='Ficheiro (XLSX, XLS, CSV, XML)')

class APIImportForm(forms.Form):
    TIPO_CHOICES = (
        ('casos', 'Casos de Doenças'),
        ('alertas', 'Alertas'),
        ('cobertura', 'Cobertura Vacinal'),
        ('leitos', 'Leitos'),
    )
    tipo_dado = forms.ChoiceField(choices=TIPO_CHOICES, label='Tipo de dados')
    url_api = forms.URLField(label='URL da API', help_text='Exemplo: https://api.exemplo.com/dados')
    token = forms.CharField(label='Token (opcional)', required=False, widget=forms.TextInput(attrs={'placeholder': 'Bearer token'}))

class ConfiguracaoAPIForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoAPI
        fields = ['nome', 'url', 'token', 'tipo_dado', 'intervalo', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Dados COVID-19'}),
            'url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://api.exemplo.com/dados'}),
            'token': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bearer token (opcional)'}),
            'tipo_dado': forms.Select(attrs={'class': 'form-control'}),
            'intervalo': forms.Select(attrs={'class': 'form-control'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }