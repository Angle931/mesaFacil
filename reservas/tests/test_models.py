from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from ..admin import ClienteAdmin, ClienteAdminForm, MesaAdmin, ReservaAdmin
from ..codigos import ALFABETO_CODIGO, generar_codigo_confirmacion
from ..horarios import HORARIOS
from ..models import Cliente, Mesa, Reserva
from ..validators import normalizar_telefono


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


class CodigoReservaTests(SimpleTestCase):
    def test_generacion_longitud_y_alfabeto(self):
        codigo = generar_codigo_confirmacion()
        self.assertEqual(len(codigo), 16)
        self.assertTrue(set(codigo) <= set(ALFABETO_CODIGO))


class ReservaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mesa = Mesa.objects.create(numero="A1", capacidad=4)
        cls.cliente = Cliente.objects.create(nombre="Ana", telefono="+50588881234")

    def setUp(self):
        self.ahora = timezone.make_aware(datetime(2030, 5, 10, 13), timezone.get_default_timezone())
        reloj = patch("reservas.models.timezone.now", return_value=self.ahora)
        reloj.start()
        self.addCleanup(reloj.stop)
        self.fecha = self.ahora.date() + timedelta(days=1)

    def nueva(self, **cambios):
        datos = dict(cliente=self.cliente, mesa=self.mesa, fecha=self.fecha, hora=time(12), cantidad_personas=2)
        datos.update(cambios)
        return Reserva(**datos)

    def guardar(self, **cambios):
        reserva = self.nueva(**cambios)
        reserva.full_clean()
        reserva.save()
        return reserva

    def test_crear_reserva_y_relaciones(self):
        reserva = self.guardar()
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, Reserva.Estado.PENDIENTE)
        self.assertEqual(reserva.cliente, self.cliente)
        self.assertEqual(reserva.mesa, self.mesa)
        self.assertEqual(self.cliente.reservas.get(), reserva)
        self.assertEqual(self.mesa.reservas.get(), reserva)
        self.assertEqual(str(reserva), f"Reserva {reserva.codigo_confirmacion}")

    def test_campos_obligatorios(self):
        for campo in ("cliente", "mesa", "fecha", "hora", "cantidad_personas", "estado"):
            with self.subTest(campo=campo):
                with self.assertRaises(ValidationError):
                    self.nueva(**{campo: None}).full_clean()

    def test_proteccion_cliente_y_mesa(self):
        self.guardar()
        for objeto in (self.cliente, self.mesa):
            with self.subTest(modelo=type(objeto).__name__):
                with self.assertRaises(ProtectedError):
                    objeto.delete()

    def test_capacidad_limite_y_cantidad_uno(self):
        self.guardar(cantidad_personas=1)
        self.guardar(cantidad_personas=4, hora=time(13))

    def test_cantidad_invalida_django_y_postgresql(self):
        for cantidad in (0, -1):
            with self.subTest(cantidad=cantidad):
                with self.assertRaises(ValidationError):
                    self.nueva(cantidad_personas=cantidad).full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.nueva(cantidad_personas=cantidad).save()

    def test_mesa_inactiva_y_capacidad_insuficiente(self):
        with self.assertRaises(ValidationError) as error:
            self.nueva(cantidad_personas=5).full_clean()
        self.assertIn("cantidad_personas", error.exception.message_dict)
        Mesa.objects.filter(pk=self.mesa.pk).update(activa=False)
        with self.assertRaises(ValidationError) as error:
            self.nueva().full_clean()
        self.assertIn("mesa", error.exception.message_dict)

    def test_horarios_aprobados_independientes(self):
        self.assertEqual(HORARIOS, tuple(time(hora) for hora in range(12, 22)))
        for hora in HORARIOS:
            self.guardar(hora=hora)
        self.assertEqual(Reserva.objects.count(), 10)

    def test_horarios_invalidos_django_y_postgresql(self):
        for hora in (time(11), time(22), time(12, 30), time(12, 0, 1)):
            with self.subTest(hora=hora):
                with self.assertRaises(ValidationError):
                    self.nueva(hora=hora).full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.nueva(hora=hora).save()

    def test_creacion_solo_futura_en_hora_local(self):
        for fecha, hora in ((self.ahora.date() - timedelta(days=1), time(21)), (self.ahora.date(), time(12)), (self.ahora.date(), time(13))):
            with self.subTest(fecha=fecha, hora=hora):
                with self.assertRaises(ValidationError):
                    self.nueva(fecha=fecha, hora=hora).full_clean()
        self.guardar(fecha=self.ahora.date(), hora=time(14))

    def test_reprogramacion_pasada_rechazada(self):
        reserva = self.guardar()
        reserva.fecha = self.ahora.date()
        reserva.hora = time(12)
        with self.assertRaises(ValidationError):
            reserva.full_clean()

    def test_estados_invalidos_django_y_postgresql(self):
        for estado in ("", "OTRO"):
            with self.subTest(estado=estado):
                with self.assertRaises(ValidationError):
                    self.nueva(estado=estado).full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.nueva(estado=estado).save()

    def test_transiciones_aprobadas_y_rechazadas(self):
        permitidas = {
            "PENDIENTE": {"CONFIRMADA", "CANCELADA"},
            "CONFIRMADA": {"COMPLETADA", "CANCELADA"},
            "COMPLETADA": set(), "CANCELADA": set(),
        }
        # Datos históricos para que COMPLETADA sea temporalmente válida.
        for origen in Reserva.Estado.values:
            for destino in Reserva.Estado.values:
                with self.subTest(origen=origen, destino=destino):
                    reserva = self.nueva(fecha=self.ahora.date() - timedelta(days=1), estado=origen)
                    reserva.save()
                    reserva.estado = destino
                    if destino == origen or destino in permitidas[origen]:
                        reserva.full_clean()
                    else:
                        with self.assertRaises(ValidationError):
                            reserva.full_clean()
                    reserva.delete()

    def test_no_completar_antes_del_inicio(self):
        reserva = self.guardar(estado=Reserva.Estado.CONFIRMADA)
        reserva.estado = Reserva.Estado.COMPLETADA
        with self.assertRaises(ValidationError):
            reserva.full_clean()
        inicio = timezone.make_aware(datetime.combine(reserva.fecha, reserva.hora), timezone.get_default_timezone())
        with patch("reservas.models.timezone.now", return_value=inicio):
            reserva.full_clean()
            reserva.save()

    def test_cancelar_pasada_sin_revalidar_politica_de_mesas(self):
        reserva = self.guardar()
        Mesa.objects.filter(pk=self.mesa.pk).update(activa=False, capacidad=1)
        with patch("reservas.models.timezone.now", return_value=self.ahora + timedelta(days=2)):
            reserva.estado = Reserva.Estado.CANCELADA
            reserva.full_clean()
            reserva.save()

    def test_conflictos_activos_django_y_postgresql(self):
        for primero in ("PENDIENTE", "CONFIRMADA"):
            for segundo in ("PENDIENTE", "CONFIRMADA"):
                with self.subTest(primero=primero, segundo=segundo):
                    reserva = self.guardar(estado=primero)
                    with self.assertRaises(ValidationError):
                        self.nueva(estado=segundo).full_clean()
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        self.nueva(estado=segundo).save()
                    reserva.delete()

    def test_estados_no_bloqueantes_permiten_otras_reservas(self):
        for estado in ("CANCELADA", "COMPLETADA"):
            self.nueva(estado=estado).save()
        self.guardar()

    def test_cancelacion_libera_turno(self):
        reserva = self.guardar()
        reserva.estado = Reserva.Estado.CANCELADA
        reserva.full_clean()
        reserva.save()
        self.guardar()

    def test_sin_conflicto_con_otra_fecha_o_mesa(self):
        self.guardar()
        self.guardar(fecha=self.fecha + timedelta(days=1))
        otra = Mesa.objects.create(numero="A2", capacidad=4)
        self.guardar(mesa=otra)

    def test_edicion_sin_conflicto_con_si_misma(self):
        reserva = self.guardar()
        reserva.cantidad_personas = 3
        reserva.full_clean()
        reserva.save()

    def test_reasignacion_conflictiva(self):
        self.guardar()
        reserva = self.guardar(hora=time(13))
        reserva.hora = time(12)
        with self.assertRaises(ValidationError):
            reserva.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            reserva.save()

    def test_codigo_estable_y_colision_sin_reintentos(self):
        reserva = self.guardar()
        codigo = reserva.codigo_confirmacion
        reserva.full_clean()
        reserva.save()
        reserva.refresh_from_db()
        self.assertEqual(reserva.codigo_confirmacion, codigo)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.nueva(hora=time(13), codigo_confirmacion=codigo).save()
        reserva.codigo_confirmacion = "A" * 16 if codigo != "A" * 16 else "B" * 16
        with self.assertRaises(ValidationError):
            reserva.full_clean()

    def test_codigo_invalido_django_y_postgresql(self):
        for codigo in ("", "A" * 15, "a" * 16, "0" * 16):
            with self.subTest(codigo=codigo):
                with self.assertRaises(ValidationError):
                    self.nueva(codigo_confirmacion=codigo).full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.nueva(codigo_confirmacion=codigo).save()


class ReservaAdminTests(TestCase):
    def test_admin_solo_consulta(self):
        modelo_admin = admin.site.get_model_admin(Reserva)
        self.assertIsInstance(modelo_admin, ReservaAdmin)
        usuario = get_user_model().objects.create_superuser(username="admin", password="test-only")
        request = RequestFactory().get("/admin/reservas/reserva/")
        request.user = usuario
        self.assertTrue(modelo_admin.has_view_permission(request))
        self.assertFalse(modelo_admin.has_add_permission(request))
        self.assertFalse(modelo_admin.has_change_permission(request))
        self.assertFalse(modelo_admin.has_delete_permission(request))
        self.assertEqual(modelo_admin.get_actions(request), {})

        cliente = Cliente.objects.create(nombre="Ana", telefono="+50588881234")
        mesa = Mesa.objects.create(numero="A1", capacidad=4)
        reserva = Reserva.objects.create(cliente=cliente, mesa=mesa, fecha=timezone.localdate() + timedelta(days=1), hora=time(12), cantidad_personas=2)
        self.client.force_login(usuario)
        detalle = f"/admin/reservas/reserva/{reserva.pk}/change/"
        self.assertEqual(self.client.get("/admin/reservas/reserva/").status_code, 200)
        self.assertEqual(self.client.get(detalle).status_code, 200)
        self.assertEqual(self.client.post(detalle, {"estado": "CANCELADA"}).status_code, 403)
        self.assertEqual(self.client.post("/admin/reservas/reserva/add/", {}).status_code, 403)
        self.assertEqual(self.client.post(f"/admin/reservas/reserva/{reserva.pk}/delete/", {}).status_code, 403)
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, "PENDIENTE")
