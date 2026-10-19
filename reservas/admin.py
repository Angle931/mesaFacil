from django.contrib import admin

from .models import Mesa


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ("numero", "capacidad", "activa")
    list_filter = ("activa",)
    ordering = ("numero",)

    def has_delete_permission(self, request, obj=None):
        return False
