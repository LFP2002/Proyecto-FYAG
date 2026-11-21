from uuid import uuid4

from django.db import connection, transaction, IntegrityError
from django.test import TestCase

from apps.inventario.models import Merma, MermaEvento as Evento, OperacionMaterial as Op, MovimientoInventario as Movimiento
from .test_mermas import MermasBase


class IntegridadMermasTests(MermasBase, TestCase):
    def setUp(self):
        self.preparar_mermas()
        self.preparar_entrega()

    def test_original_eventos_no_mutan_ni_reabren_sql(self):
        for ambito in ['BODEGA', 'OBRA']:
            m = self.resolver(self.informar(ambito))
            for columna, valor in [('cantidad', '1.000'), ('estado', 'PENDIENTE'), ('motivo', 'Otro'), ('informado_por_id', self.tecnico.pk)]:
                with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as c:
                    c.execute(f'UPDATE inventario_merma SET {columna}=%s WHERE id=%s', [valor, m.pk])
            for sql in ['DELETE FROM inventario_merma WHERE id=%s', 'DELETE FROM inventario_mermaevento WHERE merma_id=%s', "UPDATE inventario_mermaevento SET motivo='Cambio' WHERE merma_id=%s"]:
                with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as c:
                    c.execute(sql, [m.pk])

    def test_actor_falso_evento_decision_y_segunda_decision(self):
        m = self.informar('OBRA')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Evento.objects.create(merma=m, tipo='RECHAZO', actor=self.finanzas, motivo='Actor falso', clave_idempotencia=uuid4(), huella='a'*64)
        self.resolver(m, 'RECHAZAR')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Evento.objects.create(merma=m, tipo='APROBACION', actor=self.supervisor, motivo='Segunda', clave_idempotencia=uuid4(), huella='a'*64)

    def test_origen_mo_no_permite_entrega_obra_articulo_unidad_falsos(self):
        m = self.informar('OBRA')
        columnas = {f.attname: getattr(m, f.attname) for f in Merma._meta.concrete_fields if f.name != 'id'}
        for cambio in [{'entrega_id': self.autorizar().pk}, {'obra_id': self.otra_obra().pk}, {'unidad': 'otra'}, {'cantidad': '7.000'}, {'informado_por_id': self.bodega.pk}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Merma.objects.create(**{**columnas, 'clave_idempotencia': uuid4(), **cambio})

    def test_confirmacion_diferida_exige_evento_creacion(self):
        m = self.informar()
        columnas = {f.attname: getattr(m, f.attname) for f in Merma._meta.concrete_fields if f.name != 'id'}
        with self.assertRaises(IntegrityError), transaction.atomic():
            Merma.objects.create(**{**columnas, 'clave_idempotencia': uuid4()})
            with connection.cursor() as c:
                c.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_mb_efecto_huerfano_falla_al_commit_y_no_mueve_stock(self):
        m = self.informar()
        antes = self.saldo()
        with self.assertRaises(IntegrityError), transaction.atomic():
            op = Op.objects.create(tipo='MERMA', merma_bodega=m, articulo=m.articulo, cantidad=m.cantidad, unidad=m.unidad,
                actor=self.finanzas, clave_idempotencia=uuid4(), huella='a'*64, referencia=m.referencia,
                motivo=f'Merma de Bodega {m.pk}; informante {m.informado_por_id}', costo_unitario_neto='100.00',
                saldo_valorado_anterior='4.000', saldo_valorado_posterior='2.000', promedio_anterior='100.00', promedio_posterior='100.00')
            Movimiento.objects.create(tipo='MERMA', operacion=op, articulo=m.articulo, cantidad=m.cantidad, actor=self.finanzas,
                clave_idempotencia=op.clave_idempotencia, referencia=op.referencia, motivo=op.motivo, saldo_anterior='4.000', saldo_posterior='2.000')
            with connection.cursor() as c:
                c.execute('SET CONSTRAINTS ALL IMMEDIATE')
        self.assertEqual(self.saldo(), antes)

    def test_sql_devolucion_y_autorizacion_superan_mo_rechazadas(self):
        a = self.op('AUTORIZACION_DEVOLUCION', entrega=self.entrega.pk, cantidad='6.000')
        self.resolver(self.informar('OBRA', cantidad='5.000'))
        for tipo in ['AUTORIZACION_DEVOLUCION', 'DEVOLUCION']:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Op.objects.create(tipo=tipo, entrega=self.entrega, autorizacion=a if tipo == 'DEVOLUCION' else None,
                    obra=self.obra, articulo=self.article, unidad=self.entrega.unidad, cantidad='2.000',
                    actor=self.bodega if tipo == 'DEVOLUCION' else self.supervisor,
                    clave_idempotencia=uuid4(), huella='a'*64, referencia='QA', motivo='No devolver merma')

    def test_sql_clasificacion_supera_recibido_y_baja_falsa_rechazadas(self):
        self.devolver(self.entrega, '5.000')
        m = self.informar('OBRA')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Evento.objects.create(merma=m, tipo='APROBACION', actor=self.supervisor, motivo='Exceso', clave_idempotencia=uuid4(), huella='a'*64)
        mb = self.informar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Evento.objects.create(merma=mb, tipo='APROBACION', actor=self.finanzas, motivo='Sin operación', clave_idempotencia=uuid4(), huella='a'*64)

    def test_sql_saldo_no_conciliado_y_valoracion_manual_prohibidos(self):
        for tabla, columna in [('inventario_existenciainventario', 'saldo'), ('inventario_estadovaloracion', 'saldo_valorado')]:
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as c:
                c.execute(f'UPDATE {tabla} SET {columna}={columna}+1 WHERE articulo_id=%s', [self.article.pk])
                c.execute('SET CONSTRAINTS ALL IMMEDIATE')
