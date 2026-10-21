"""Pruebas PostgreSQL: bloqueo real observado, sin usar sleeps para sincronizar."""

from datetime import time, timedelta
from queue import Queue
from threading import Event, Thread, current_thread
from time import monotonic
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from ..exceptions import ConflictoReserva, SinDisponibilidad
from ..models import Cliente, Mesa, Reserva
from .. import services
from ..services import _bloquear_candidatas, cancelar_reserva, modificar_reserva, registrar_reserva


class RegistroConcurrenteTests(TransactionTestCase):
    def setUp(self):
        # Fallar explícitamente en otro motor: estas garantías no se prueban con SQLite.
        self.assertEqual(connection.vendor, "postgresql", "La concurrencia requiere PostgreSQL.")
        self.solicitud = dict(
            nombre="Ana", telefono="88881234", fecha=timezone.localdate() + timedelta(days=2),
            hora=time(12), cantidad_personas=2,
        )

    def ejecutar_dos_registros(self):
        primera_bloqueada = Event()
        segunda_intentando = Event()
        liberar_primera = Event()
        resultados = Queue()
        pids = {}
        ordenes = {}
        hilos = []

        def bloquear(cantidad):
            nombre = current_thread().name
            if nombre == "registro-segundo":
                segunda_intentando.set()
            filas = _bloquear_candidatas(cantidad)
            ordenes[nombre] = [mesa.pk for mesa in filas]
            if nombre == "registro-primero":
                primera_bloqueada.set()
                if not liberar_primera.wait(10):
                    raise TimeoutError("No se liberó el primer registro dentro del límite.")
            return filas

        def registrar():
            nombre = current_thread().name
            try:
                connections.close_all()
                with connections["default"].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '8s'")
                    cursor.execute("SET statement_timeout = '12s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids[nombre] = cursor.fetchone()[0]
                reserva = registrar_reserva(**self.solicitud)
                resultados.put((nombre, reserva.pk))
            except Exception as error:
                resultados.put((nombre, error))
            finally:
                connections.close_all()

        with patch("reservas.services._bloquear_candidatas", side_effect=bloquear):
            try:
                primero = Thread(target=registrar, name="registro-primero", daemon=True)
                hilos.append(primero)
                primero.start()
                self.assertTrue(primera_bloqueada.wait(5), "El primer registro no obtuvo las candidatas.")
                segundo = Thread(target=registrar, name="registro-segundo", daemon=True)
                hilos.append(segundo)
                segundo.start()
                self.assertTrue(segunda_intentando.wait(5), "El segundo registro no intentó bloquear.")

                # Observar la espera real en PostgreSQL antes de permitir el commit.
                limite = monotonic() + 5
                bloqueo_observado = False
                while monotonic() < limite:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_blocking_pids(%s)", [pids["registro-segundo"]])
                        bloqueadores = cursor.fetchone()[0]
                    if pids["registro-primero"] in bloqueadores:
                        bloqueo_observado = True
                        break
                    if not segundo.is_alive():
                        break
                self.assertTrue(bloqueo_observado, "PostgreSQL no registró la espera esperada.")
                self.assertNotEqual(pids["registro-primero"], pids["registro-segundo"])
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    self.assertNotIn(cursor.fetchone()[0], pids.values())
            finally:
                liberar_primera.set()
                for hilo in hilos:
                    hilo.join(timeout=15)
                self.assertFalse(any(hilo.is_alive() for hilo in hilos), "Un registro quedó bloqueado.")

        self.assertEqual(resultados.qsize(), 2)
        for ids in ordenes.values():
            self.assertEqual(ids, sorted(ids))
        return dict(resultados.get_nowait() for _ in range(2))

    def test_dos_registros_una_mesa_no_duplican_asignacion(self):
        mesa = Mesa.objects.create(numero="A1", capacidad=2)
        resultados = self.ejecutar_dos_registros()
        self.assertIsInstance(resultados["registro-primero"], int)
        self.assertIsInstance(resultados["registro-segundo"], SinDisponibilidad)
        self.assertEqual(Reserva.objects.count(), 1)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(Reserva.objects.get().mesa_id, mesa.pk)

    def test_dos_registros_eligen_mesas_distintas_en_orden_aprobado(self):
        # El orden de bloqueo por id es diferente del orden de selección por capacidad.
        mayor = Mesa.objects.create(numero="A1", capacidad=4)
        menor = Mesa.objects.create(numero="Z9", capacidad=2)
        resultados = self.ejecutar_dos_registros()
        for resultado in resultados.values():
            self.assertIsInstance(resultado, int, repr(resultado))
        self.assertEqual(Reserva.objects.get(pk=resultados["registro-primero"]).mesa_id, menor.pk)
        self.assertEqual(Reserva.objects.get(pk=resultados["registro-segundo"]).mesa_id, mayor.pk)
        self.assertEqual(Reserva.objects.count(), 2)
        self.assertEqual(Cliente.objects.count(), 2)

    def test_desempate_concurrente_por_identificador(self):
        primera = Mesa.objects.create(numero="Z9", capacidad=2)
        segunda = Mesa.objects.create(numero="A1", capacidad=2)
        resultados = self.ejecutar_dos_registros()
        for resultado in resultados.values():
            self.assertIsInstance(resultado, int, repr(resultado))
        self.assertEqual(Reserva.objects.get(pk=resultados["registro-primero"]).mesa_id, primera.pk)
        self.assertEqual(Reserva.objects.get(pk=resultados["registro-segundo"]).mesa_id, segunda.pk)
        self.assertEqual(Cliente.objects.count(), 2)

    def test_colision_codigo_entre_conexiones_se_recupera(self):
        Mesa.objects.create(numero="A1", capacidad=2)
        Mesa.objects.create(numero="A2", capacidad=2)
        intentos = {}

        def generar():
            nombre = current_thread().name
            intentos[nombre] = intentos.get(nombre, 0) + 1
            return "A" * 16 if intentos[nombre] == 1 else "B" * 16

        with patch("reservas.services.generar_codigo_confirmacion", side_effect=generar):
            resultados = self.ejecutar_dos_registros()
        for resultado in resultados.values():
            self.assertIsInstance(resultado, int, repr(resultado))
        self.assertEqual(intentos, {"registro-primero": 1, "registro-segundo": 2})
        self.assertEqual(set(Reserva.objects.values_list("codigo_confirmacion", flat=True)), {"A" * 16, "B" * 16})
        self.assertEqual(Cliente.objects.count(), 2)


class ModificacionConcurrenteTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql", "Estas pruebas requieren PostgreSQL.")
        self.fecha = timezone.localdate() + timedelta(days=2)
        self.mesa1 = Mesa.objects.create(numero="A1", capacidad=4)
        self.mesa2 = Mesa.objects.create(numero="A2", capacidad=4)
        self.mesa3 = Mesa.objects.create(numero="A3", capacidad=4)

    def crear_reserva(self, mesa, cliente=None):
        if cliente is None:
            cliente = Cliente.objects.create(nombre="Ana", telefono="+50588881234")
        return Reserva.objects.create(cliente=cliente, mesa=mesa, fecha=self.fecha, hora=time(12), cantidad_personas=2)

    def ejecutar_operaciones(self, primera, segunda, punto="_bloquear_reserva"):
        obtenido = Event()
        intentando = Event()
        liberar = Event()
        resultados = Queue()
        pids = {}
        hilos = []
        original = getattr(services, punto)

        def interceptar(*args, **kwargs):
            nombre = current_thread().name
            if nombre == "operacion-segunda":
                intentando.set()
            try:
                return original(*args, **kwargs)
            finally:
                # Retener también un rechazo antes de que salga de atomic y
                # libere sus bloqueos: permite probar destinos ya ocupados.
                if nombre == "operacion-primera":
                    obtenido.set()
                    if not liberar.wait(10):
                        raise TimeoutError("No se liberó la primera operación.")

        def ejecutar(operacion):
            nombre = current_thread().name
            try:
                connections.close_all()
                conexion = connections["default"]
                with conexion.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '8s'")
                    cursor.execute("SET statement_timeout = '12s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids[nombre] = cursor.fetchone()[0]

                def verificar_orden(execute, sql, params, many, context):
                    if '"reservas_mesa"' in sql and "FOR UPDATE" in sql:
                        if 'ORDER BY "reservas_mesa"."id" ASC' not in sql or "SKIP LOCKED" in sql:
                            raise AssertionError("Bloqueo de mesas fuera del protocolo aprobado.")
                    return execute(sql, params, many, context)

                with conexion.execute_wrapper(verificar_orden):
                    resultado = operacion()
                resultados.put((nombre, resultado.pk))
            except Exception as error:
                resultados.put((nombre, error))
            finally:
                connections.close_all()

        with patch(f"reservas.services.{punto}", side_effect=interceptar):
            try:
                primero = Thread(target=ejecutar, args=(primera,), name="operacion-primera", daemon=True)
                hilos.append(primero)
                primero.start()
                self.assertTrue(obtenido.wait(5), "La primera operación no llegó al punto de bloqueo.")
                segundo = Thread(target=ejecutar, args=(segunda,), name="operacion-segunda", daemon=True)
                hilos.append(segundo)
                segundo.start()
                self.assertTrue(intentando.wait(5), "La segunda operación no intentó obtener el bloqueo.")
                limite = monotonic() + 5
                esperando = False
                while monotonic() < limite:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_blocking_pids(%s)", [pids["operacion-segunda"]])
                        esperando = pids["operacion-primera"] in cursor.fetchone()[0]
                    if esperando or not segundo.is_alive():
                        break
                self.assertTrue(esperando, "No se observó la espera real en PostgreSQL.")
                self.assertNotEqual(pids["operacion-primera"], pids["operacion-segunda"])
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    self.assertNotIn(cursor.fetchone()[0], pids.values())
            finally:
                liberar.set()
                for hilo in hilos:
                    hilo.join(timeout=15)
                self.assertFalse(any(hilo.is_alive() for hilo in hilos), "Una operación quedó bloqueada.")
        self.assertEqual(resultados.qsize(), 2)
        return dict(resultados.get_nowait() for _ in range(2))

    def assert_ambas_validas(self, resultados):
        for resultado in resultados.values():
            self.assertIsInstance(resultado, int, repr(resultado))

    def test_dos_modificaciones_misma_reserva_ultima_escritura_valida(self):
        reserva = self.crear_reserva(self.mesa1)
        resultados = self.ejecutar_operaciones(
            lambda: modificar_reserva(reserva.pk, {"cantidad_personas": 3}),
            lambda: modificar_reserva(reserva.pk, {"cantidad_personas": 4}),
        )
        self.assert_ambas_validas(resultados)
        reserva.refresh_from_db()
        self.assertEqual(reserva.cantidad_personas, 4)

    def test_reasignaciones_mismo_destino_solo_una_valida(self):
        primera = self.crear_reserva(self.mesa1)
        segunda = self.crear_reserva(self.mesa2)
        resultados = self.ejecutar_operaciones(
            lambda: modificar_reserva(primera.pk, {"mesa_id": self.mesa3.pk}),
            lambda: modificar_reserva(segunda.pk, {"mesa_id": self.mesa3.pk}),
            punto="_elegir_mesa_modificacion",
        )
        self.assertIsInstance(resultados["operacion-primera"], int)
        self.assertIsInstance(resultados["operacion-segunda"], ConflictoReserva)
        primera.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual(primera.mesa_id, self.mesa3.pk)
        self.assertEqual(segunda.mesa_id, self.mesa2.pk)

    def test_reasignaciones_opuestas_no_interbloquean(self):
        primera = self.crear_reserva(self.mesa1)
        segunda = self.crear_reserva(self.mesa2)
        resultados = self.ejecutar_operaciones(
            lambda: modificar_reserva(primera.pk, {"mesa_id": self.mesa2.pk}),
            lambda: modificar_reserva(segunda.pk, {"mesa_id": self.mesa1.pk}),
            punto="_elegir_mesa_modificacion",
        )
        for resultado in resultados.values():
            self.assertIsInstance(resultado, ConflictoReserva, repr(resultado))
        primera.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual(primera.mesa_id, self.mesa1.pk)
        self.assertEqual(segunda.mesa_id, self.mesa2.pk)

    def test_modificacion_seguida_de_cancelacion(self):
        reserva = self.crear_reserva(self.mesa1)
        resultados = self.ejecutar_operaciones(
            lambda: modificar_reserva(reserva.pk, {"cantidad_personas": 3}),
            lambda: cancelar_reserva(reserva.pk),
        )
        self.assert_ambas_validas(resultados)
        reserva.refresh_from_db()
        self.assertEqual(reserva.cantidad_personas, 3)
        self.assertEqual(reserva.estado, "CANCELADA")

    def test_cancelacion_seguida_de_modificacion_rechazada(self):
        reserva = self.crear_reserva(self.mesa1)
        resultados = self.ejecutar_operaciones(
            lambda: cancelar_reserva(reserva.pk),
            lambda: modificar_reserva(reserva.pk, {"cantidad_personas": 3}),
        )
        self.assertIsInstance(resultados["operacion-primera"], int)
        self.assertIsInstance(resultados["operacion-segunda"], ValidationError)
        reserva.refresh_from_db()
        self.assertEqual(reserva.cantidad_personas, 2)
        self.assertEqual(reserva.estado, "CANCELADA")

    def test_copy_on_write_concurrente_recuenta_cliente(self):
        primera = self.crear_reserva(self.mesa1)
        segunda = self.crear_reserva(self.mesa2, cliente=primera.cliente)
        cliente_original = primera.cliente_id
        resultados = self.ejecutar_operaciones(
            lambda: modificar_reserva(primera.pk, {}, {"nombre": "María"}),
            lambda: modificar_reserva(segunda.pk, {}, {"nombre": "Juana"}),
            punto="_actualizar_contacto",
        )
        self.assert_ambas_validas(resultados)
        primera.refresh_from_db()
        segunda.refresh_from_db()
        self.assertNotEqual(primera.cliente_id, cliente_original)
        self.assertEqual(segunda.cliente_id, cliente_original)
        self.assertEqual(primera.cliente.nombre, "María")
        self.assertEqual(segunda.cliente.nombre, "Juana")
        self.assertEqual(Cliente.objects.count(), 2)

    def test_registro_y_reasignacion_respetan_mismo_bloqueo(self):
        reserva = self.crear_reserva(self.mesa3)
        resultados = self.ejecutar_operaciones(
            lambda: modificar_reserva(reserva.pk, {"cantidad_personas": 3}),
            lambda: registrar_reserva(nombre="Luis", telefono="88881234", fecha=self.fecha, hora=time(12), cantidad_personas=2),
            punto="_bloquear_candidatas",
        )
        self.assert_ambas_validas(resultados)
        reserva.refresh_from_db()
        nueva = Reserva.objects.get(pk=resultados["operacion-segunda"])
        self.assertEqual(reserva.mesa_id, self.mesa1.pk)
        self.assertEqual(nueva.mesa_id, self.mesa2.pk)
