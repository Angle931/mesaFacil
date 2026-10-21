from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .exceptions import ConflictoReserva, GeneracionCodigoAgotada, ReservaNoEncontrada, ReservaServiceError, SinDisponibilidad
from .models import Cliente, Mesa, Reserva
from .services import cancelar_reserva, cambiar_estado_reserva, confirmar_reserva, consultar_mesas_disponibles, modificar_reserva, registrar_reserva


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


class ModificacionReservaTests(TestCase):
    def setUp(self):
        self.ahora = timezone.make_aware(datetime(2030, 5, 10, 13), timezone.get_default_timezone())
        reloj = patch("django.utils.timezone.now", side_effect=lambda: self.ahora)
        reloj.start()
        self.addCleanup(reloj.stop)
        self.mesa = Mesa.objects.create(numero="A1", capacidad=4)
        self.reserva = registrar_reserva(
            nombre="Ana", telefono="88881234", correo="ana@example.com",
            fecha=self.ahora.date() + timedelta(days=1), hora=time(12), cantidad_personas=2,
        )

    def compartir_cliente(self, estado="PENDIENTE"):
        return Reserva.objects.create(
            cliente=self.reserva.cliente, mesa=self.mesa, fecha=self.reserva.fecha,
            hora=time(13), cantidad_personas=2, estado=estado,
        )

    def modificar(self, cambios=None, contacto=None):
        return modificar_reserva(self.reserva.pk, cambios or {}, contacto)

    def test_sin_cambios_no_guarda(self):
        with patch.object(Reserva, "save") as guardar, patch.object(Cliente, "save") as guardar_cliente:
            resultado = self.modificar()
            self.modificar(contacto={})
            guardar.assert_not_called()
            guardar_cliente.assert_not_called()
        self.assertEqual(resultado.pk, self.reserva.pk)
        self.assertEqual(resultado.mesa_id, self.mesa.pk)

    def test_contacto_exclusivo_sin_cambio_ocupacion(self):
        menor = Mesa.objects.create(numero="A2", capacidad=2)
        resultado = self.modificar(contacto={"nombre": "  María  ", "correo": ""})
        self.assertEqual(resultado.cliente_id, self.reserva.cliente_id)
        self.assertEqual(resultado.cliente.nombre, "María")
        self.assertEqual(resultado.cliente.correo, "")
        self.assertNotEqual(resultado.mesa_id, menor.pk)
        self.assertEqual(Cliente.objects.count(), 1)

    def test_copy_on_write_conserva_las_otras_reservas(self):
        otra = self.compartir_cliente(estado="CANCELADA")
        resultado = self.modificar(contacto={"nombre": "María"})
        otra.refresh_from_db()
        self.assertNotEqual(resultado.cliente_id, otra.cliente_id)
        self.assertEqual(resultado.cliente.nombre, "María")
        self.assertEqual(resultado.cliente.correo, "ana@example.com")
        self.assertEqual(otra.cliente.nombre, "Ana")
        self.assertEqual(Cliente.objects.count(), 2)

    def test_contacto_equivalente_no_copia_ni_actualiza(self):
        self.compartir_cliente()
        with patch.object(Cliente, "save") as guardar_cliente, patch.object(Reserva, "save") as guardar:
            resultado = self.modificar(contacto={"nombre": " Ana ", "telefono": "8888-1234", "correo": " ana@example.com "})
            guardar.assert_not_called()
            guardar_cliente.assert_not_called()
        self.assertEqual(resultado.cliente_id, self.reserva.cliente_id)
        self.assertEqual(Cliente.objects.count(), 1)

    def test_no_modifica_diccionarios_recibidos(self):
        cambios = {"cantidad_personas": "3"}
        contacto = {"nombre": "  María  "}
        modificar_reserva(self.reserva.pk, cambios, contacto)
        self.assertEqual(cambios, {"cantidad_personas": "3"})
        self.assertEqual(contacto, {"nombre": "  María  "})

    def test_normaliza_antes_de_detectar_cambios(self):
        Mesa.objects.create(numero="A2", capacidad=2)
        with patch.object(Reserva, "save") as guardar:
            resultado = self.modificar({"fecha": str(self.reserva.fecha), "hora": "12:00", "cantidad_personas": "2", "mesa_id": str(self.mesa.pk)})
            guardar.assert_not_called()
        self.assertEqual(resultado.mesa_id, self.mesa.pk)

    def test_reprogramacion_conserva_mesa_si_es_la_mejor(self):
        resultado = self.modificar({"hora": time(13)})
        self.assertEqual(resultado.mesa_id, self.mesa.pk)
        self.assertEqual(resultado.hora, time(13))

    def test_reasignacion_automatica_al_cambiar_cantidad(self):
        menor = Mesa.objects.create(numero="Z9", capacidad=3)
        Mesa.objects.create(numero="A0", capacidad=3)
        resultado = self.modificar({"cantidad_personas": 3})
        self.assertEqual(resultado.mesa_id, menor.pk)

    def test_mesa_explicita_no_sustituida_por_menor(self):
        Mesa.objects.create(numero="A2", capacidad=2)
        resultado = self.modificar({"hora": time(13), "mesa_id": self.mesa.pk})
        self.assertEqual(resultado.mesa_id, self.mesa.pk)

    def test_mesa_explicita_valida_y_exclusion_propia(self):
        resultado = self.modificar({"cantidad_personas": 3, "mesa_id": self.mesa.pk})
        self.assertEqual(resultado.cantidad_personas, 3)
        otra = Mesa.objects.create(numero="A2", capacidad=4)
        self.assertEqual(self.modificar({"mesa_id": otra.pk}).mesa_id, otra.pk)

    def test_mesas_explicitas_invalidas(self):
        inactiva = Mesa.objects.create(numero="A2", capacidad=4, activa=False)
        insuficiente = Mesa.objects.create(numero="A3", capacidad=1)
        for mesa_id in (999999, inactiva.pk, insuficiente.pk):
            with self.subTest(mesa_id=mesa_id):
                with self.assertRaises(ValidationError) as error:
                    self.modificar({"mesa_id": mesa_id})
                self.assertIn("mesa_id", error.exception.message_dict)
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.mesa_id, self.mesa.pk)

    def test_conflicto_explicito_no_modifica_contacto(self):
        otra_mesa = Mesa.objects.create(numero="A2", capacidad=4)
        Reserva.objects.create(cliente=self.reserva.cliente, mesa=otra_mesa, fecha=self.reserva.fecha, hora=time(12), cantidad_personas=2)
        with self.assertRaises(ConflictoReserva):
            self.modificar({"mesa_id": otra_mesa.pk}, {"nombre": "María"})
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.cliente.nombre, "Ana")
        self.assertEqual(Cliente.objects.count(), 1)

    def test_sin_disponibilidad_automatica(self):
        self.compartir_cliente()
        with self.assertRaises(SinDisponibilidad):
            self.modificar({"hora": time(13)})
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.hora, time(12))

    def test_rechaza_contenedores_y_campos_no_permitidos(self):
        for cambios in (None, [], "fecha", {"estado": "CANCELADA"}, {"cliente": 1}, {"cliente_id": 1}, {"codigo_confirmacion": "A" * 16}, {"extra": 1}):
            with self.subTest(cambios=cambios):
                with self.assertRaises(ValidationError):
                    modificar_reserva(self.reserva.pk, cambios)
        for contacto in ([], "Ana", {"id": 1}, {"cliente_id": 1}, {"extra": "x"}):
            with self.subTest(contacto=contacto):
                with self.assertRaises(ValidationError):
                    self.modificar(contacto=contacto)

    def test_rechaza_valores_nulos_e_invalidos(self):
        for campo in ("fecha", "hora", "cantidad_personas", "mesa_id"):
            with self.subTest(campo=campo):
                with self.assertRaises(ValidationError):
                    self.modificar({campo: None})
        for campo in ("nombre", "telefono", "correo"):
            with self.subTest(campo=campo):
                with self.assertRaises(ValidationError):
                    self.modificar(contacto={campo: None})
        for cantidad in (True, 1.5, 0, -1):
            with self.subTest(cantidad=cantidad):
                with self.assertRaises(ValidationError):
                    self.modificar({"cantidad_personas": cantidad})

    def test_reserva_no_encontrada_e_identificador_invalido(self):
        for funcion, args in ((modificar_reserva, ({},)), (cambiar_estado_reserva, ("CONFIRMADA",)), (confirmar_reserva, ()), (cancelar_reserva, ())):
            with self.subTest(funcion=funcion.__name__):
                with self.assertRaises(ReservaNoEncontrada):
                    funcion(999999, *args)
                with self.assertRaises(ValidationError):
                    funcion(None, *args)

    def test_estados_finales_solo_admiten_contacto_y_valores_equivalentes(self):
        for estado in ("CANCELADA", "COMPLETADA"):
            with self.subTest(estado=estado):
                Reserva.objects.filter(pk=self.reserva.pk).update(estado=estado, fecha=self.ahora.date() - timedelta(days=1))
                self.reserva.refresh_from_db()
                for cambios in ({"fecha": self.reserva.fecha + timedelta(days=3)}, {"hora": time(13)}, {"cantidad_personas": 3}, {"mesa_id": 999999}):
                    with self.assertRaises(ValidationError):
                        self.modificar(cambios)
                self.modificar({"cantidad_personas": "2", "hora": "12:00"})
                self.assertEqual(self.modificar(contacto={"nombre": "María"}).cliente.nombre, "María")

    def test_pasadas_no_finales_no_admiten_ocupacion(self):
        for estado in ("PENDIENTE", "CONFIRMADA"):
            with self.subTest(estado=estado):
                Reserva.objects.filter(pk=self.reserva.pk).update(estado=estado, fecha=self.ahora.date() - timedelta(days=1))
                for cambios in ({"hora": time(13)}, {"fecha": self.ahora.date() + timedelta(days=2)}, {"cantidad_personas": 3}, {"mesa_id": 999999}):
                    with self.assertRaises(ValidationError):
                        self.modificar(cambios)
                self.assertEqual(self.modificar(contacto={"nombre": "María"}).cliente.nombre, "María")

    def test_copy_on_write_contacto_en_estado_final(self):
        otra = self.compartir_cliente()
        Reserva.objects.filter(pk=self.reserva.pk).update(estado="CANCELADA")
        resultado = self.modificar(contacto={"correo": "nuevo@example.com"})
        self.assertNotEqual(resultado.cliente_id, otra.cliente_id)
        self.assertEqual(otra.cliente.correo, "ana@example.com")

    def test_codigo_estable_sin_generador(self):
        codigo = self.reserva.codigo_confirmacion
        with patch("reservas.services.generar_codigo_confirmacion") as generar:
            self.modificar({"hora": time(13)})
            confirmar_reserva(self.reserva.pk)
            cancelar_reserva(self.reserva.pk)
            generar.assert_not_called()
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.codigo_confirmacion, codigo)

    def test_transiciones_validas_e_invalidas(self):
        permitidas = {"PENDIENTE": {"CONFIRMADA", "CANCELADA"}, "CONFIRMADA": {"COMPLETADA", "CANCELADA"}, "COMPLETADA": set(), "CANCELADA": set()}
        Reserva.objects.filter(pk=self.reserva.pk).update(fecha=self.ahora.date() - timedelta(days=1))
        for origen in Reserva.Estado.values:
            for destino in Reserva.Estado.values:
                with self.subTest(origen=origen, destino=destino):
                    Reserva.objects.filter(pk=self.reserva.pk).update(estado=origen)
                    if destino == origen or destino in permitidas[origen]:
                        self.assertEqual(cambiar_estado_reserva(self.reserva.pk, destino).estado, destino)
                    else:
                        with self.assertRaises(ValidationError):
                            cambiar_estado_reserva(self.reserva.pk, destino)

    def test_estado_actual_idempotente_sin_save(self):
        with patch.object(Reserva, "save") as guardar:
            self.assertEqual(cambiar_estado_reserva(self.reserva.pk, "PENDIENTE").estado, "PENDIENTE")
            guardar.assert_not_called()

    def test_estado_invalido(self):
        for estado in (None, "", "OTRO"):
            with self.subTest(estado=estado):
                with self.assertRaises(ValidationError):
                    cambiar_estado_reserva(self.reserva.pk, estado)

    def test_completar_antes_y_en_el_inicio(self):
        confirmar_reserva(self.reserva.pk)
        with self.assertRaises(ValidationError):
            cambiar_estado_reserva(self.reserva.pk, "COMPLETADA")
        self.ahora = timezone.make_aware(datetime.combine(self.reserva.fecha, self.reserva.hora), timezone.get_default_timezone())
        self.assertEqual(cambiar_estado_reserva(self.reserva.pk, "COMPLETADA").estado, "COMPLETADA")

    def test_wrappers_delegan(self):
        with patch("reservas.services.cambiar_estado_reserva", return_value=self.reserva) as cambiar:
            self.assertIs(confirmar_reserva(self.reserva.pk), self.reserva)
            cambiar.assert_called_with(self.reserva.pk, "CONFIRMADA")
            self.assertIs(cancelar_reserva(self.reserva.pk), self.reserva)
            cambiar.assert_called_with(self.reserva.pk, "CANCELADA")

    def test_fallo_posterior_revierte_ocupacion_y_contacto(self):
        for compartido in (False, True):
            with self.subTest(compartido=compartido):
                otra = self.compartir_cliente() if compartido else None
                cliente_id = self.reserva.cliente_id
                total = Cliente.objects.count()
                with patch.object(Reserva, "full_clean", side_effect=ValidationError("fallo posterior")):
                    with self.assertRaises(ValidationError):
                        self.modificar({"hora": time(14)}, {"nombre": "María"})
                self.reserva.refresh_from_db()
                self.assertEqual(self.reserva.hora, time(12))
                self.assertEqual(self.reserva.cliente_id, cliente_id)
                self.assertEqual(self.reserva.cliente.nombre, "Ana")
                self.assertEqual(Cliente.objects.count(), total)
                if otra:
                    otra.delete()

    def test_integrityerror_desconocido_se_propaga_y_revierte(self):
        guardar = Reserva.save

        def guardar_invalida(reserva, *args, **kwargs):
            reserva.cantidad_personas = 0
            return guardar(reserva, *args, **kwargs)

        with patch.object(Reserva, "save", guardar_invalida):
            with self.assertRaises(IntegrityError):
                self.modificar({"hora": time(14)}, {"nombre": "María"})
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.hora, time(12))
        self.assertEqual(self.reserva.cliente.nombre, "Ana")

    def test_conflicto_postgresql_se_traduce_y_revierte(self):
        self.compartir_cliente()
        with patch.object(Reserva, "full_clean"), patch("reservas.services._mesas_ocupadas", return_value=Reserva.objects.none().values_list("mesa_id", flat=True)):
            with self.assertRaises(ConflictoReserva):
                self.modificar({"hora": time(13), "mesa_id": self.mesa.pk}, {"nombre": "María"})
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.hora, time(12))
        self.assertEqual(Cliente.objects.count(), 1)

    def test_espera_que_alcanza_inicio_impide_modificar(self):
        from .services import _elegir_mesa_modificacion

        def esperar(*args):
            mesa = _elegir_mesa_modificacion(*args)
            self.ahora += timedelta(days=2)
            return mesa

        with patch("reservas.services._elegir_mesa_modificacion", side_effect=esperar):
            with self.assertRaises(ValidationError):
                self.modificar({"hora": time(14)}, {"nombre": "María"})
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.hora, time(12))
        self.assertEqual(self.reserva.cliente.nombre, "Ana")
