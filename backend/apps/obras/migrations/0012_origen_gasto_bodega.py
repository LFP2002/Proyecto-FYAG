from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('obras', '0011_cierre_costos_finalizacion')]
    operations = [migrations.AddField('gastoobra', 'origen', models.CharField(max_length=12, default='MANUAL', choices=[('MANUAL', 'Manual'), ('BODEGA_019B', 'Entrega Bodega')], editable=False))]
