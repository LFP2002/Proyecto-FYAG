"""Laboratorio 023B desechable. Ejecutar desde host con Docker Compose.

python backend/scripts/qa_chat_ws.py [--full]
Nunca lee .env ni opera proyectos/volúmenes preexistentes.
"""
import argparse
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='Regresión completa además de Chat')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    base = Path(os.environ['LOCALAPPDATA'])/'Temp'/'opencode' if os.name == 'nt' else Path(tempfile.gettempdir())/'opencode'
    base.mkdir(parents=True, exist_ok=True)
    project = 'fyag-023b-'+uuid.uuid4().hex[:12]
    existing = subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project='+project], text=True)
    if existing.strip():
        raise RuntimeError('Proyecto ya existente; no se autoriza reutilización.')
    with tempfile.TemporaryDirectory(prefix=project+'-', dir=base) as folder:
        folder = Path(folder)
        env = folder/'qa.env'
        env.write_text(''.join('QA_'+key+'='+secrets.token_hex(48)+'\n' for key in (
            'POSTGRES_PASSWORD', 'MONGO_ROOT_PASSWORD', 'MONGO_PASSWORD', 'DJANGO_SECRET', 'JWT_SECRET', 'REDIS_PASSWORD')), encoding='utf-8')
        override = folder/'qa.override.yaml'
        override.write_text('''services:
  postgres:
    environment:
      POSTGRES_DB: fyag_spec018c_c2_qa
    healthcheck:
      test: [CMD-SHELL, 'pg_isready -U fyag_pr44_qa -d fyag_spec018c_c2_qa']
  backend:
    environment:
      POSTGRES_DB: fyag_spec018c_c2_qa
''', encoding='utf-8')
        compose = ['docker', 'compose', '--env-file', str(env), '-f', str(root/'compose.premerge-qa.yaml'),
                   '-f', str(override), '-p', project]
        def run(*command):
            subprocess.run([*compose, *command], cwd=root, check=True)
        def django(*command):
            run('exec', '-T', 'backend', 'python', 'manage.py', *command)
        print('Proyecto QA exclusivo: '+project, flush=True)
        try:
            run('up', '-d', '--build', '--wait')
            django('check')
            django('makemigrations', '--check', '--dry-run')
            django('migrate', '--noinput')
            django('test', 'apps.chat', '--noinput', '--verbosity', '1')
            if args.full:
                django('test', '--noinput', '--verbosity', '1')
        finally:
            # Solo el proyecto recién generado; todos sus datos son QA efímeros.
            run('down', '--volumes', '--remove-orphans')


if __name__ == '__main__':
    main()
