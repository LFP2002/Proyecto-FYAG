# Migración inicial para 004A; revisar mediante makemigrations --check --dry-run.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import F, Q
from django.db.models.functions import Lower, Trim


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("comercial", "0005_remove_presupuesto_presupuesto_gerencia_coherente_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CategoriaServicio",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=100)),
                ("activo", models.BooleanField(default=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("creado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="categorias_servicio_creadas", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("nombre", "id")},
        ),
        migrations.CreateModel(
            name="Obra",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("descripcion", models.CharField(max_length=2000)),
                ("fecha_programada", models.DateField(blank=True, null=True)),
                ("iniciado_en", models.DateTimeField(blank=True, editable=False, null=True)),
                ("estado", models.CharField(choices=[
                    ("PLANIFICADA", "Planificada"), ("EN_PROCESO", "En proceso"),
                    ("SUSPENDIDA", "Suspendida"), ("FINALIZADA", "Finalizada"),
                    ("CANCELADA", "Cancelada")], default="PLANIFICADA", editable=False, max_length=12)),
                ("finalizado_en", models.DateTimeField(blank=True, editable=False, null=True)),
                ("cancelado_en", models.DateTimeField(blank=True, editable=False, null=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("categoria_servicio", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="obras", to="obras.categoriaservicio")),
                ("creado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="obras_creadas", to=settings.AUTH_USER_MODEL)),
                ("presupuesto", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="obra", to="comercial.presupuesto")),
                ("tecnico_responsable", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="obras_asignadas", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-creado_en", "-id")},
        ),
        migrations.CreateModel(
            name="CategoriaServicioEvento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[
                    ("CREACION", "Creación"), ("EDICION", "Edición"),
                    ("ACTIVACION", "Activación"), ("DESACTIVACION", "Desactivación")], max_length=20)),
                ("datos_anteriores", models.JSONField(default=dict)),
                ("datos_nuevos", models.JSONField(default=dict)),
                ("motivo", models.CharField(blank=True, default="", max_length=2000)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("categoria", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="eventos", to="obras.categoriaservicio")),
                ("registrado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="eventos_categoria_servicio", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("creado_en", "id")},
        ),
        migrations.CreateModel(
            name="ObraEvento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[
                    ("CREACION", "Creación"), ("CAMBIO_ESTADO", "Cambio de estado"),
                    ("CAMBIO_TECNICO", "Cambio de técnico"), ("EDICION", "Edición de ficha")], max_length=20)),
                ("estado_anterior", models.CharField(blank=True, choices=[
                    ("PLANIFICADA", "Planificada"), ("EN_PROCESO", "En proceso"),
                    ("SUSPENDIDA", "Suspendida"), ("FINALIZADA", "Finalizada"),
                    ("CANCELADA", "Cancelada")], max_length=12, null=True)),
                ("estado_nuevo", models.CharField(choices=[
                    ("PLANIFICADA", "Planificada"), ("EN_PROCESO", "En proceso"),
                    ("SUSPENDIDA", "Suspendida"), ("FINALIZADA", "Finalizada"),
                    ("CANCELADA", "Cancelada")], max_length=12)),
                ("datos_anteriores", models.JSONField(default=dict)),
                ("datos_nuevos", models.JSONField(default=dict)),
                ("motivo", models.CharField(blank=True, default="", max_length=2000)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("obra", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="eventos", to="obras.obra")),
                ("registrado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="eventos_obra", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("creado_en", "id")},
        ),
        migrations.AddIndex(
            model_name="obra",
            index=models.Index(fields=["tecnico_responsable", "estado"], name="obra_tecnico_estado_idx"),
        ),
        migrations.AddConstraint(
            model_name="categoriaservicio",
            constraint=models.CheckConstraint(condition=~Q(nombre="") & Q(nombre=Trim("nombre")), name="obra_categoria_nombre_valido"),
        ),
        migrations.AddConstraint(
            model_name="categoriaservicio",
            constraint=models.UniqueConstraint(Lower("nombre"), name="obra_categoria_nombre_unico"),
        ),
        migrations.AddConstraint(
            model_name="obra",
            constraint=models.CheckConstraint(condition=Q(estado__in=["PLANIFICADA", "EN_PROCESO", "SUSPENDIDA", "FINALIZADA", "CANCELADA"]), name="obra_estado_valido"),
        ),
        migrations.AddConstraint(
            model_name="obra",
            constraint=models.CheckConstraint(condition=~Q(descripcion="") & Q(descripcion=Trim("descripcion")), name="obra_descripcion_valida"),
        ),
        migrations.AddConstraint(
            model_name="obra",
            constraint=models.CheckConstraint(condition=(
                Q(estado="PLANIFICADA", iniciado_en__isnull=True, finalizado_en__isnull=True, cancelado_en__isnull=True)
                | Q(estado__in=["EN_PROCESO", "SUSPENDIDA"], tecnico_responsable__isnull=False,
                    iniciado_en__isnull=False, finalizado_en__isnull=True, cancelado_en__isnull=True)
                | Q(estado="FINALIZADA", tecnico_responsable__isnull=False,
                    iniciado_en__isnull=False, finalizado_en__isnull=False, cancelado_en__isnull=True)
                | Q(estado="CANCELADA", finalizado_en__isnull=True, cancelado_en__isnull=False)
            ), name="obra_estado_fechas_coherentes"),
        ),
        migrations.AddConstraint(
            model_name="obra",
            constraint=models.CheckConstraint(condition=Q(iniciado_en__isnull=True) | Q(iniciado_en__gte=F("creado_en")), name="obra_inicio_tras_alta"),
        ),
        migrations.AddConstraint(
            model_name="obra",
            constraint=models.CheckConstraint(condition=Q(finalizado_en__isnull=True) | Q(finalizado_en__gte=F("iniciado_en")), name="obra_fin_tras_inicio"),
        ),
        migrations.AddConstraint(
            model_name="obra",
            constraint=models.CheckConstraint(condition=Q(cancelado_en__isnull=True) | Q(cancelado_en__gte=F("creado_en")), name="obra_cancelacion_tras_alta"),
        ),
        migrations.AddConstraint(
            model_name="obraevento",
            constraint=models.CheckConstraint(condition=Q(tipo__in=["CREACION", "CAMBIO_ESTADO", "CAMBIO_TECNICO", "EDICION"]), name="obra_evento_tipo_valido"),
        ),
        migrations.AddConstraint(
            model_name="obraevento",
            constraint=models.CheckConstraint(condition=Q(estado_anterior__isnull=True) | Q(estado_anterior__in=["PLANIFICADA", "EN_PROCESO", "SUSPENDIDA", "FINALIZADA", "CANCELADA"]), name="obra_evento_estado_prev_valido"),
        ),
        migrations.AddConstraint(
            model_name="obraevento",
            constraint=models.CheckConstraint(condition=Q(estado_nuevo__in=["PLANIFICADA", "EN_PROCESO", "SUSPENDIDA", "FINALIZADA", "CANCELADA"]), name="obra_evento_estado_nuevo_valido"),
        ),
        migrations.AddConstraint(
            model_name="obraevento",
            constraint=models.CheckConstraint(condition=(
                Q(tipo="CREACION", estado_anterior__isnull=True, estado_nuevo="PLANIFICADA", motivo="")
                | (Q(tipo="CAMBIO_ESTADO", motivo__gt="") & (
                    Q(estado_anterior="PLANIFICADA", estado_nuevo="EN_PROCESO")
                    | Q(estado_anterior="EN_PROCESO", estado_nuevo="SUSPENDIDA")
                    | Q(estado_anterior="SUSPENDIDA", estado_nuevo="EN_PROCESO")
                ))
                | (Q(tipo__in=["CAMBIO_TECNICO", "EDICION"], motivo__gt="")
                   & Q(estado_anterior=F("estado_nuevo")))
            ), name="obra_evento_transicion_valida"),
        ),
        migrations.AddConstraint(
            model_name="obraevento",
            constraint=models.UniqueConstraint(fields=("obra",), condition=Q(tipo="CREACION"), name="obra_evento_creacion_unica"),
        ),
        migrations.AddConstraint(
            model_name="obraevento",
            constraint=models.CheckConstraint(condition=Q(motivo=Trim("motivo")), name="obra_evento_motivo_trim"),
        ),
        migrations.AddConstraint(
            model_name="categoriaservicioevento",
            constraint=models.CheckConstraint(condition=Q(tipo__in=["CREACION", "EDICION", "ACTIVACION", "DESACTIVACION"]), name="obra_cat_evento_tipo_valido"),
        ),
        migrations.AddConstraint(
            model_name="categoriaservicioevento",
            constraint=models.CheckConstraint(condition=Q(motivo=Trim("motivo")), name="obra_cat_evento_motivo_trim"),
        ),
        migrations.AddConstraint(
            model_name="categoriaservicioevento",
            constraint=models.CheckConstraint(condition=Q(tipo="CREACION") | ~Q(motivo=""), name="obra_cat_evento_motivo_oblig"),
        ),
    ]
