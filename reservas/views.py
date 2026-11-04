from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.utils import timezone

from .exceptions import ConflictoReserva, SinDisponibilidad
from .forms import ConsultaDisponibilidadForm, DatosReservaForm
from .models import Mesa
from .services import consultar_mesas_disponibles
from .services import registrar_reserva


def inicio(request):
    mesas = []
    consultado = False
    reserva_form = None
    reserva_creada = None
    mesa_seleccionada = None
    form = ConsultaDisponibilidadForm(request.POST or None)
    fecha_minima = timezone.localdate().isoformat()
    form.fields["fecha"].widget.attrs["min"] = fecha_minima

    if request.method == "POST" and request.POST.get("accion") == "reservar":
        reserva_form = DatosReservaForm(request.POST)
        if reserva_form.is_valid():
            mesa_seleccionada = Mesa.objects.filter(pk=reserva_form.cleaned_data["mesa_id"]).first()
            try:
                reserva_creada = registrar_reserva(**reserva_form.cleaned_data)
            except (ConflictoReserva, SinDisponibilidad) as error:
                reserva_form.add_error(None, str(error))
            except ValidationError as error:
                if hasattr(error, "error_dict"):
                    for campo, errores in error.error_dict.items():
                        reserva_form.add_error(campo if campo in reserva_form.fields else None, errores)
                else:
                    reserva_form.add_error(None, error)
    elif request.method == "POST" and request.POST.get("accion") == "elegir":
        if form.is_valid():
            consultado = True
            try:
                mesas = consultar_mesas_disponibles(**form.cleaned_data)
                mesa_id = request.POST.get("mesa_id")
                if not any(str(mesa.pk) == mesa_id for mesa in mesas):
                    form.add_error(None, "La mesa seleccionada ya no está disponible. Consulta nuevamente.")
                else:
                    mesa_seleccionada = next(mesa for mesa in mesas if str(mesa.pk) == mesa_id)
                    reserva_form = DatosReservaForm(initial={
                        **form.cleaned_data,
                        "mesa_id": mesa_id,
                    })
            except ValidationError as error:
                form.add_error(None, error)
    elif request.method == "POST" and form.is_valid():
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
        "reserva_form": reserva_form,
        "reserva_creada": reserva_creada,
        "mesa_seleccionada": mesa_seleccionada,
    })
