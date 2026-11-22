import uuid

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q, F
from django.db.models.deletion import PROTECT
from django.utils import timezone


def pk():
    return ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'))


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='ConversacionChat', fields=[pk(),
            ('tipo', models.CharField(max_length=7, choices=[('DIRECTA', 'Directa'), ('GRUPAL', 'Grupal')])),
            ('titulo', models.CharField(max_length=100, blank=True, default='')),
            ('creador', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name='chats_creados')),
            ('par_menor', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, null=True, related_name='+')),
            ('par_mayor', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, null=True, related_name='+')),
            ('creado_en', models.DateTimeField(default=timezone.now, editable=False)),
        ], options={'ordering': ['id'], 'constraints': [
            models.UniqueConstraint(fields=['par_menor', 'par_mayor'], condition=Q(tipo='DIRECTA'), name='chat_directa_par_unico'),
            models.CheckConstraint(name='chat_conversacion_forma', condition=Q(tipo='DIRECTA', titulo='', par_menor__isnull=False, par_mayor__isnull=False, par_menor__lt=F('par_mayor')) | (Q(tipo='GRUPAL', par_menor__isnull=True, par_mayor__isnull=True) & ~Q(titulo=''))),
        ]}),
        migrations.CreateModel(name='ParticipanteChat', fields=[pk(),
            ('conversacion', models.ForeignKey(to='chat.conversacionchat', on_delete=PROTECT, related_name='participantes')),
            ('usuario', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name='chats')),
            ('incorporado_en', models.DateTimeField(default=timezone.now, editable=False)),
            ('ultimo_leido_mensaje_id', models.PositiveBigIntegerField(null=True, blank=True)),
        ], options={'constraints': [models.UniqueConstraint(fields=['conversacion', 'usuario'], name='chat_miembro_unico')], 'indexes': [models.Index(fields=['usuario', 'conversacion'], name='chat_usuario_conversacion')]}),
        migrations.CreateModel(name='MensajeChat', fields=[pk(),
            ('conversacion', models.ForeignKey(to='chat.conversacionchat', on_delete=PROTECT, related_name='mensajes')),
            ('autor', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name='mensajes_chat')),
            ('texto', models.CharField(max_length=2000, blank=True, default='')),
            ('creado_en', models.DateTimeField(default=timezone.now, editable=False)), ('vence_en', models.DateTimeField(editable=False)),
            ('clave_idempotencia', models.UUIDField(editable=False)), ('huella', models.CharField(max_length=64, editable=False)),
        ], options={'ordering': ['-id'], 'constraints': [
            models.UniqueConstraint(fields=['autor', 'clave_idempotencia'], name='chat_mensaje_uuid_autor'),
            models.CheckConstraint(name='chat_mensaje_vence', condition=Q(vence_en__gt=F('creado_en'))),
            models.CheckConstraint(name='chat_mensaje_huella', condition=Q(huella__regex=r'^[0-9a-f]{64}$')),
        ], 'indexes': [models.Index(fields=['conversacion', '-id'], name='chat_historial_cursor'), models.Index(fields=['vence_en', 'id'], name='chat_vencimiento')]}),
        migrations.CreateModel(name='ArchivoChat', fields=[pk(),
            ('mensaje', models.OneToOneField(to='chat.mensajechat', on_delete=PROTECT, null=True, related_name='archivo')),
            ('clave_interna', models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
            ('estado', models.CharField(max_length=9, default='RESERVADO', choices=[('RESERVADO', 'Reservado'), ('PUBLICADO', 'Publicado'), ('RETIRAR', 'Retirar')])),
            ('nombre', models.CharField(max_length=150, blank=True, default='')), ('mime', models.CharField(max_length=32, blank=True, default='')),
            ('tamano_bytes', models.PositiveIntegerField(default=0)), ('sha256', models.CharField(max_length=64, blank=True, default='')),
            ('creado_en', models.DateTimeField(default=timezone.now, editable=False)),
        ], options={'constraints': [models.CheckConstraint(name='chat_archivo_forma', condition=Q(estado__in=['RESERVADO', 'RETIRAR'], mensaje__isnull=True) | (Q(estado='PUBLICADO', mensaje__isnull=False, tamano_bytes__gt=0, tamano_bytes__lte=8388608, mime__in=['image/jpeg', 'image/png', 'application/pdf'], sha256__regex=r'^[0-9a-f]{64}$') & ~Q(nombre='')))], 'indexes': [models.Index(fields=['estado', 'creado_en'], name='chat_archivo_retiro')]}),
        migrations.CreateModel(name='ActoChat', fields=[pk(),
            ('autor', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name='+')),
            ('accion', models.CharField(max_length=12, choices=[('CONVERSACION', 'Conversación'), ('MENSAJE', 'Mensaje')])),
            ('clave', models.UUIDField()), ('huella', models.CharField(max_length=64)),
            ('conversacion', models.ForeignKey(to='chat.conversacionchat', on_delete=PROTECT, related_name='+')),
            ('mensaje_id', models.PositiveBigIntegerField(null=True)), ('caducado', models.BooleanField(default=False)),
        ], options={'constraints': [models.UniqueConstraint(fields=['autor', 'accion', 'clave'], name='chat_acto_unico')], 'indexes': [models.Index(fields=['mensaje_id'], name='chat_acto_mensaje')]}),
        migrations.CreateModel(name='CupoChat', fields=[pk(), ('clave', models.CharField(max_length=64)), ('ventana', models.PositiveBigIntegerField()), ('cantidad', models.PositiveIntegerField(default=1))], options={'constraints': [models.UniqueConstraint(fields=['clave', 'ventana'], name='chat_cupo_unico')]}),
    ]
