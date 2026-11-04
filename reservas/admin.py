from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Cliente, Mesa, Reserva
from .services import cambiar_estado_reserva, modificar_reserva
from .validators import normalizar_telefono


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ("numero", "capacidad", "activa")
    list_filter = ("activa",)
    ordering = ("numero",)

    def has_delete_permission(self, request, obj=None):
        return False


class ClienteAdminForm(forms.ModelForm):
    telefono = forms.CharField(label="Teléfono", strip=False)

    class Meta:
        model = Cliente
        fields = ("nombre", "telefono", "correo")

    def clean_telefono(self):
        return normalizar_telefono(self.cleaned_data["telefono"])


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    form = ClienteAdminForm
    list_display = ("nombre", "telefono")
    search_fields = ("nombre", "telefono")
    ordering = ("nombre", "id")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ("codigo_confirmacion", "fecha", "hora", "mesa", "cantidad_personas", "estado")
    list_filter = ("fecha", "hora", "estado")
    search_fields = ("=codigo_confirmacion",)
    ordering = ("-fecha", "hora")
    list_select_related = ("mesa", "cliente")
    readonly_fields = ("codigo_confirmacion",)
    fields = (
        "codigo_confirmacion", "nombre_cliente", "telefono_cliente", "correo_cliente",
        "fecha", "hora", "cantidad_personas", "mesa", "estado",
    )
    actions = None

    class ReservaAdminForm(forms.ModelForm):
        nombre_cliente = forms.CharField(label="Nombre del cliente", max_length=150)
        telefono_cliente = forms.CharField(label="Teléfono", strip=False)
        correo_cliente = forms.EmailField(label="Correo electrónico", required=False)

        class Meta:
            model = Reserva
            fields = ("fecha", "hora", "cantidad_personas", "mesa", "estado")

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.instance and self.instance.pk:
                cliente = self.instance.cliente
                self.initial.update(
                    nombre_cliente=cliente.nombre,
                    telefono_cliente=cliente.telefono,
                    correo_cliente=cliente.correo,
                )

        def clean_telefono_cliente(self):
            return normalizar_telefono(self.cleaned_data["telefono_cliente"])

        def _post_clean(self):
            # Las reglas y la disponibilidad se validan dentro de los servicios
            # transaccionales en save_model.
            from django.forms.models import construct_instance
            self.instance = construct_instance(self, self.instance, self._meta.fields, self._meta.exclude)

    form = ReservaAdminForm

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            raise ValidationError("Las reservas se registran desde el flujo de reservas.")
        anterior = Reserva.objects.get(pk=obj.pk)
        datos = form.cleaned_data
        cambios = {}
        for campo in ("fecha", "hora", "cantidad_personas", "mesa"):
            valor = datos[campo]
            if campo == "mesa":
                if valor.pk != anterior.mesa_id:
                    cambios["mesa_id"] = valor.pk
            elif valor != getattr(anterior, campo):
                cambios[campo] = valor
        contacto = {
            "nombre": datos["nombre_cliente"],
            "telefono": datos["telefono_cliente"],
            "correo": datos["correo_cliente"],
        }
        with transaction.atomic():
            actualizado = modificar_reserva(anterior.pk, cambios, contacto)
            if datos["estado"] != actualizado.estado:
                actualizado = cambiar_estado_reserva(actualizado.pk, datos["estado"])
        obj.__dict__.update(actualizado.__dict__)

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return False
