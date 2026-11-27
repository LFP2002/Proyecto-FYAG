"""Offline logical backup/restore of the standalone FYAG Compose. See docs/RESPALDO-RESTAURACION.md."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
from time import monotonic
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
FILES = ('evidencias', 'adjuntos', 'archivos_chat')
PAYLOAD = ('postgres.dump', 'postgres.toc', 'mongo.archive', *(f'{v}.tar' for v in FILES))
MONGO_DB = 'fyag_documentos'
COLLECTIONS = {'documentos_metadata', 'adjuntos_metadata'}
ENGINES = {'postgres', 'mongodb'}
IMAGE_SERVICES = ('postgres', 'mongodb', 'migraciones', 'backend', 'proxy', 'redis-seguridad', 'redis')
SETTINGS = {'POSTGRES_DB', 'POSTGRES_USER', 'FYAG_MONGO_USER', 'MONGO_INITDB_ROOT_USERNAME', 'FYAG_PUBLIC_HOST',
            'FYAG_HTTPS_PORT', 'FYAG_CHAT_RETENCION_DIAS', 'FYAG_EMAIL_PROFILE', 'FYAG_BLOQUEOS_PERFIL',
            'FYAG_BLOQUEOS_AUTORIZACION', 'FYAG_BLOQUEOS_ENTREGA_SMTP', 'FYAG_BLOQUEOS_AUTORIZACION_REMITENTE',
            'FYAG_BLOQUEOS_CORREO_TI', 'FYAG_BLOQUEOS_DOMINIO', 'EMAIL_HOST', 'EMAIL_PORT', 'EMAIL_USE_TLS',
            'EMAIL_USE_SSL', 'DEFAULT_FROM_EMAIL'}
PG_LOGIN = '''export PGPASSWORD="$(cat /run/secrets/postgres_migration_password)"
exec "$@" -h 127.0.0.1 -U fyag_sql_migration -d "$POSTGRES_DB"'''
MONGO_TOOL = r'''umask 077
config=$(mktemp /dev/shm/fyag-mongo.XXXXXX)
trap 'rm -f "$config"' EXIT
password=$(cat /run/secrets/mongo_root_password)
# Single-quoted YAML scalar; double any internal quote. Never pass a password in argv.
case "$password" in *[![:print:]]*) exit 2;; esac
escaped=$(printf '%s' "$password" | sed "s/'/''/g")
printf "password: '%s'\n" "$escaped" > "$config"
unset password escaped
"$@" --config "$config" --host 127.0.0.1 --username "$MONGO_INITDB_ROOT_USERNAME" --authenticationDatabase admin'''
MONGO_INFO = '''
const fs = require('fs');
const admin = db.getSiblingDB('admin');
admin.auth(process.env.MONGO_INITDB_ROOT_USERNAME, fs.readFileSync('/run/secrets/mongo_root_password', 'utf8').replace(/\\r?\\n$/, ''));
const app = db.getSiblingDB('fyag_documentos');
const collections = Object.fromEntries(app.getCollectionNames().sort().map(n => [n, app.getCollection(n).countDocuments()]));
const version = admin.runCommand({buildInfo: 1}).version;
print(JSON.stringify({version, collections}));
'''


class BackupError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise BackupError(message)


def run(argv, label='Docker', *, source=None, destination=None):
    # Native tool errors may contain private data; don't copy them to evidence/logs.
    with (source.open('rb') if source else open(os.devnull, 'rb')) as stream:
        if destination:
            with destination.open('xb') as output:
                result = subprocess.run(argv, stdin=stream, stdout=output, stderr=subprocess.DEVNULL, cwd=ROOT)
        else:
            result = subprocess.run(argv, stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=ROOT)
    require(result.returncode == 0, f'{label}: fallo (código {result.returncode}); no publicar ni abrir tráfico.')
    return result.stdout


def docker(*args, **kwargs):
    return run(['docker', *args], **kwargs)


def inspect(kind, name):
    return json.loads(docker(kind, 'inspect', name))[0]


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def digest(path):
    with path.open('rb') as stream:
        return {'bytes': path.stat().st_size, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}


def tar_names(archive):
    seen = set()
    for entry in archive:
        raw = entry.name.removeprefix('./')
        if raw == '.' and entry.isdir():
            raw = ''
        parts = PurePosixPath(raw).parts
        require((raw != '' or entry.isdir()) and not raw.startswith('/') and '\\' not in raw
                and all(p not in {'..', '.'} and ':' not in p for p in parts)
                and raw == '/'.join(parts) and not entry.mode & 0o7000
                and (entry.isfile() or entry.isdir()) and raw not in seen, 'Entrada TAR no permitida.')
        seen.add(raw)
        yield raw, entry


def file_inventory(path):
    with tarfile.open(path, 'r:') as archive:
        return sorted((name, entry.size) for name, entry in tar_names(archive) if entry.isfile())


class Compose:
    def __init__(self, options):
        self.project = options.project
        require(re.fullmatch(r'fyag-[a-z0-9][a-z0-9-]{1,39}', self.project), 'Se requiere un nombre explícito fyag-* válido.')
        self.argv = ['compose', '-p', self.project, '--env-file', str(options.env.resolve()), '-f', 'compose.production.yaml']
        if options.smtp:
            self.argv += ['-f', 'deploy/compose.production.smtp.yaml']
        self.argv += ['--profile', '*']
        self.config = json.loads(self.call('config', '--format', 'json'))
        services = self.config['services']
        for name in self.config['volumes']:
            self.volume(name)
        for name, network in self.config['networks'].items():
            require(network.get('name') == f'{self.project}_{name}' and not network.get('external'), 'Red externa no admitida.')
        for db in ENGINES:
            require(not services[db].get('ports'), 'Motor publicado no admitido.')

    def call(self, *args, **kwargs):
        return docker(*self.argv, *args, **kwargs)

    def volume(self, name):
        definition = self.config['volumes'][name]
        expected = f'{self.project}_{name}'
        require(definition.get('name') == expected and not definition.get('external') and not definition.get('driver_opts')
                and definition.get('driver', 'local') == 'local', 'Volumen no aislado o no estándar.')
        return expected

    def existing(self, kind):
        args = ('-a',) if kind == 'container' else ()
        template = '{{.Names}}' if kind == 'container' else '{{.Name}}'
        return docker(kind, 'ls', *args, '--format', template, label=f'Inventario Docker {kind}').decode().splitlines()

    def empty_target(self):
        require(self.project.startswith('fyag-dr-'), 'El destino debe comenzar con fyag-dr-.')
        for kind in ('container', 'volume', 'network'):
            require(not docker(kind, 'ls', *(() if kind != 'container' else ('-a',)), '-q', '--filter',
                               f'label=com.docker.compose.project={self.project}').strip(), 'El destino ya tiene recursos Compose.')
            require(not any(n == self.project or n.startswith((self.project + '-', self.project + '_'))
                            for n in self.existing(kind)), 'El destino ya tiene recursos reservados.')

    def images(self):
        return {s: inspect('image', self.config['services'][s]['image'])['Id'] for s in IMAGE_SERVICES}

    def report(self):
        return {s: {'options': {k: v for k, v in cfg.get('environment', {}).items() if k in SETTINGS},
                    'image': cfg.get('image'), 'ports': cfg.get('ports', []),
                    'secrets': sorted(item['source'] for item in cfg.get('secrets', []))}
                for s, cfg in self.config['services'].items()}

    def engines_only(self):
        ids = docker('ps', '-q', '--filter', f'label=com.docker.compose.project={self.project}').decode().splitlines()
        info = [inspect('container', cid) for cid in ids]
        require({cfg['Config']['Labels']['com.docker.compose.service'] for cfg in info} == ENGINES and len(info) == 2,
                'Debe haber exactamente dos contenedores activos: PostgreSQL y MongoDB.')
        running = {cfg['Id'] for cfg in info}
        for name in ('sql', 'documentos'):
            network = inspect('network', self.config['networks'][name]['name'])
            require(network['Internal'] and set(network['Containers'] or {}) <= running, 'Cliente externo en red de datos.')
        for cfg in info:
            service = cfg['Config']['Labels']['com.docker.compose.service']
            network = 'sql' if service == 'postgres' else 'documentos'
            require(set(cfg['NetworkSettings']['Networks']) == {self.config['networks'][network]['name']}
                    and not cfg['HostConfig'].get('PortBindings'), 'Motor conectado a una red no aislada.')
        session = self.pg('psql', '-XAt', '-c', "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND backend_type='client backend' AND pid<>pg_backend_pid()")
        require(session.strip() == b'0', 'Quedan sesiones SQL ajenas.')

        for volume in FILES:
            require(not docker('ps', '-q', '--filter', f'volume={self.volume(volume)}').strip(), 'Queda un cliente de archivos activo.')

    @contextmanager
    def lock(self):
        # Atomic within the selected Docker daemon, including across operator hosts.
        name = f'aud023-lock-{self.project}'
        cid = docker('create', '--name', name, '--network', 'none', '--read-only',
                     self.images()['backend'], 'false', label='Reserva exclusiva AUD-023').decode().strip()
        try:
            yield
        finally:
            docker('rm', cid, label='Liberar reserva AUD-023')

    def pg(self, command, *args, **kwargs):
        return self.call('exec', '-T', 'postgres', 'sh', '-ec', PG_LOGIN, 'fyag', command, *args, **kwargs)

    def mongo(self, command, *args, **kwargs):
        return self.call('exec', '-T', 'mongodb', 'sh', '-ec', MONGO_TOOL, 'fyag', command, *args, **kwargs)

    def mongo_info(self):
        info = json.loads(self.call('exec', '-T', 'mongodb', 'mongosh', '--norc', '--quiet', '--eval', MONGO_INFO))
        require(set(info['collections']) == COLLECTIONS, 'Inventario Mongo no contemplado.')
        return info

    def versions(self, mongo):
        return {'postgres': self.pg('psql', '-XAt', '-c', 'SHOW server_version').decode().strip(),
                'pg_dump': self.call('exec', '-T', 'postgres', 'pg_dump', '--version').decode().strip(),
                'mongo': mongo['version'], 'mongodump': self.call('exec', '-T', 'mongodb', 'mongodump', '--version').decode().splitlines()[0]}

    def reset_redis(self):
        self.call('up', '-d', '--no-deps', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '60',
                  'redis-seguridad', 'redis', label='Comprobar Redis nuevos')
        try:
            for service, command in (
                ('redis-seguridad', 'REDISCLI_AUTH="$(cat /run/secrets/redis_security_password)" '
                 'redis-cli --tls --cacert /run/secrets/redis_ca --sni redis-seguridad -h redis-seguridad --raw DBSIZE'),
                ('redis', 'REDISCLI_AUTH="$(cat /run/secrets/redis_chat_password)" redis-cli --raw DBSIZE'),
            ):
                require(self.call('exec', '-T', service, 'sh', '-ec', command).strip() == b'0', 'Redis destino no está vacío.')
        finally:
            self.call('stop', 'redis-seguridad', 'redis', label='Cerrar Redis tras comprobación')

    def files(self, volume, image, args, *, writable=False, **kwargs):
        name = self.volume(volume)
        require(inspect('volume', name).get('Labels', {}).get('com.docker.compose.project') == self.project,
                'Volumen sin etiqueta del proyecto esperado.')
        mount = f'type=volume,src={name},dst=/datos,volume-nocopy' + ('' if writable else ',readonly')
        return docker('run', '--rm', '-i', '--read-only', '--network', 'none', '--mount', mount,
                      '--entrypoint', '/bin/sh', image, *args, **kwargs)


def crypt(options, *, source, destination, encrypt):
    flags = ['--symmetric', '--cipher-algo', 'AES256', '--compress-algo', 'none', '--force-mdc'] if encrypt else ['--decrypt']
    run([options.gpg, '--no-options', '--batch', '--no-tty', '--pinentry-mode', 'loopback', '--no-symkey-cache',
         '--passphrase-file', str(options.key.resolve()), '--output', '-', *flags], 'Cifrado o autenticación GPG',
        source=source, destination=destination)


def backup(compose, options, work):
    require(not options.archive.exists(), 'El respaldo de salida ya existe.')
    images = compose.images()
    for service in IMAGE_SERVICES:
        ids = compose.call('ps', '-a', '-q', service).decode().splitlines()
        require(all(inspect('container', cid)['Image'] == images[service] for cid in ids), 'Imagen real distinta de la referencia configurada.')
    compose.call('stop', *sorted(set(compose.config['services']) - ENGINES), label='Detener escritores y entrada')
    compose.engines_only()
    frozen = now()
    mongo = compose.mongo_info()
    versions = compose.versions(mongo)
    compose.pg('pg_dump', '--format=custom', '--schema=public', '--no-owner', '--no-acl', '--lock-wait-timeout=10s',
               destination=work / 'postgres.dump', label='pg_dump')
    compose.call('exec', '-T', 'postgres', 'pg_restore', '--list', source=work / 'postgres.dump',
                 destination=work / 'postgres.toc', label='Inventario PostgreSQL')
    compose.mongo('mongodump', '--db', MONGO_DB, '--archive', destination=work / 'mongo.archive', label='mongodump')
    inventory = {}
    for volume in FILES:
        archive = work / f'{volume}.tar'
        compose.files(volume, images['postgres'], ('-ec', 'cd /datos && exec tar --numeric-owner --hard-dereference -cf - .'),
                      destination=archive, label=f'Captura {volume}')
        inventory[volume] = file_inventory(archive)
    compose.engines_only()
    manifest = {'format': 1, 'project': compose.project, 'frozen_at': frozen, 'captured_at': now(), 'versions': versions,
                'images': images, 'configuration': compose.report(), 'mongo': mongo['collections'], 'files': inventory,
                'redis': 'reset', 'payload': {name: digest(work / name) for name in PAYLOAD}}
    (work / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding='utf-8')
    bundle = work / 'bundle.tar'
    with tarfile.open(bundle, 'x:') as archive:
        for name in (*PAYLOAD, 'manifest.json'):
            archive.add(work / name, arcname=name)
    # Publish only the complete ciphertext; neither the manifest nor dumps leave staging in clear.
    partial = options.archive.with_name(f'.{options.archive.name}.{uuid4().hex}.partial')
    try:
        crypt(options, source=bundle, destination=partial, encrypt=True)
        os.link(partial, options.archive)  # atomic, never overwrite
    finally:
        partial.unlink(missing_ok=True)
    print(f'Respaldo cifrado completo; corte {frozen}. Origen aún sin tráfico: reabrir según el runbook.')


def verified(options, work):
    bundle = work / 'bundle.tar'
    crypt(options, source=options.archive, destination=bundle, encrypt=False)
    expected = set(PAYLOAD) | {'manifest.json'}
    with tarfile.open(bundle, 'r:') as archive:
        for name, entry in tar_names(archive):
            require(name in expected and entry.isfile(), 'Componente inesperado en el respaldo.')
            expected.remove(name)
            with archive.extractfile(entry) as source, (work / name).open('xb') as destination:
                while chunk := source.read(1024 * 1024):
                    destination.write(chunk)
    require(not expected, 'Respaldo incompleto.')
    manifest = json.loads((work / 'manifest.json').read_text(encoding='utf-8'))
    require(manifest['format'] == 1 and manifest['redis'] == 'reset', 'Formato o política incompatible.')
    require(manifest['payload'] == {name: digest(work / name) for name in PAYLOAD}, 'Inventario o SHA-256 no coincide.')
    require(manifest['files'] == json.loads(json.dumps({v: file_inventory(work / f'{v}.tar') for v in FILES})),
            'Inventario de archivos incoherente.')
    require(set(manifest['mongo']) == COLLECTIONS, 'Inventario Mongo incompatible.')
    return manifest


def restore_postgres(compose, work, toc):
    # pg_dump may include public's CREATE/COMMENT, but the destination schema
    # already has its owner/USAGE from its own AUD-025 initdb.
    listing = work / 'restore.toc'
    listing.write_bytes(b''.join(line for line in toc.splitlines(keepends=True)
        if not re.search(rb' (?:SCHEMA - public |COMMENT - SCHEMA public )', line)))
    remote = f'/dev/shm/fyag-toc-{uuid4().hex}'
    try:
        compose.call('exec', '-T', 'postgres', 'sh', '-ec', 'umask 077; cat > "$1"', 'fyag', remote,
                     source=listing, label='Selección del catálogo PostgreSQL')
        compose.pg('pg_restore', '--exit-on-error', '--single-transaction', '--no-owner', '--no-acl',
                   '--use-list', remote, source=work / 'postgres.dump', label='pg_restore')
    finally:
        compose.call('exec', '-T', 'postgres', 'rm', '-f', remote, label='Retirar catálogo temporal')


def restore(compose, options, work):
    compose.empty_target()
    manifest = verified(options, work)
    require(compose.project != manifest['project'], 'Origen y destino no pueden coincidir.')
    images = compose.images()
    require(images == manifest['images'], 'Imágenes incompatibles con las del respaldo.')
    compose.empty_target()
    compose.call('up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '100', 'postgres', 'mongodb',
                 label='Inicializar solo motores nuevos')
    compose.engines_only()
    mongo = compose.mongo_info()
    require(compose.versions(mongo) == manifest['versions'] and not any(mongo['collections'].values()),
            'Versiones incompatibles o Mongo no vacío.')
    require(compose.pg('psql', '-XAt', '-c', "SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace").strip() == b'0',
            'El esquema SQL destino no está vacío.')
    toc = compose.call('exec', '-T', 'postgres', 'pg_restore', '--list', source=work / 'postgres.dump')
    require(toc == (work / 'postgres.toc').read_bytes(), 'El catálogo nativo no coincide.')
    for volume in FILES:
        docker('volume', 'create', '--label', f'com.docker.compose.project={compose.project}',
               '--label', f'com.docker.compose.volume={volume}', compose.volume(volume), label=f'Crear volumen nuevo {volume}')
        compose.files(volume, images['postgres'], ('-ec', 'test -z "$(find /datos -mindepth 1 -print -quit)"'), label=f'Volumen vacío {volume}')
    # The target's public schema and roles belong to AUD-025 provisioning, not the source.
    restore_postgres(compose, work, toc)
    compose.pg('psql', '-X', '-v', 'ON_ERROR_STOP=1', source=Path(__file__).with_name('invalidate.sql'), label='Invalidación SQL')
    compose.call('run', '--rm', '--no-deps', '-T', 'migraciones', label='Reinstalar matriz AUD-025')
    compose.mongo('mongorestore', '--archive', '--nsInclude', f'{MONGO_DB}.*', '--drop', '--stopOnError',
                  source=work / 'mongo.archive', label='mongorestore')
    require(compose.mongo_info()['collections'] == manifest['mongo'], 'Conteos Mongo restaurados incoherentes.')
    for volume in FILES:
        compose.files(volume, images['postgres'], ('-ec', 'cd /datos && exec tar --numeric-owner -xpf -'),
                      writable=True, source=work / f'{volume}.tar', label=f'Restaurar {volume}')
        compose.files(volume, images['postgres'], ('-ec', 'cd /datos && exec tar --compare -f -'),
                      source=work / f'{volume}.tar', label=f'Verificar bytes y metadatos {volume}')
    compose.engines_only()
    compose.reset_redis()
    compose.engines_only()
    print(f'Restauración offline verificada; corte {manifest["frozen_at"]}. No se abrió tráfico.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('backup', 'verify', 'restore'))
    for flag in ('archive', 'stage', 'key', 'env'):
        parser.add_argument(f'--{flag}', type=Path, required=flag != 'env')
    parser.add_argument('--project')
    parser.add_argument('--confirm', help='Debe coincidir exactamente con --project para operaciones Docker.')
    parser.add_argument('--smtp', action='store_true')
    parser.add_argument('--gpg', default='gpg')
    options = parser.parse_args()
    os.umask(0o077)
    start = monotonic()
    require(options.stage.is_dir() and options.key.is_file(), 'Se requiere staging protegido y archivo de clave externo.')
    require(re.fullmatch(rb'[0-9a-f]{64}', options.key.read_bytes().rstrip(b'\r\n')), 'Use una clave externa de 32 bytes aleatorios en hexadecimal.')
    if os.name == 'posix':
        require(not options.stage.stat().st_mode & 0o077 and not options.key.stat().st_mode & 0o077,
                'Staging y clave deben excluir al grupo y a otros usuarios.')
        if options.action == 'backup':
            require(not options.archive.parent.stat().st_mode & 0o077, 'El directorio de respaldo debe ser privado.')
    with tempfile.TemporaryDirectory(prefix='aud023-', dir=options.stage) as directory:
        work = Path(directory)
        if options.action == 'verify':
            verified(options, work)
            print('Cifrado, manifiesto e inventario verificados.')
        else:
            require(options.env and options.project and options.confirm == options.project, 'Confirme el proyecto explícito y su archivo de entorno.')
            compose = Compose(options)
            with compose.lock():
                (backup if options.action == 'backup' else restore)(compose, options, work)
    print(f'Tiempo real: {monotonic() - start:.2f} s.')


if __name__ == '__main__':
    try:
        main()
    except BackupError as exc:
        sys.exit(f'AUD-023: {exc}')
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as exc:
        sys.exit(f'AUD-023: entrada o entorno inválido ({type(exc).__name__}); mantener el destino aislado.')
