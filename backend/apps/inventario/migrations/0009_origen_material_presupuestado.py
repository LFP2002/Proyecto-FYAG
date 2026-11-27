import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('comercial', '0007_presupuestoitem_articulo'),
        ('inventario', '0008_integridad_mermas'),
    ]

    operations = [
        migrations.AddField(
            model_name='operacionmaterial', name='item_presupuesto',
            field=models.OneToOneField(
                to='comercial.presupuestoitem', on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True, related_name='autorizacion_prevista', editable=False,
            ),
        ),
        migrations.RunSQL(
            """
            CREATE FUNCTION fyag_validar_origen_019f() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.tipo <> 'AUTORIZACION_ENTREGA' OR NEW.solicitud_material_id IS NOT NULL
                   OR NOT EXISTS (
                    SELECT 1 FROM comercial_presupuestoitem i
                    JOIN obras_obra o ON o.presupuesto_id = i.presupuesto_id
                    WHERE i.id = NEW.item_presupuesto_id AND o.id = NEW.obra_id
                      AND i.articulo_id = NEW.articulo_id AND i.unidad = NEW.unidad
                      AND i.cantidad = NEW.cantidad
                ) THEN
                    RAISE EXCEPTION 'Origen de autorización prevista inválido'
                        USING ERRCODE = '23514', CONSTRAINT = 'inv_019f_integridad';
                END IF;
                RETURN NEW;
            END;
            $$;
            -- Se ejecuta después de los validadores existentes de Presupuesto/Obra.
            CREATE TRIGGER fyag_z_origen_019f BEFORE INSERT ON inventario_operacionmaterial
                FOR EACH ROW WHEN (NEW.item_presupuesto_id IS NOT NULL)
                EXECUTE FUNCTION fyag_validar_origen_019f();
            """,
            """
            DROP TRIGGER fyag_z_origen_019f ON inventario_operacionmaterial;
            DROP FUNCTION fyag_validar_origen_019f();
            """,
        ),
    ]
