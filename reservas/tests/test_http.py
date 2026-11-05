from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.utils import timezone

from ..models import Cliente, Mesa, Reserva


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class FlujoPublicoHTTPTests(TestCase):
    def setUp(self):
        self.fecha = timezone.localdate() + timedelta(days=2)
        self.mesa = Mesa.objects.create(numero="P1", capacidad=4)
        self.busqueda = {
            "fecha": self.fecha.isoformat(), "hora": "12:00", "cantidad_personas": "2",
        }

    def test_consulta_seleccion_registro_y_confirmacion(self):
        respuesta = self.client.post("/", self.busqueda)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Mesa P1")

        respuesta = self.client.post("/", {
            **self.busqueda, "accion": "elegir", "mesa_id": str(self.mesa.pk),
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Completa tu reserva")

        respuesta = self.client.post("/", {
            **self.busqueda, "accion": "reservar", "mesa_id": str(self.mesa.pk),
            "nombre": "María", "telefono": "8888-1234", "correo": "",
        })
        self.assertEqual(respuesta.status_code, 200)
        reserva = Reserva.objects.get()
        self.assertContains(respuesta, reserva.codigo_confirmacion)
        self.assertEqual(reserva.cliente.nombre, "María")

    def test_no_ofrece_mesa_inactiva_y_rechaza_seleccion_manipulada(self):
        self.mesa.activa = False
        self.mesa.save()
        respuesta = self.client.post("/", self.busqueda)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Mesa P1")

        respuesta = self.client.post("/", {
            **self.busqueda, "accion": "elegir", "mesa_id": str(self.mesa.pk),
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "ya no está disponible")
        self.assertEqual(Cliente.objects.count(), 0)
        self.assertEqual(Reserva.objects.count(), 0)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class AdminReservaHTTPTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("staff", password="test-only", is_staff=True)
        self.cliente = Cliente.objects.create(nombre="Ana", telefono="+50588881234")
        self.mesa = Mesa.objects.create(numero="A1", capacidad=4)
        self.reserva = Reserva.objects.create(
            cliente=self.cliente, mesa=self.mesa,
            fecha=timezone.localdate() + timedelta(days=1), hora=time(12), cantidad_personas=2,
        )
        self.url = f"/admin/reservas/reserva/{self.reserva.pk}/change/"

    def grant(self, codename):
        self.user.user_permissions.add(Permission.objects.get(codename=codename, content_type__app_label="reservas"))

    def post_data(self, **overrides):
        data = {
            "nombre_cliente": "Ana", "telefono_cliente": "+50588881234", "correo_cliente": "",
            "fecha": self.reserva.fecha.isoformat(), "hora": "12:00:00",
            "cantidad_personas": "2", "mesa": str(self.mesa.pk), "estado": "PENDIENTE", "_save": "Guardar",
        }
        data.update(overrides)
        return data

    def test_staff_sin_permiso_no_puede_editar_por_get_ni_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.post_data(estado="CANCELADA")).status_code, 403)
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.estado, Reserva.Estado.PENDIENTE)

    def test_staff_con_solo_consulta_no_puede_editar_por_get_ni_post(self):
        self.grant("view_reserva")
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url, self.post_data(estado="CANCELADA")).status_code, 403)
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.estado, Reserva.Estado.PENDIENTE)

    def test_error_de_capacidad_se_muestra_y_no_guarda_contacto(self):
        self.grant("change_reserva")
        self.client.force_login(self.user)
        respuesta = self.client.post(self.url, self.post_data(
            nombre_cliente="Nombre no guardado", cantidad_personas="5",
        ))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "supera la capacidad")
        self.assertContains(respuesta, "Nombre no guardado")
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.cantidad_personas, 2)
        self.assertEqual(self.cliente.nombre, "Ana")

    def test_errores_de_mesa_estado_y_fecha_se_muestran_sin_guardar(self):
        self.grant("change_reserva")
        self.client.force_login(self.user)
        mesa_inactiva = Mesa.objects.create(numero="X1", capacidad=8, activa=False)
        casos = (
            ("mesa inactiva", {"mesa": str(mesa_inactiva.pk)}, "mesa debe estar activa"),
            ("reserva pasada", {"fecha": (timezone.localdate() - timedelta(days=1)).isoformat()}, "deben ser futuras"),
        )
        for nombre, cambios, mensaje in casos:
            with self.subTest(nombre=nombre):
                respuesta = self.client.post(self.url, self.post_data(**cambios))
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, mensaje)
                self.reserva.refresh_from_db()
                self.assertEqual(self.reserva.mesa_id, self.mesa.pk)
                self.assertEqual(self.reserva.estado, Reserva.Estado.PENDIENTE)
                self.assertEqual(self.cliente.nombre, "Ana")

    def test_transicion_de_estado_invalida_se_muestra_sin_guardar(self):
        self.grant("change_reserva")
        self.client.force_login(self.user)
        fecha_pasada = timezone.localdate() - timedelta(days=1)
        self.reserva.fecha = fecha_pasada
        self.reserva.save(update_fields=("fecha",))
        respuesta = self.client.post(self.url, self.post_data(
            fecha=fecha_pasada.isoformat(), estado="COMPLETADA",
        ))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "transición de estado")
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.estado, Reserva.Estado.PENDIENTE)

    def test_no_permite_completar_reserva_antes_del_turno(self):
        self.grant("change_reserva")
        self.client.force_login(self.user)
        self.reserva.estado = Reserva.Estado.CONFIRMADA
        self.reserva.save(update_fields=("estado",))
        respuesta = self.client.post(self.url, self.post_data(estado="COMPLETADA"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "antes de su fecha y hora")
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.estado, Reserva.Estado.CONFIRMADA)

    def test_error_del_servicio_se_presenta_con_post_conservado_y_rollback(self):
        self.grant("change_reserva")
        self.client.force_login(self.user)
        mesa_ocupada = Mesa.objects.create(numero="A2", capacidad=6)
        otro_cliente = Cliente.objects.create(nombre="Luis", telefono="+50588881235")
        Reserva.objects.create(
            cliente=otro_cliente, mesa=mesa_ocupada, fecha=self.reserva.fecha,
            hora=self.reserva.hora, cantidad_personas=2,
        )
        respuesta = self.client.post(self.url, self.post_data(
            nombre_cliente="Cambio temporal", mesa=str(mesa_ocupada.pk),
        ))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "ya no está disponible")
        self.assertContains(respuesta, "Cambio temporal")
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.mesa_id, self.mesa.pk)
        self.assertEqual(self.cliente.nombre, "Ana")
