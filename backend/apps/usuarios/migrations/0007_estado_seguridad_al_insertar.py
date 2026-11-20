"""Solo cuentas nuevas: estado PERSONAL atómico en todos los caminos de INSERT.

No repara ausencias existentes: la procedencia de sus hashes es desconocida.
0006 conserva íntegra su responsabilidad de migrar cuentas históricas conocidas.
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("usuarios", "0006_seguridad_credenciales")]

    operations = [migrations.RunSQL(
        sql="""
            CREATE FUNCTION fyag_usuario_seguridad_inicial() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                INSERT INTO usuarios_seguridadcredencial (usuario_id, estado)
                VALUES (NEW.id, 'PERSONAL');
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER fyag_usuario_seguridad_inicial
            AFTER INSERT ON usuarios_usuario
            FOR EACH ROW EXECUTE FUNCTION fyag_usuario_seguridad_inicial();
        """,
        reverse_sql="""
            DROP TRIGGER fyag_usuario_seguridad_inicial ON usuarios_usuario;
            DROP FUNCTION fyag_usuario_seguridad_inicial();
        """,
    )]
