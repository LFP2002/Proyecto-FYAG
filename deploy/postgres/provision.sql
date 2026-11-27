BEGIN;
SET LOCAL search_path = pg_catalog;
SET LOCAL lock_timeout = '5s';
SET LOCAL log_statement = 'none';
SET LOCAL log_min_error_statement = 'panic';
SET LOCAL track_activities = off;

DO $$
BEGIN
    IF current_user LIKE 'fyag\_sql\_%' OR current_database() IN ('postgres', 'template0', 'template1')
       OR NOT EXISTS (SELECT FROM pg_database WHERE datname = current_database() AND pg_get_userbyid(datdba) = current_user)
       OR EXISTS (SELECT FROM pg_database WHERE datname NOT IN (current_database(), 'postgres', 'template0', 'template1'))
       OR EXISTS (SELECT FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()
                  AND backend_type = 'client backend')
       OR EXISTS (SELECT FROM pg_namespace WHERE nspname NOT IN ('public', 'information_schema') AND nspname NOT LIKE 'pg\_%')
       OR EXISTS (SELECT FROM pg_extension WHERE extname <> 'plpgsql') THEN
        RAISE EXCEPTION 'Se requiere la base FYAG dedicada, sin extensiones adicionales, sin tráfico y su administrador propietario';
    END IF;
END $$;

CREATE TEMP TABLE cuentas (rol name PRIMARY KEY, clave text NOT NULL) ON COMMIT DROP;
\getenv migration fyag_migration
\getenv web fyag_web
\getenv security fyag_security
\getenv alerts fyag_alerts
\getenv documents fyag_documents
\getenv attachments fyag_attachments
\getenv chat fyag_chat
\getenv mail fyag_mail
INSERT INTO cuentas VALUES ('fyag_sql_migration', :'migration'), ('fyag_sql_web', :'web'),
    ('fyag_sql_security', :'security'), ('fyag_sql_alerts', :'alerts'), ('fyag_sql_documents', :'documents'),
    ('fyag_sql_attachments', :'attachments'), ('fyag_sql_chat', :'chat'), ('fyag_sql_mail', :'mail');

DO $$
DECLARE row record;
BEGIN
    FOR row IN SELECT c.*, r.oid FROM pg_temp.cuentas c LEFT JOIN pg_roles r ON r.rolname = c.rol LOOP
        IF row.oid IS NULL THEN
            EXECUTE format('CREATE ROLE %I', row.rol);
            EXECUTE format('COMMENT ON ROLE %I IS %L', row.rol, 'FYAG AUD-025 managed');
        ELSIF shobj_description(row.oid, 'pg_authid') IS DISTINCT FROM 'FYAG AUD-025 managed'
           OR EXISTS (SELECT FROM pg_auth_members WHERE member = row.oid OR roleid = row.oid) THEN
            RAISE EXCEPTION 'Colisión o membresía no autorizada para %', row.rol;
        END IF;
        EXECUTE format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L', row.rol, row.clave);
        EXECUTE format('ALTER ROLE %I SET search_path TO public, pg_catalog', row.rol);
        EXECUTE format('REVOKE ALL ON DATABASE %I FROM %I', current_database(), row.rol);
        EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), row.rol);
    END LOOP;
END $$;

SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database()) \gexec
REVOKE CONNECT, TEMPORARY ON DATABASE postgres, template1 FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO fyag_sql_migration;
REVOKE ALL ON SCHEMA public FROM fyag_sql_web, fyag_sql_security, fyag_sql_alerts, fyag_sql_documents,
    fyag_sql_attachments, fyag_sql_chat, fyag_sql_mail CASCADE;
GRANT USAGE ON SCHEMA public TO fyag_sql_web, fyag_sql_security, fyag_sql_alerts, fyag_sql_documents,
    fyag_sql_attachments, fyag_sql_chat, fyag_sql_mail;

-- Transfer only the application schema, never cluster objects or database ownership.
DO $$
DECLARE obj record;
BEGIN
    FOR obj IN SELECT c.relname, c.relkind, pg_get_userbyid(c.relowner) AS owner
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind NOT IN ('i','I','t') ORDER BY (c.relkind='S') LOOP
        IF obj.owner NOT IN (current_user, 'fyag_sql_migration') OR obj.relkind NOT IN ('r','S') THEN
            RAISE EXCEPTION 'Objeto no inventariado: %', obj.relname;
        END IF;
        IF obj.owner = current_user THEN
            EXECUTE format('ALTER %s public.%I OWNER TO fyag_sql_migration', CASE obj.relkind WHEN 'S' THEN 'SEQUENCE' ELSE 'TABLE' END, obj.relname);
        END IF;
    END LOOP;
    FOR obj IN SELECT p.oid::regprocedure AS signature, p.proname, pg_get_userbyid(p.proowner) AS owner
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' LOOP
        IF obj.owner NOT IN (current_user, 'fyag_sql_migration') OR obj.proname NOT LIKE 'fyag\_%' THEN
            RAISE EXCEPTION 'Rutina no inventariada: %', obj.proname;
        END IF;
        EXECUTE format('ALTER FUNCTION %s OWNER TO fyag_sql_migration', obj.signature);
    END LOOP;
END $$;
ALTER DEFAULT PRIVILEGES FOR ROLE fyag_sql_migration REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
COMMIT;
