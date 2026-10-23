from django import forms

from .horarios import HORARIOS_CHOICES


class ConsultaDisponibilidadForm(forms.Form):
    fecha = forms.DateField(
        label="Fecha",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-lg"}),
        input_formats=["%Y-%m-%d"],
    )
    hora = forms.TimeField(
        label="Horario",
        input_formats=["%H:%M"],
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

