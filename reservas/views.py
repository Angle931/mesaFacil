from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.utils import timezone

from .forms import ConsultaDisponibilidadForm
from .services import consultar_mesas_disponibles


def inicio(request):
    mesas = []
    consultado = False
    form = ConsultaDisponibilidadForm(request.POST or None)
    fecha_minima = timezone.localdate().isoformat()
    form.fields["fecha"].widget.attrs["min"] = fecha_minima

    if request.method == "POST" and form.is_valid():
        consultado = True
        try:
            mesas = consultar_mesas_disponibles(**form.cleaned_data)
        except ValidationError as error:
            if hasattr(error, "error_dict"):
                for campo, errores in error.error_dict.items():
                    if campo in form.fields:
                        for detalle in errores:
                            form.add_error(campo, detalle)
                    else:
                        form.add_error(None, error)
            else:
                form.add_error(None, error)

    return render(request, "reservas/inicio.html", {
        "form": form,
        "mesas": mesas,
        "consultado": consultado,
        "fecha_minima": fecha_minima,
    })
