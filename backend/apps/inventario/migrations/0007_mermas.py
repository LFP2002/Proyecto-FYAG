from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q, F
from django.db.models.deletion import PROTECT
from django.db.models.functions import Trim
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [('inventario', '0006_integridad_solicitudes'), ('obras', '0012_origen_gasto_bodega'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='Merma', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('ambito', models.CharField(max_length=6, choices=[('BODEGA', 'Bodega'), ('OBRA', 'Obra')])),
            ('articulo', models.ForeignKey(to='inventario.articuloinventario', on_delete=PROTECT, related_name='mermas')),
            ('obra', models.ForeignKey(to='obras.obra', on_delete=PROTECT, null=True, blank=True, related_name='mermas')),
            ('entrega', models.ForeignKey(to='inventario.operacionmaterial', on_delete=PROTECT, null=True, blank=True, related_name='mermas_informadas')),
            ('unidad', models.CharField(max_length=30, editable=False)),
            ('cantidad', models.DecimalField(max_digits=12, decimal_places=3)),
            ('tipo', models.CharField(max_length=24)), ('motivo', models.CharField(max_length=2000)),
            ('referencia', models.CharField(max_length=150, blank=True, default='')),
            ('actividad', models.CharField(max_length=2000, blank=True, default='')),
            ('corte_movimiento', models.ForeignKey(to='inventario.movimientoinventario', on_delete=PROTECT, null=True, blank=True, editable=False, related_name='mermas_observadas')),
            ('informado_por', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name='mermas_informadas', editable=False)),
            ('clave_idempotencia', models.UUIDField(unique=True, editable=False)), ('huella', models.CharField(max_length=64, editable=False)),
            ('creado_en', models.DateTimeField(default=timezone.now, editable=False)),
            ('estado', models.CharField(max_length=9, default='PENDIENTE', choices=[('PENDIENTE', 'Pendiente'), ('APROBADA', 'Aprobada'), ('RECHAZADA', 'Rechazada')], editable=False)),
            ('decidido_por', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, null=True, blank=True, related_name='mermas_decididas', editable=False)),
            ('decidido_en', models.DateTimeField(null=True, blank=True, editable=False)),
            ('motivo_decision', models.CharField(max_length=2000, blank=True, default='', editable=False)),
            ('operacion', models.OneToOneField(to='inventario.operacionmaterial', on_delete=PROTECT, null=True, blank=True, related_name='merma_aprobada', editable=False)),
        ], options={'ordering': ['id'], 'constraints': [
            models.CheckConstraint(name='inv_merma_cantidad', condition=Q(cantidad__gt=0, cantidad__lte=Decimal('999999999.999'))),
            models.CheckConstraint(name='inv_merma_origen', condition=(
                (Q(ambito='BODEGA', obra__isnull=True, entrega__isnull=True, actividad='', tipo__in=['DANO', 'VENCIMIENTO', 'EXTRAVIO', 'DIFERENCIA_CONTEO', 'OTRA']) & ~Q(referencia=''))
                | (Q(ambito='OBRA', obra__isnull=False, entrega__isnull=False, corte_movimiento__isnull=True, operacion__isnull=True, tipo__in=['CORTE_NO_REUTILIZABLE', 'DANO_EN_OBRA', 'EXTRAVIO_EN_OBRA', 'OTRA']) & ~Q(actividad='')))),
            models.CheckConstraint(name='inv_merma_textos', condition=~Q(motivo='') & Q(motivo=Trim('motivo'), referencia=Trim('referencia'), actividad=Trim('actividad'), motivo_decision=Trim('motivo_decision')) & ~Q(motivo__regex=r'[[:cntrl:]]') & ~Q(referencia__regex=r'[[:cntrl:]]') & ~Q(actividad__regex=r'[[:cntrl:]]') & ~Q(motivo_decision__regex=r'[[:cntrl:]]')),
            models.CheckConstraint(name='inv_merma_huella', condition=Q(huella__regex=r'^[0-9a-f]{64}$')),
            models.CheckConstraint(name='inv_merma_decision', condition=(
                Q(estado='PENDIENTE', decidido_por__isnull=True, decidido_en__isnull=True, motivo_decision='', operacion__isnull=True)
                | (Q(estado='RECHAZADA', decidido_por__isnull=False, decidido_en__isnull=False, decidido_en__gte=F('creado_en'), operacion__isnull=True) & ~Q(motivo_decision=''))
                | (Q(estado='APROBADA', decidido_por__isnull=False, decidido_en__isnull=False, decidido_en__gte=F('creado_en')) & ~Q(motivo_decision='') & (Q(ambito='BODEGA', operacion__isnull=False) | Q(ambito='OBRA', operacion__isnull=True))))),
        ]}),
        migrations.CreateModel(name='MermaEvento', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('merma', models.ForeignKey(to='inventario.merma', on_delete=PROTECT, related_name='eventos')),
            ('tipo', models.CharField(max_length=10, choices=[('CREACION', 'Creación'), ('APROBACION', 'Aprobación'), ('RECHAZO', 'Rechazo')])),
            ('actor', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name='eventos_mermas', editable=False)),
            ('motivo', models.CharField(max_length=2000)),
            ('operacion', models.OneToOneField(to='inventario.operacionmaterial', on_delete=PROTECT, null=True, blank=True, related_name='evento_merma')),
            ('clave_idempotencia', models.UUIDField(unique=True, editable=False)), ('huella', models.CharField(max_length=64, editable=False)),
            ('creado_en', models.DateTimeField(default=timezone.now, editable=False)),
        ], options={'ordering': ['id'], 'constraints': [
            models.UniqueConstraint(fields=['merma', 'tipo'], name='inv_merma_evento_tipo_unico'),
            models.UniqueConstraint(fields=['merma'], condition=~Q(tipo='CREACION'), name='inv_merma_una_decision'),
            models.CheckConstraint(name='inv_merma_evento_forma', condition=Q(tipo='APROBACION') | Q(tipo__in=['CREACION', 'RECHAZO'], operacion__isnull=True)),
            models.CheckConstraint(name='inv_merma_evento_texto', condition=~Q(motivo='') & Q(motivo=Trim('motivo')) & ~Q(motivo__regex=r'[[:cntrl:]]')),
            models.CheckConstraint(name='inv_merma_evento_huella', condition=Q(huella__regex=r'^[0-9a-f]{64}$')),
        ]}),
        migrations.AddField('operacionmaterial', 'merma_bodega', models.OneToOneField(to='inventario.merma', on_delete=PROTECT, null=True, blank=True, related_name='baja_generada', editable=False)),
        migrations.RemoveConstraint('movimientoinventario', 'inventario_movimiento_tipo'),
        migrations.RemoveConstraint('movimientoinventario', 'inventario_movimiento_suma'),
        migrations.RemoveConstraint('movimientoinventario', 'inventario_movimiento_enlace'),
        migrations.RemoveConstraint('operacionmaterial', 'inv_op_tipo'),
        migrations.AlterField('movimientoinventario', 'tipo', models.CharField(max_length=12, default='INGRESO', choices=[('INGRESO', 'Ingreso físico'), ('SALIDA', 'Entrega a Obra'), ('DEVOLUCION', 'Recepción desde Obra'), ('MERMA', 'Merma de Bodega aprobada')])),
        migrations.AlterField('operacionmaterial', 'tipo', models.CharField(max_length=24, choices=[('AUTORIZACION_ENTREGA', 'Autorización de entrega'), ('ENTREGA', 'Despacho físico'), ('AUTORIZACION_DEVOLUCION', 'Autorización de retorno'), ('DEVOLUCION', 'Recepción física devuelta'), ('VALORIZACION', 'Valoración de ingreso'), ('REGULARIZACION', 'Valoración inicial explícita'), ('MERMA', 'Baja por merma de Bodega')])),
        migrations.AddConstraint('movimientoinventario', models.CheckConstraint(name='inventario_movimiento_tipo', condition=Q(tipo__in=['INGRESO', 'SALIDA', 'DEVOLUCION', 'MERMA']))),
        migrations.AddConstraint('movimientoinventario', models.CheckConstraint(name='inventario_movimiento_suma', condition=Q(tipo__in=['SALIDA', 'MERMA'], saldo_posterior=F('saldo_anterior')-F('cantidad')) | Q(tipo__in=['INGRESO', 'DEVOLUCION'], saldo_posterior=F('saldo_anterior')+F('cantidad')))),
        migrations.AddConstraint('movimientoinventario', models.CheckConstraint(name='inventario_movimiento_enlace', condition=Q(tipo='INGRESO', operacion__isnull=True) | Q(tipo__in=['SALIDA', 'DEVOLUCION', 'MERMA'], operacion__isnull=False))),
        migrations.AddConstraint('operacionmaterial', models.CheckConstraint(name='inv_op_tipo', condition=Q(tipo__in=['AUTORIZACION_ENTREGA', 'ENTREGA', 'AUTORIZACION_DEVOLUCION', 'DEVOLUCION', 'VALORIZACION', 'REGULARIZACION', 'MERMA']))),
        migrations.AddConstraint('operacionmaterial', models.CheckConstraint(name='inv_op_merma_enlace', condition=Q(tipo='MERMA', merma_bodega__isnull=False) | (~Q(tipo='MERMA') & Q(merma_bodega__isnull=True)))),
    ]
