import uuid

from django.conf import settings
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError
from django.db.models import Q, F
from django.db.models.deletion import PROTECT
from django.utils import timezone


SQL = r"""
CREATE FUNCTION fyag_chat_ticket() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
   IF OLD.vence_en>statement_timestamp() THEN PERFORM fyag_chat_error(); END IF;
   RETURN OLD;
 END IF;
 IF TG_OP='INSERT' THEN
   IF NEW.usado_en IS NOT NULL OR NEW.vence_en-NEW.creado_en>interval '45 seconds'
   THEN PERFORM fyag_chat_error(); END IF;
 ELSE
   IF (to_jsonb(NEW)-'usado_en') IS DISTINCT FROM (to_jsonb(OLD)-'usado_en')
     OR OLD.usado_en IS NOT NULL OR NEW.usado_en IS NULL OR OLD.vence_en<=statement_timestamp()
   THEN PERFORM fyag_chat_error(); END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_chat_ticket BEFORE INSERT OR UPDATE OR DELETE ON chat_ticketchat FOR EACH ROW EXECUTE FUNCTION fyag_chat_ticket();
"""


def proteger_reversion(apps, schema_editor):
    ahora = timezone.now()
    if (apps.get_model('chat', 'TicketChat').objects.filter(vence_en__gt=ahora).exists()
        or apps.get_model('chat', 'CanalChat').objects.filter(vence_en__gt=ahora).exists()):
        raise IrreversibleError('Esperar caducidad de tickets y canales antes de revertir 023B.')


class Migration(migrations.Migration):
    dependencies = [('chat', '0002_integridad_chat'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='TicketChat', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('digest', models.CharField(max_length=64, unique=True, editable=False)),
            ('usuario', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name='+')),
            ('sesion_version', models.PositiveBigIntegerField()),
            ('creado_en', models.DateTimeField(default=timezone.now, editable=False)),
            ('vence_en', models.DateTimeField(editable=False)), ('usado_en', models.DateTimeField(null=True, editable=False)),
        ], options={'constraints': [
            models.CheckConstraint(name='chat_ticket_digest', condition=Q(digest__regex=r'^[0-9a-f]{64}$')),
            models.CheckConstraint(name='chat_ticket_version', condition=Q(sesion_version__gte=1)),
            models.CheckConstraint(name='chat_ticket_tiempos', condition=Q(vence_en__gt=F('creado_en')) & (Q(usado_en__isnull=True) | Q(usado_en__gte=F('creado_en'), usado_en__lte=F('vence_en')))),
        ], 'indexes': [models.Index(fields=['vence_en'], name='chat_ticket_vencimiento')]}),
        migrations.CreateModel(name='CanalChat', fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ('ip_digest', models.CharField(max_length=64)),
            ('usuario', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, null=True, related_name='+')),
            ('creado_en', models.DateTimeField(default=timezone.now, editable=False)), ('vence_en', models.DateTimeField()),
        ], options={'indexes': [models.Index(fields=['usuario', 'vence_en'], name='chat_canales_usuario'), models.Index(fields=['ip_digest', 'vence_en'], name='chat_canales_ip'), models.Index(fields=['vence_en'], name='chat_canales_vencimiento')]}),
        migrations.RunSQL(SQL, 'DROP TRIGGER fyag_chat_ticket ON chat_ticketchat; DROP FUNCTION fyag_chat_ticket();'),
        migrations.RunPython(migrations.RunPython.noop, proteger_reversion),
    ]
