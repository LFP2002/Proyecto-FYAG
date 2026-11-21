from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q, F
from django.db.models.deletion import PROTECT
from django.utils import timezone


def cantidad(**kwargs):
    return models.DecimalField(max_digits=12, decimal_places=3, **kwargs)


def costo(**kwargs):
    return models.DecimalField(max_digits=15, decimal_places=2, **kwargs)


class Migration(migrations.Migration):
    dependencies = [('inventario', '0002_integridad_libro'), ('obras', '0012_origen_gasto_bodega'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='EstadoValoracion', fields=[
            ('articulo', models.OneToOneField(to='inventario.articuloinventario', primary_key=True, serialize=False, on_delete=PROTECT)),
            ('saldo_historico', cantidad(default=Decimal('0.000'))),
            ('ultimo_movimiento_historico', models.BigIntegerField(null=True, blank=True)),
            ('corte_en', models.DateTimeField(default=timezone.now, editable=False)),
            ('saldo_valorado', cantidad(default=Decimal('0.000'))),
            ('promedio', costo(null=True, blank=True)),
        ], options={'constraints': [
            models.CheckConstraint(name='inv_val_saldos', condition=Q(saldo_historico__gte=0, saldo_historico__lte=Decimal('999999999.999'), saldo_valorado__gte=0, saldo_valorado__lte=Decimal('999999999.999'))),
            models.CheckConstraint(name='inv_val_promedio', condition=(Q(saldo_valorado=0, promedio__isnull=True) | Q(saldo_valorado__gt=0, promedio__isnull=False, promedio__gte=0, promedio__lte=Decimal('9999999999999.99')))),
        ]}),
        migrations.CreateModel(name='OperacionMaterial', fields=[
            ('id', models.BigAutoField(primary_key=True, auto_created=True, serialize=False, verbose_name='ID')),
            ('tipo', models.CharField(max_length=24, choices=[('AUTORIZACION_ENTREGA', 'Autorización de entrega'), ('ENTREGA', 'Despacho físico'), ('AUTORIZACION_DEVOLUCION', 'Autorización de retorno'), ('DEVOLUCION', 'Recepción física devuelta'), ('VALORIZACION', 'Valoración de ingreso'), ('REGULARIZACION', 'Valoración inicial explícita')])),
            ('articulo', models.ForeignKey(to='inventario.articuloinventario', on_delete=PROTECT, related_name='operaciones_material')),
            ('obra', models.ForeignKey(to='obras.obra', on_delete=PROTECT, null=True, blank=True, related_name='operaciones_material')),
            ('autorizacion', models.ForeignKey(to='inventario.operacionmaterial', on_delete=PROTECT, null=True, blank=True, related_name='ejecuciones')),
            ('entrega', models.ForeignKey(to='inventario.operacionmaterial', on_delete=PROTECT, null=True, blank=True, related_name='retornos')),
            ('ingreso', models.OneToOneField(to='inventario.movimientoinventario', on_delete=PROTECT, null=True, blank=True, related_name='valoracion')),
            ('gasto', models.OneToOneField(to='obras.gastoobra', on_delete=PROTECT, null=True, blank=True, related_name='entrega_bodega')),
            ('cantidad', cantidad()), ('unidad', models.CharField(max_length=30)),
            ('costo_unitario_neto', costo(null=True, blank=True)),
            ('saldo_valorado_anterior', cantidad(null=True, blank=True)), ('saldo_valorado_posterior', cantidad(null=True, blank=True)),
            ('promedio_anterior', costo(null=True, blank=True)), ('promedio_posterior', costo(null=True, blank=True)),
            ('clave_idempotencia', models.UUIDField(unique=True, editable=False)), ('huella', models.CharField(max_length=64, editable=False)),
            ('referencia', models.CharField(max_length=150)), ('motivo', models.CharField(max_length=2000)),
            ('actor', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name='operaciones_material')),
            ('creado_en', models.DateTimeField(default=timezone.now, editable=False)),
        ], options={'ordering': ['id'], 'constraints': [
            models.CheckConstraint(name='inv_op_tipo', condition=Q(tipo__in=['AUTORIZACION_ENTREGA', 'ENTREGA', 'AUTORIZACION_DEVOLUCION', 'DEVOLUCION', 'VALORIZACION', 'REGULARIZACION'])),
            models.CheckConstraint(name='inv_op_cantidad', condition=Q(cantidad__gt=0, cantidad__lte=Decimal('999999999.999'))),
            models.CheckConstraint(name='inv_op_precio', condition=Q(costo_unitario_neto__isnull=True) | Q(costo_unitario_neto__gte=0, costo_unitario_neto__lte=Decimal('9999999999999.99'))),
            models.CheckConstraint(name='inv_op_huella', condition=Q(huella__regex=r'^[0-9a-f]{64}$')),
            models.UniqueConstraint(fields=['articulo'], condition=Q(tipo='REGULARIZACION'), name='inv_regularizacion_unica'),
        ]}),
        migrations.AddField('movimientoinventario', 'operacion', models.OneToOneField(to='inventario.operacionmaterial', on_delete=PROTECT, null=True, blank=True, related_name='movimiento', editable=False)),
        migrations.AlterField('movimientoinventario', 'tipo', models.CharField(max_length=12, default='INGRESO', choices=[('INGRESO', 'Ingreso físico'), ('SALIDA', 'Entrega a Obra'), ('DEVOLUCION', 'Recepción desde Obra')])),
        migrations.RemoveConstraint('movimientoinventario', 'inventario_movimiento_tipo'),
        migrations.RemoveConstraint('movimientoinventario', 'inventario_movimiento_suma'),
        migrations.AddConstraint('movimientoinventario', models.CheckConstraint(name='inventario_movimiento_tipo', condition=Q(tipo__in=['INGRESO', 'SALIDA', 'DEVOLUCION']))),
        migrations.AddConstraint('movimientoinventario', models.CheckConstraint(name='inventario_movimiento_suma', condition=(Q(tipo='SALIDA', saldo_posterior=F('saldo_anterior') - F('cantidad')) | Q(tipo__in=['INGRESO', 'DEVOLUCION'], saldo_posterior=F('saldo_anterior') + F('cantidad'))))),
        migrations.AddConstraint('movimientoinventario', models.CheckConstraint(name='inventario_movimiento_enlace', condition=Q(tipo='INGRESO', operacion__isnull=True) | Q(tipo__in=['SALIDA', 'DEVOLUCION'], operacion__isnull=False))),
    ]
