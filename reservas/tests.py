from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from .admin import MesaAdmin
from .models import Mesa


class MesaTests(TestCase):
    def test_crear_mesa_valida(self):
        for numero in ("1", "A1", "Terraza-1"):
            with self.subTest(numero=numero):
                mesa = Mesa(numero=numero, capacidad=4)
                mesa.full_clean()
                mesa.save()
                mesa.refresh_from_db()
                self.assertEqual(mesa.numero, numero)
                self.assertEqual(mesa.capacidad, 4)

    def test_activa_por_defecto(self):
        mesa = Mesa.objects.create(numero="A1", capacidad=4)
        mesa.refresh_from_db()
        self.assertIs(mesa.activa, True)

    def test_capacidad_uno(self):
        mesa = Mesa(numero="A1", capacidad=1)
        mesa.full_clean()
        mesa.save()
        mesa.refresh_from_db()
        self.assertEqual(mesa.capacidad, 1)

    def test_capacidad_invalida_en_validacion(self):
        for capacidad in (0, -1):
            with self.subTest(capacidad=capacidad):
                mesa = Mesa(numero="A1", capacidad=capacidad)
                with self.assertRaises(ValidationError) as error:
                    mesa.full_clean()
                self.assertIn("capacidad", error.exception.message_dict)

    def test_capacidad_invalida_en_base_de_datos(self):
        for capacidad in (0, -1):
            with self.subTest(capacidad=capacidad):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Mesa.objects.create(numero="A1", capacidad=capacidad)

    def test_numero_duplicado_en_validacion(self):
        Mesa.objects.create(numero="A1", capacidad=4)
        with self.assertRaises(ValidationError) as error:
            Mesa(numero="A1", capacidad=2).full_clean()
        self.assertIn("numero", error.exception.message_dict)

    def test_numero_duplicado_en_base_de_datos(self):
        Mesa.objects.create(numero="A1", capacidad=4)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Mesa.objects.create(numero="A1", capacidad=2)

    def test_numero_vacio(self):
        with self.assertRaises(ValidationError) as error:
            Mesa(numero="", capacidad=4).full_clean()
        self.assertIn("numero", error.exception.message_dict)

    def test_representacion(self):
        self.assertEqual(str(Mesa(numero="Terraza-1", capacidad=4)), "Mesa Terraza-1")


class MesaAdminTests(TestCase):
    def test_mesa_registrada(self):
        self.assertTrue(admin.site.is_registered(Mesa))
        self.assertIsInstance(admin.site.get_model_admin(Mesa), MesaAdmin)

    def test_eliminacion_deshabilitada_incluso_para_superusuario(self):
        request = RequestFactory().get("/admin/reservas/mesa/")
        request.user = get_user_model()(is_active=True, is_staff=True, is_superuser=True)
        mesa_admin = admin.site.get_model_admin(Mesa)
        mesa = Mesa.objects.create(numero="A1", capacidad=4)
        self.assertFalse(mesa_admin.has_delete_permission(request))
        self.assertFalse(mesa_admin.has_delete_permission(request, mesa))
        self.assertNotIn("delete_selected", mesa_admin.get_actions(request))
