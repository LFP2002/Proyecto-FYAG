from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("usuarios", "0009_recuperacion_acceso_c2")]
    operations = [
        migrations.RemoveConstraint(model_name="usuario", name="usuarios_rol_valido"),
        migrations.AlterField(model_name="usuario", name="rol", field=models.CharField(max_length=30, choices=[
            ("GERENCIA", "Gerencia"), ("ADMINISTRATIVO_FINANZAS", "Administrativo / Finanzas"),
            ("SUPERVISOR_OBRAS", "Supervisor de Obras"), ("TECNICO", "Técnico"),
            ("ADMINISTRADOR_TI", "Administrador de TI"), ("BODEGUERO", "Bodeguero")])),
        migrations.AddConstraint(model_name="usuario", constraint=models.CheckConstraint(name="usuarios_rol_valido",
            condition=models.Q(rol__in=["GERENCIA", "ADMINISTRATIVO_FINANZAS", "SUPERVISOR_OBRAS", "TECNICO", "ADMINISTRADOR_TI", "BODEGUERO"]))),
    ]
