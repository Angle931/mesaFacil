from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .exceptions import ConflictoReserva, GeneracionCodigoAgotada, ReservaServiceError, SinDisponibilidad
from .models import Cliente, Mesa, Reserva
from .services import consultar_mesas_disponibles, registrar_reserva


class ServiciosReservaTests(TestCase):
    def setUp(self):
        self.ahora = timezone.make_aware(datetime(2030, 5, 10, 13), timezone.get_default_timezone())
        reloj = patch("django.utils.timezone.now", return_value=self.ahora)
        reloj.start()
        self.addCleanup(reloj.stop)
        self.solicitud = dict(fecha=self.ahora.date() + timedelta(days=1), hora=time(12), cantidad_personas=2)
        self.mesa = Mesa.objects.create(numero="A1", capacidad=4)

    def registrar(self, **cambios):
        datos = dict(nombre="  Ana María  ", telefono="8888-1234", **self.solicitud)
        datos.update(cambios)
        return registrar_reserva(**datos)

    def test_registro_normaliza_y_crea_pendiente(self):
        reserva = self.registrar(correo=" Ana@Example.com ")
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, Reserva.Estado.PENDIENTE)
        self.assertEqual(reserva.cliente.nombre, "Ana María")
        self.assertEqual(reserva.cliente.telefono, "+50588881234")
        self.assertEqual(reserva.cliente.correo, "Ana@Example.com")
        self.assertEqual(reserva.mesa, self.mesa)
        self.assertEqual(len(reserva.codigo_confirmacion), 16)

    def test_asignacion_por_capacidad_y_desempate_por_id(self):
        menor = Mesa.objects.create(numero="Z9", capacidad=2)
        otra = Mesa.objects.create(numero="A0", capacidad=2)
        disponible = consultar_mesas_disponibles(**self.solicitud)
        self.assertEqual([mesa.pk for mesa in disponible], [menor.pk, otra.pk, self.mesa.pk])
        self.assertEqual(self.registrar().mesa, menor)
        self.assertEqual(self.registrar().mesa, otra)
        self.assertEqual(self.registrar().mesa, self.mesa)

    def test_no_reutiliza_cliente_por_telefono(self):
        primero = self.registrar()
        segundo = self.registrar(hora=time(13))
        self.assertNotEqual(primero.cliente_id, segundo.cliente_id)
        self.assertEqual(Cliente.objects.count(), 2)
        self.assertEqual(segundo.cliente.correo, "")

    def test_disponibilidad_por_estado_fecha_y_hora(self):
        reserva = self.registrar()
        for estado in Reserva.Estado.values:
            Reserva.objects.filter(pk=reserva.pk).update(estado=estado)
            mesas = consultar_mesas_disponibles(**self.solicitud)
            self.assertEqual(bool(mesas), estado in ("CANCELADA", "COMPLETADA"))
        self.assertEqual(consultar_mesas_disponibles(**{**self.solicitud, "hora": time(13)}), [self.mesa])
        self.assertEqual(consultar_mesas_disponibles(**{**self.solicitud, "fecha": self.solicitud["fecha"] + timedelta(days=1)}), [self.mesa])

    def test_excluye_inactivas_e_insuficientes(self):
        self.mesa.activa = False
        self.mesa.save()
        Mesa.objects.create(numero="B1", capacidad=1)
        self.assertEqual(consultar_mesas_disponibles(**self.solicitud), [])
        with self.assertRaises(SinDisponibilidad):
            self.registrar()
        self.assertEqual(Cliente.objects.count(), 0)
        self.assertEqual(Reserva.objects.count(), 0)

    def test_solicitud_invalida_no_equivale_a_lista_vacia(self):
        invalidas = (
            {"fecha": None}, {"fecha": "invalida"}, {"hora": None}, {"hora": "invalida"},
            {"hora": time(11)}, {"hora": time(12, 30)}, {"cantidad_personas": 0},
            {"cantidad_personas": -1}, {"cantidad_personas": None},
            {"cantidad_personas": True}, {"cantidad_personas": 1.5},
            {"fecha": self.ahora.date() - timedelta(days=1)},
            {"fecha": self.ahora.date(), "hora": time(12)},
            {"fecha": self.ahora.date(), "hora": time(13)},
        )
        for cambios in invalidas:
            with self.subTest(cambios=cambios):
                with self.assertRaises(ValidationError):
                    consultar_mesas_disponibles(**{**self.solicitud, **cambios})
                with self.assertRaises(ValidationError):
                    self.registrar(**cambios)
        self.assertEqual(Cliente.objects.count(), 0)

    def test_campos_convertidos_con_validadores_del_modelo(self):
        mesas = consultar_mesas_disponibles(fecha="2030-05-11", hora="12:00", cantidad_personas="2")
        self.assertEqual(mesas, [self.mesa])

    def test_datos_cliente_invalidos_sin_escrituras(self):
        for cambios in ({"nombre": " "}, {"telefono": "invalido"}, {"correo": None}, {"correo": "invalido"}):
            with self.subTest(cambios=cambios):
                with self.assertRaises(ValidationError):
                    self.registrar(**cambios)
        self.assertEqual(Cliente.objects.count(), 0)
        self.assertEqual(Reserva.objects.count(), 0)

    def test_consulta_previa_no_reserva_mesa(self):
        self.assertEqual(consultar_mesas_disponibles(**self.solicitud), [self.mesa])
        self.registrar()
        with self.assertRaises(SinDisponibilidad):
            self.registrar()
        self.assertEqual(Cliente.objects.count(), 1)

    def test_revalida_actividad_y_capacidad_despues_del_bloqueo(self):
        from .services import _bloquear_candidatas

        for cambios in ({"activa": False}, {"capacidad": 1}):
            with self.subTest(cambios=cambios):
                Mesa.objects.filter(pk=self.mesa.pk).update(activa=True, capacidad=4)

                def cambiar_mesa(cantidad):
                    filas = _bloquear_candidatas(cantidad)
                    Mesa.objects.filter(pk=self.mesa.pk).update(**cambios)
                    return filas

                with patch("reservas.services._bloquear_candidatas", side_effect=cambiar_mesa):
                    with self.assertRaises(SinDisponibilidad):
                        self.registrar()
                self.assertEqual(Cliente.objects.count(), 0)

    def test_revalida_hora_tras_esperar_bloqueo(self):
        from .services import _bloquear_candidatas

        def esperar(cantidad):
            filas = _bloquear_candidatas(cantidad)
            self.ahora = self.ahora + timedelta(days=2)
            return filas

        with patch("reservas.services._bloquear_candidatas", side_effect=esperar):
            with patch("django.utils.timezone.now", side_effect=lambda: self.ahora):
                with self.assertRaises(ValidationError):
                    self.registrar()
        self.assertEqual(Cliente.objects.count(), 0)

    def test_colision_real_se_recupera_sin_duplicar_cliente(self):
        codigo = "A" * 16
        with patch("reservas.services.generar_codigo_confirmacion", return_value=codigo):
            self.registrar(hora=time(13))
        with patch("reservas.services.generar_codigo_confirmacion", side_effect=[codigo, "B" * 16]) as generar:
            reserva = self.registrar()
        self.assertEqual(generar.call_count, 2)
        self.assertEqual(reserva.codigo_confirmacion, "B" * 16)
        self.assertEqual(Cliente.objects.count(), 2)
        self.assertEqual(Reserva.objects.count(), 2)

    def test_agota_cinco_intentos_y_revierte_cliente(self):
        with patch("reservas.services.generar_codigo_confirmacion", return_value="A" * 16):
            self.registrar(hora=time(13))
        with patch("reservas.services.generar_codigo_confirmacion", return_value="A" * 16) as generar:
            with self.assertRaises(GeneracionCodigoAgotada):
                self.registrar()
        self.assertEqual(generar.call_count, 5)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(Reserva.objects.count(), 1)
        # La conexión sigue utilizable tras los savepoints y el rollback exterior.
        self.registrar()

    def test_error_integridad_desconocido_no_se_oculta_ni_reintenta(self):
        guardar = Reserva.save

        def guardar_invalida(reserva, *args, **kwargs):
            reserva.cantidad_personas = 0
            return guardar(reserva, *args, **kwargs)

        with patch("reservas.services.generar_codigo_confirmacion", return_value="A" * 16) as generar:
            with patch.object(Reserva, "save", guardar_invalida):
                with self.assertRaises(IntegrityError):
                    self.registrar()
        self.assertEqual(generar.call_count, 1)
        self.assertEqual(Cliente.objects.count(), 0)
        self.assertEqual(Reserva.objects.count(), 0)

    def test_conflicto_real_de_turno_no_reintenta_codigo(self):
        # Simular un escritor que no usa servicios entre validar e insertar.
        self.registrar()
        with patch("reservas.services._disponibles", return_value=Mesa.objects.filter(pk=self.mesa.pk)):
            with patch.object(Reserva, "full_clean"):
                with patch("reservas.services.generar_codigo_confirmacion", return_value="B" * 16) as generar:
                    with self.assertRaises(ConflictoReserva):
                        self.registrar()
        self.assertEqual(generar.call_count, 1)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(Reserva.objects.count(), 1)

    def test_transaccion_exterior_puede_revertir_operacion_completa(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.registrar()
                raise RuntimeError("rollback del llamador")
        self.assertEqual(Cliente.objects.count(), 0)
        self.assertEqual(Reserva.objects.count(), 0)

    def test_excepciones_bajo_base_comun(self):
        for clase in (SinDisponibilidad, ConflictoReserva, GeneracionCodigoAgotada):
            self.assertIsInstance(clase(), ReservaServiceError)
