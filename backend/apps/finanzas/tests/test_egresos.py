from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.finanzas import services_egresos as services, consultas_egresos as consultas
from apps.finanzas.models import Egreso, EgresoEvento
from apps.finanzas.serializers_egresos import EgresoLecturaSerializer
from apps.finanzas.validaciones import hoy_santiago, LIMITE
from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from .base import FinanzasBase

URL = '/api/finanzas/egresos/'
RESUMEN = '/api/finanzas/flujo-dinero/resumen/'


def payload(**changes):
    return {'monto': '100.25', 'fecha_pago': hoy_santiago().isoformat(), 'categoria': 'MATERIALES',
            'concepto': ' Material pagado ', 'beneficiario': ' Comercio de ejemplo ',
            'medio': 'TRANSFERENCIA', 'referencia_respaldo': ' COMPROBANTE-EXTERNO ', **changes}


class EgresosBase(FinanzasBase):
    def crear_egreso(self, **changes):
        return services.registrar_egreso(payload(**changes), self.finanzas, str(uuid4()))[0]

    def post_egreso(self, data=None, key=None):
        return self.client.post(URL, payload() if data is None else data, format='json',
                                HTTP_IDEMPOTENCY_KEY=key or str(uuid4()))


class EgresosAPITests(EgresosBase, TestCase):
    def setUp(self):
        self.preparar_finanzas()

    def test_alta_replay_tras_anulacion_respuesta_original_y_get_actual(self):
        key = str(uuid4())
        r = self.post_egreso(key=key)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r['Idempotency-Replayed'], 'false')
        original = dict(r.data)
        self.assertEqual(set(original), set(EgresoLecturaSerializer().fields))
        self.assertEqual(original['concepto'], 'Material pagado')
        self.assertEqual(original['beneficiario'], 'Comercio de ejemplo')
        self.assertEqual(original['moneda'], 'CLP')
        self.assertIsNone(original['obra'])
        ruta = f'{URL}{original["id"]}/'
        r = self.client.post(ruta + 'anular/', {'motivo': ' Error de registro ', 'referencia_correccion': ' RECT-1 '}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data['activo'])
        r = self.post_egreso(key=key)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Idempotency-Replayed'], 'true')
        self.assertEqual(r.data, original)
        self.assertFalse(self.client.get(ruta).data['activo'])
        self.assertEqual(self.client.get(ruta + 'historial/').data['count'], 2)
        self.assertEqual(Egreso.objects.count(), 1)
        self.assertEqual(EgresoEvento.objects.count(), 2)
        r = self.post_egreso(payload(monto='100.26'), key=key)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['code'], 'idempotencia_conflictiva')
        r = self.client.post(ruta + 'anular/', {'motivo': 'Reintento', 'referencia_correccion': 'RECT-2'}, format='json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['code'], 'egreso_ya_anulado')

    def test_seis_roles_jwt_manipulado_flags_y_servicios(self):
        e = self.crear_egreso()
        for rol in Usuario.Rol:
            actor = Usuario.objects.create_user(username=f'eg_{rol}', email=f'{rol}@eg.test', rol=rol, is_staff=True, is_superuser=True)
            token = AccessToken.for_user(actor)
            token['rol'] = 'ADMINISTRATIVO_FINANZAS'
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
            permitido = rol in ['GERENCIA', 'ADMINISTRATIVO_FINANZAS']
            for ruta in [URL, f'{URL}{e.pk}/', f'{URL}{e.pk}/historial/', RESUMEN + f'?desde={hoy_santiago()}&hasta={hoy_santiago()}']:
                for metodo in ['get', 'head', 'options']:
                    self.assertEqual(getattr(self.client, metodo)(ruta).status_code, 200 if permitido else 403, (rol, metodo, ruta))
            self.assertEqual(self.post_egreso().status_code, 201 if rol == 'ADMINISTRATIVO_FINANZAS' else 403)
            propio = self.crear_egreso()
            self.assertEqual(self.client.post(f'{URL}{propio.pk}/anular/',
                {'motivo': 'Error', 'referencia_correccion': 'R'}, format='json').status_code,
                200 if rol == 'ADMINISTRATIVO_FINANZAS' else 403)
            actor.rol = 'ADMINISTRATIVO_FINANZAS'
            if rol != 'ADMINISTRATIVO_FINANZAS':
                with self.assertRaises(PermissionDenied):
                    services.registrar_egreso(payload(), actor, str(uuid4()))
                with self.assertRaises(PermissionDenied):
                    services.anular_egreso(e.pk, {'motivo': 'No', 'referencia_correccion': 'No'}, actor)
            if not permitido:
                with self.assertRaises(PermissionDenied):
                    consultas.obtener(actor, e.pk)
                with self.assertRaises(PermissionDenied):
                    consultas.resumen(actor, {})

    def test_sin_jwt_revocacion_inactividad_y_rol_persistido(self):
        self.client.credentials()
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.autenticar(self.finanzas)
        Usuario.objects.filter(pk=self.finanzas.pk).update(sesion_version=self.finanzas.sesion_version + 1)
        self.assertEqual(self.post_egreso().status_code, 401)
        self.finanzas.refresh_from_db()
        self.autenticar(self.finanzas)
        Usuario.objects.filter(pk=self.finanzas.pk).update(is_active=False)
        self.assertEqual(self.client.get(URL).status_code, 401)
        with self.assertRaises(AuthenticationFailed):
            services.registrar_egreso(payload(), self.finanzas, str(uuid4()))
        Usuario.objects.filter(pk=self.finanzas.pk).update(is_active=True, rol='TECNICO')
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_campos_desconocidos_servidor_y_tipos_estrictos(self):
        for campo, valor in [('actor', 1), ('activo', False), ('obra_id', 1), ('registrado_por', 1),
                             ('clave_idempotencia', str(uuid4())), ('huella_solicitud', 'a' * 64),
                             ('anulado_en', '2026-01-01'), ('moneda', 'USD'), ('saldo', '1'), ('monto_neto', '1')]:
            r = self.post_egreso(payload(**{campo: valor}))
            self.assertEqual(r.status_code, 400, (campo, r.data))
        for campo, valores in [('monto', [1, 1.5, True, None, '0', '-1', '+1', '1e2', 'NaN', 'Infinity', '1.001', '1,00', str(LIMITE) + '0']),
                                ('fecha_pago', ['2026-02-30', '2026-1-01', (hoy_santiago() + timedelta(days=1)).isoformat(), True]),
                                ('categoria', ['INVENTADA', 1]), ('medio', ['BANCO', True]),
                                ('concepto', [1, True, '', '  ', 'x' * 201]), ('beneficiario', [1, None, '', 'x' * 201]),
                                ('referencia_respaldo', ['', None, 'x' * 501]), ('observacion', [None, True, 'x' * 2001]),
                                ('obra', [True, '1', 1.0, -1, 0, 9223372036854775808])]:
            for valor in valores:
                r = self.post_egreso(payload(**{campo: valor}))
                self.assertEqual(r.status_code, 400, (campo, valor, r.data))
        self.assertEqual(Egreso.objects.count(), 0)
        self.assertEqual(EgresoEvento.objects.count(), 0)

    def test_uuid_obligatorio_y_formato(self):
        for key in ['', 'no-uuid', '0' * 32, str(uuid4()) + ' ', 123]:
            r = self.client.post(URL, payload(), format='json', HTTP_IDEMPOTENCY_KEY=key)
            self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post(URL, payload(), format='json').status_code, 400)

    def test_obra_opcional_informativa_existente_y_fuera_de_ambito(self):
        # No exigir FINALIZADA: asociación informativa, no regla documental 007.
        otra = self.otra_obra()
        r = self.post_egreso(payload(obra=otra.pk))
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['obra'], otra.pk)
        self.assertEqual(self.post_egreso(payload(obra=999999)).status_code, 400)
        self.autenticar(self.tecnico)
        for pk in [otra.pk, 999999]:
            self.assertEqual(self.post_egreso(payload(obra=pk)).status_code, 403)

    def test_montos_limite_minimo_categorias_y_medios(self):
        for monto in ['0.01', format(LIMITE, '.2f')]:
            r = self.post_egreso(payload(monto=monto))
            self.assertEqual(r.status_code, 201, r.data)
            self.assertEqual(r.data['monto'], monto)
        for categoria in Egreso.Categoria.values:
            for medio in ['TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'OTRO']:
                self.assertEqual(self.post_egreso(payload(categoria=categoria, medio=medio)).status_code, 201)

    def test_fecha_civil_santiago_no_dia_utc_en_ambos_offsets(self):
        for mes, dia in [(4, 10), (11, 21)]:
            ahora = datetime(2026, mes, dia, 1, tzinfo=datetime_timezone.utc)
            with patch('django.utils.timezone.now', return_value=ahora):
                self.assertEqual(self.post_egreso(payload(fecha_pago=ahora.date().isoformat())).status_code, 400)
                fecha_local = (ahora.date() - timedelta(days=1)).isoformat()
                r = self.post_egreso(payload(fecha_pago=fecha_local))
                self.assertEqual(r.status_code, 201, r.data)
                self.assertEqual(r.data['fecha_pago'], fecha_local)

    def test_paginacion_orden_filtros_y_lecturas_sin_escrituras(self):
        for _ in range(27):
            self.crear_egreso()
        r = self.client.get(URL)
        self.assertEqual((r.data['count'], len(r.data['results'])), (27, 25))
        self.assertIsNotNone(r.data['next'])
        ids = [x['id'] for x in r.data['results']]
        self.assertEqual(ids, sorted(ids, reverse=True))
        self.assertEqual(len(self.client.get(r.data['next']).data['results']), 2)
        e = Egreso.objects.first()
        services.anular_egreso(e.pk, {'motivo': 'Error', 'referencia_correccion': 'R'}, self.finanzas)
        for filtros, n in [({'activo': 'false'}, 1), ({'activo': 'true'}, 26), ({'medio': 'EFECTIVO'}, 0),
                            ({'obra': str(self.obra.pk)}, 0), ({'categoria': 'MATERIALES'}, 27),
                            ({'desde': str(hoy_santiago()), 'hasta': str(hoy_santiago())}, 27)]:
            self.assertEqual(self.client.get(URL, filtros).data['count'], n)
        with CaptureQueriesContext(connection) as q:
            for ruta in [URL, f'{URL}{e.pk}/', f'{URL}{e.pk}/historial/']:
                r = self.client.get(ruta)
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r['Cache-Control'], 'private, no-store')
                self.assertIn('Authorization', r['Vary'])
        self.assertFalse(any(x['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for x in q))

    def test_query_estricta_por_ruta_y_metodos(self):
        e = self.crear_egreso()
        for query in ['x=1', 'activo=', 'activo=1', 'medio=OTRA', 'categoria=x', 'obra=0', 'obra=true',
                      'desde=2026-01-01', 'hasta=2026-01-01', 'desde=2026-02-30&hasta=2026-03-01',
                      'desde=2024-01-01&hasta=2025-01-01', 'desde=2026-02-01&hasta=2026-01-01',
                      'page=0', 'page=last', 'page=01', 'page=1&page=2', 'activo=true&activo=false']:
            self.assertEqual(self.client.get(URL + '?' + query).status_code, 400, query)
        self.assertEqual(self.client.get(URL + '?page=999').status_code, 404)
        for ruta in [f'{URL}{e.pk}/', RESUMEN]:
            self.assertEqual(self.client.get(ruta, {'page': 1}).status_code, 400)
        for metodo in ['put', 'patch', 'delete']:
            self.assertEqual(getattr(self.client, metodo)(f'{URL}{e.pk}/', {}, format='json').status_code, 405)
        for sufijo in ['', 'historial/']:
            self.assertEqual(self.client.get(URL + '999999/' + sufijo).status_code, 404)
        self.assertEqual(self.client.post(URL + '999999/anular/', {'motivo': 'Error', 'referencia_correccion': 'R'}, format='json').status_code, 404)

    def test_anulacion_body_exacto_y_sin_efectos_parciales(self):
        e = self.crear_egreso()
        for data in [{}, {'motivo': 'X'}, {'motivo': '', 'referencia_correccion': 'R'},
                     {'motivo': 'X', 'referencia_correccion': ''}, {'motivo': 'X', 'referencia_correccion': 'R', 'activo': False}]:
            self.assertEqual(self.client.post(f'{URL}{e.pk}/anular/', data, format='json').status_code, 400)
        self.assertTrue(Egreso.objects.get(pk=e.pk).activo)
        self.assertEqual(e.eventos.count(), 1)


class EgresosIntegridadTests(EgresosBase, TestCase):
    def setUp(self):
        self.preparar_finanzas()

    def test_idempotencia_payload_normalizado_y_clave_independiente_de_pagos(self):
        key = str(uuid4())
        e, creado = services.registrar_egreso(payload(), self.finanzas, key)
        otro, nuevo = services.registrar_egreso(payload(monto='100.250'.rstrip('0'), observacion='', obra=None,
            concepto='Material pagado', beneficiario='Comercio de ejemplo', referencia_respaldo='COMPROBANTE-EXTERNO'), self.finanzas, key.upper())
        self.assertTrue(creado)
        self.assertFalse(nuevo)
        self.assertEqual(otro.pk, e.pk)
        self.assertEqual(e.eventos.count(), 1)

    def test_modelos_inmutables_y_eventos_append_only(self):
        e = self.crear_egreso()
        for obj in [e, e.eventos.get()]:
            for accion in [obj.save, obj.delete, lambda: type(obj).objects.filter(pk=obj.pk).update(motivo='No'),
                           lambda: type(obj).objects.filter(pk=obj.pk).delete(), lambda: type(obj).objects.bulk_update([obj], ['id'])]:
                with self.assertRaises(DjangoValidationError):
                    accion()

    def test_constraints_sql_sin_validacion_python(self):
        e = self.crear_egreso()
        for cambios in [{'monto': Decimal('0')}, {'monto': Decimal('-1')}, {'categoria': 'NO'}, {'medio': 'NO'},
                        {'concepto': ''}, {'beneficiario': ' Comercio '}, {'referencia_respaldo': ''},
                        {'observacion': ' Con espacios '}, {'huella_solicitud': 'x' * 64}, {'activo': False},
                        {'anulado_por_id': self.finanzas.pk}, {'fecha_pago': hoy_santiago() + timedelta(days=1)}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                models.QuerySet(model=Egreso).filter(pk=e.pk).update(**cambios)
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as c:
            c.execute('UPDATE finanzas_egreso SET monto = %s::numeric WHERE id = %s', ['NaN', e.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            EgresoEvento.objects.create(egreso=e, actor=self.finanzas, tipo='CREACION')
        with self.assertRaises(IntegrityError), transaction.atomic():
            EgresoEvento.objects.create(egreso=e, actor=self.finanzas, tipo='ANULACION', motivo='')

    def test_fallo_evento_revierte_alta_y_anulacion(self):
        with patch('apps.finanzas.services_egresos.EgresoEvento.objects.create', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.crear_egreso()
        self.assertFalse(Egreso.objects.exists())
        e = self.crear_egreso()
        with patch('apps.finanzas.services_egresos.EgresoEvento.objects.create', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                services.anular_egreso(e.pk, {'motivo': 'Error', 'referencia_correccion': 'R'}, self.finanzas)
        e.refresh_from_db()
        self.assertTrue(e.activo)
        self.assertEqual(e.eventos.count(), 1)

    def test_integrity_inesperado_no_se_oculta_y_actor_ausente_deniega(self):
        with patch.object(services, '_registrar', side_effect=IntegrityError('inesperado')):
            with self.assertRaises(IntegrityError):
                self.crear_egreso()
        for actor in [None, 'ADMINISTRATIVO_FINANZAS', Usuario(pk=self.finanzas.pk)]:
            with self.assertRaises(PermissionDenied):
                services.registrar_egreso(payload(), actor, str(uuid4()))
