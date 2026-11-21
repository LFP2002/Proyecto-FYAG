from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q, F
from django.db.models.deletion import PROTECT
from django.db.models.functions import Trim
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [('inventario', '0004_integridad_materiales'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='SolicitudMaterialObra', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('obra', models.ForeignKey(to='obras.obra', on_delete=PROTECT, related_name='solicitudes_materiales')),
            ('solicitante', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name='solicitudes_materiales', editable=False)),
            ('articulo', models.ForeignKey(to='inventario.articuloinventario', on_delete=PROTECT, related_name='solicitudes_materiales')),
            ('unidad', models.CharField(max_length=30, editable=False)),
            ('cantidad_solicitada', models.DecimalField(max_digits=12, decimal_places=3)),
            ('justificacion', models.CharField(max_length=2000)),
            ('estado', models.CharField(max_length=9, default='PENDIENTE', choices=[('PENDIENTE', 'Pendiente'), ('APROBADA', 'Aprobada'), ('RECHAZADA', 'Rechazada')], editable=False)),
            ('cantidad_aprobada', models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True, editable=False)),
            ('motivo_decision', models.CharField(max_length=2000, default='', blank=True, editable=False)),
            ('decidido_por', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, null=True, blank=True, related_name='decisiones_materiales', editable=False)),
            ('decidido_en', models.DateTimeField(null=True, blank=True, editable=False)),
            ('autorizacion', models.OneToOneField(to='inventario.operacionmaterial', on_delete=PROTECT, null=True, blank=True, related_name='solicitud_aprobada', editable=False)),
            ('clave_idempotencia', models.UUIDField(unique=True, editable=False)),
            ('huella', models.CharField(max_length=64, editable=False)),
            ('creado_en', models.DateTimeField(default=timezone.now, editable=False)),
        ], options={'ordering': ['id'], 'constraints': [
            models.CheckConstraint(name='inv_sol_cantidad', condition=Q(cantidad_solicitada__gt=0, cantidad_solicitada__lte=Decimal('999999999.999'))),
            models.CheckConstraint(name='inv_sol_huella', condition=Q(huella__regex=r'^[0-9a-f]{64}$')),
            models.CheckConstraint(name='inv_sol_textos', condition=~Q(justificacion='') & Q(justificacion=Trim('justificacion'), motivo_decision=Trim('motivo_decision')) & ~Q(justificacion__regex=r'[[:cntrl:]]') & ~Q(motivo_decision__regex=r'[[:cntrl:]]')),
            models.CheckConstraint(name='inv_sol_decision', condition=(
                Q(estado='PENDIENTE', cantidad_aprobada__isnull=True, motivo_decision='', decidido_por__isnull=True, decidido_en__isnull=True, autorizacion__isnull=True)
                | (Q(estado='APROBADA', cantidad_aprobada__isnull=False, cantidad_aprobada__gt=0, cantidad_aprobada__lte=F('cantidad_solicitada'), decidido_por__isnull=False, decidido_en__isnull=False, decidido_en__gte=F('creado_en'), autorizacion__isnull=False) & ~Q(motivo_decision=''))
                | (Q(estado='RECHAZADA', cantidad_aprobada__isnull=True, decidido_por__isnull=False, decidido_en__isnull=False, decidido_en__gte=F('creado_en'), autorizacion__isnull=True) & ~Q(motivo_decision=''))
            )),
        ]}),
        migrations.CreateModel(name='SolicitudMaterialEvento', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('solicitud', models.ForeignKey(to='inventario.solicitudmaterialobra', on_delete=PROTECT, related_name='eventos')),
            ('tipo', models.CharField(max_length=10, choices=[('CREACION', 'Creación'), ('APROBACION', 'Aprobación'), ('RECHAZO', 'Rechazo')])),
            ('actor', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name='eventos_solicitudes_materiales', editable=False)),
            ('motivo', models.CharField(max_length=2000)),
            ('cantidad_aprobada', models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)),
            ('autorizacion', models.OneToOneField(to='inventario.operacionmaterial', on_delete=PROTECT, null=True, blank=True, related_name='evento_solicitud')),
            ('clave_idempotencia', models.UUIDField(unique=True, editable=False)),
            ('huella', models.CharField(max_length=64, editable=False)),
            ('creado_en', models.DateTimeField(default=timezone.now, editable=False)),
        ], options={'ordering': ['id'], 'constraints': [
            models.UniqueConstraint(fields=['solicitud', 'tipo'], name='inv_sol_evento_tipo_unico'),
            models.UniqueConstraint(fields=['solicitud'], condition=~Q(tipo='CREACION'), name='inv_sol_una_decision'),
            models.CheckConstraint(name='inv_sol_evento_forma', condition=Q(tipo='APROBACION', cantidad_aprobada__isnull=False, cantidad_aprobada__gt=0, cantidad_aprobada__lte=Decimal('999999999.999'), autorizacion__isnull=False) | Q(tipo__in=['CREACION', 'RECHAZO'], cantidad_aprobada__isnull=True, autorizacion__isnull=True)),
            models.CheckConstraint(name='inv_sol_evento_texto', condition=~Q(motivo='') & Q(motivo=Trim('motivo')) & ~Q(motivo__regex=r'[[:cntrl:]]')),
            models.CheckConstraint(name='inv_sol_evento_huella', condition=Q(huella__regex=r'^[0-9a-f]{64}$')),
        ]}),
        migrations.AddField('operacionmaterial', 'solicitud_material', models.OneToOneField(to='inventario.solicitudmaterialobra', on_delete=PROTECT, null=True, blank=True, related_name='autorizacion_generada', editable=False)),
    ]
