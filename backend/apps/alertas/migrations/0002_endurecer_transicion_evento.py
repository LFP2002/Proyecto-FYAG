# Endurecer NULL SQL: solo CREACION admite estado_anterior nulo.

import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alertas', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='alertaevento',
            name='alerta_evento_coherente',
        ),
        migrations.AddConstraint(
            model_name='alertaevento',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('actor__isnull', True), ('estado_anterior__isnull', True), ('estado_nuevo', 'PENDIENTE'), ('motivo', ''), ('tipo', 'CREACION')), models.Q(('actor__isnull', True), ('estado_anterior__in', ['PENDIENTE', 'ATENDIDA']), ('estado_anterior__isnull', False), ('estado_nuevo', 'RESUELTA'), ('motivo', ''), ('tipo', 'RESOLUCION')), models.Q(('actor__isnull', False), ('estado_anterior', 'PENDIENTE'), ('estado_anterior__isnull', False), ('estado_nuevo', 'ATENDIDA'), ('motivo', django.db.models.functions.text.Trim('motivo')), ('tipo', 'ATENCION'), models.Q(('motivo', ''), _negated=True)), _connector='OR'), name='alerta_evento_coherente'),
        ),
    ]
