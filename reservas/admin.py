from django import forms
from django.contrib import admin

from .models import Cliente, Mesa, Reserva
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
    readonly_fields = ("codigo_confirmacion", "cliente", "mesa", "fecha", "hora", "cantidad_personas", "estado")
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
