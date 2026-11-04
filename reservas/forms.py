from django import forms

from .horarios import HORARIOS_CHOICES
from .validators import normalizar_telefono


class ConsultaDisponibilidadForm(forms.Form):
    fecha = forms.DateField(
        label="Fecha",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-lg"}),
        input_formats=["%Y-%m-%d"],
    )
    hora = forms.TimeField(
        label="Horario",
        input_formats=["%H:%M", "%H:%M:%S"],
        widget=forms.Select(attrs={"class": "form-select form-select-lg"}),
    )
    cantidad_personas = forms.IntegerField(
        label="Personas",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-lg", "min": 1, "max": 20}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["hora"].widget.choices = [
            ("", "Selecciona un horario"),
            *((hora.strftime("%H:%M"), etiqueta) for hora, etiqueta in HORARIOS_CHOICES),
        ]


class DatosReservaForm(forms.Form):
    nombre = forms.CharField(
        label="Nombre", max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "name", "autofocus": True}),
    )
    telefono = forms.CharField(
        label="Teléfono", strip=False,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "tel"}),
    )
    correo = forms.EmailField(
        label="Correo electrónico", required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
    )
    fecha = forms.DateField(widget=forms.HiddenInput(), input_formats=["%Y-%m-%d"])
    hora = forms.TimeField(widget=forms.HiddenInput(), input_formats=["%H:%M", "%H:%M:%S"])
    cantidad_personas = forms.IntegerField(widget=forms.HiddenInput(), min_value=1)
    mesa_id = forms.IntegerField(widget=forms.HiddenInput(), min_value=1)

    def clean_telefono(self):
        return normalizar_telefono(self.cleaned_data["telefono"])

