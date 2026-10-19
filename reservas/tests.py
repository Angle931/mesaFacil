from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, SimpleTestCase, TestCase

from .admin import ClienteAdmin, ClienteAdminForm, MesaAdmin
from .models import Cliente, Mesa
from .validators import normalizar_telefono


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


TELEFONOS_VALIDOS = (
    "88881234", "8888-1234", "8888 1234", "+50588881234", "+505 8888-1234",
)
TELEFONOS_INVALIDOS = (
    "", "   ", None, "8888ABCD", "88881234 ext 1", "+50688881234",
    "0050588881234", "50588881234", "8888.1234", "(8888)1234",
    "8888/1234", "8888\t1234", "88881234\n", "8888123", "888812345",
    "+5058888123", "+505888812345", "++50588881234", "８８８８１２３４",
)


class NormalizarTelefonoTests(SimpleTestCase):
    def test_formatos_aprobados(self):
        for entrada in TELEFONOS_VALIDOS:
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_telefono(entrada), "+50588881234")

    def test_entradas_invalidas(self):
        for entrada in TELEFONOS_INVALIDOS:
            with self.subTest(entrada=entrada):
                with self.assertRaises(ValidationError):
                    normalizar_telefono(entrada)

    def test_idempotencia(self):
        valor = normalizar_telefono("8888-1234")
        self.assertEqual(normalizar_telefono(valor), valor)


class ClienteTests(TestCase):
    def crear_cliente(self, **cambios):
        datos = {"nombre": "Ana María", "telefono": "88881234"}
        datos.update(cambios)
        cliente = Cliente(**datos)
        cliente.full_clean()
        cliente.save()
        cliente.refresh_from_db()
        return cliente

    def test_crear_con_correo_y_normalizar_espacios(self):
        cliente = self.crear_cliente(nombre="  Ana María  ", correo="  Ana@Example.com  ")
        self.assertEqual(cliente.nombre, "Ana María")
        self.assertEqual(cliente.correo, "Ana@Example.com")
        self.assertEqual(cliente.telefono, "+50588881234")

    def test_crear_sin_correo_o_con_correo_vacio(self):
        self.assertEqual(self.crear_cliente().correo, "")
        for correo in ("", "   "):
            with self.subTest(correo=correo):
                self.assertEqual(self.crear_cliente(correo=correo).correo, "")

    def test_nombre_obligatorio(self):
        for nombre in (None, "", "   ", "\t\n"):
            with self.subTest(nombre=nombre):
                with self.assertRaises(ValidationError) as error:
                    self.crear_cliente(nombre=nombre)
                self.assertIn("nombre", error.exception.message_dict)
        with self.assertRaises(ValidationError):
            Cliente(telefono="88881234").full_clean()

    def test_nombre_con_tildes_apostrofos_y_guiones(self):
        nombre = "MARÍA O'Connor-López"
        self.assertEqual(self.crear_cliente(nombre=nombre).nombre, nombre)

    def test_limites_nombre(self):
        self.assertEqual(len(self.crear_cliente(nombre="Á" * 150).nombre), 150)
        with self.assertRaises(ValidationError) as error:
            self.crear_cliente(nombre="A" * 151)
        self.assertIn("nombre", error.exception.message_dict)

    def test_limites_correo(self):
        correo = "a" * 64 + "@" + ".".join(("b" * 63, "c" * 63, "d" * 57, "com"))
        self.assertEqual(len(correo), 254)
        self.assertEqual(self.crear_cliente(correo=correo).correo, correo)
        with self.assertRaises(ValidationError) as error:
            self.crear_cliente(correo="a" + correo)
        self.assertIn("correo", error.exception.message_dict)

    def test_formatos_telefono_normalizados_antes_de_longitud(self):
        for telefono in TELEFONOS_VALIDOS:
            with self.subTest(telefono=telefono):
                self.assertEqual(self.crear_cliente(telefono=telefono).telefono, "+50588881234")

    def test_telefono_invalido(self):
        for telefono in TELEFONOS_INVALIDOS:
            with self.subTest(telefono=telefono):
                with self.assertRaises(ValidationError) as error:
                    self.crear_cliente(telefono=telefono)
                self.assertIn("telefono", error.exception.message_dict)

    def test_correo_invalido(self):
        with self.assertRaises(ValidationError) as error:
            self.crear_cliente(correo="correo-invalido")
        self.assertIn("correo", error.exception.message_dict)

    def test_correo_null_rechazado_en_django(self):
        with self.assertRaises(ValidationError) as error:
            self.crear_cliente(correo=None)
        self.assertIn("correo", error.exception.message_dict)

    def test_campos_null_rechazados_en_postgresql(self):
        for campo in ("nombre", "telefono", "correo"):
            datos = {"nombre": "Ana", "telefono": "+50588881234", "correo": ""}
            datos[campo] = None
            with self.subTest(campo=campo):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Cliente.objects.create(**datos)

    def test_telefonos_y_correos_repetidos_permitidos(self):
        primero = self.crear_cliente(correo="ana@example.com")
        segundo = self.crear_cliente(correo="ana@example.com")
        self.assertNotEqual(primero.pk, segundo.pk)
        self.assertEqual(primero.telefono, segundo.telefono)

    def test_nombre_invalido_en_postgresql(self):
        for nombre in ("", "   ", "\t\n"):
            with self.subTest(nombre=nombre):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Cliente.objects.create(nombre=nombre, telefono="+50588881234")

    def test_telefono_invalido_en_postgresql(self):
        for telefono in ("", "88881234", "+50688881234", "+5058888abcd", "+5058888123"):
            with self.subTest(telefono=telefono):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Cliente.objects.create(nombre="Ana", telefono=telefono)

    def test_representacion_sin_datos_de_contacto(self):
        self.assertEqual(str(Cliente(nombre="Ana", telefono="+50588881234")), "Ana")

    def test_clean_fields_respeta_exclude(self):
        cliente = Cliente(nombre="Ana", telefono="invalido")
        cliente.clean_fields(exclude={"telefono"})
        self.assertEqual(cliente.telefono, "invalido")


class ClienteAdminTests(TestCase):
    def test_registro(self):
        self.assertTrue(admin.site.is_registered(Cliente))
        self.assertIsInstance(admin.site.get_model_admin(Cliente), ClienteAdmin)

    def test_formulario_acepta_telefono_con_separadores(self):
        for telefono in TELEFONOS_VALIDOS:
            with self.subTest(telefono=telefono):
                formulario = ClienteAdminForm(data={"nombre": "Ana", "telefono": telefono, "correo": ""})
                self.assertTrue(formulario.is_valid(), formulario.errors)
                cliente = formulario.save()
                cliente.refresh_from_db()
                self.assertEqual(cliente.telefono, "+50588881234")
                self.assertEqual(cliente.correo, "")

    def test_formulario_rechaza_telefono_invalido(self):
        formulario = ClienteAdminForm(data={"nombre": "Ana", "telefono": "8888.ABCD"})
        self.assertFalse(formulario.is_valid())
        self.assertIn("telefono", formulario.errors)

    def test_eliminacion_deshabilitada_incluso_para_superusuario(self):
        request = RequestFactory().get("/admin/reservas/cliente/")
        request.user = get_user_model()(is_active=True, is_staff=True, is_superuser=True)
        cliente_admin = admin.site.get_model_admin(Cliente)
        cliente = Cliente.objects.create(nombre="Ana", telefono="+50588881234")
        self.assertFalse(cliente_admin.has_delete_permission(request))
        self.assertFalse(cliente_admin.has_delete_permission(request, cliente))
        self.assertNotIn("delete_selected", cliente_admin.get_actions(request))
