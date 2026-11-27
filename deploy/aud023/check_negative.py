"""Directed negative checks against an authorized synthetic AUD-023 archive."""
import argparse
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile

from backup import BackupError, crypt, verified


def check(options, work):
    good = work / 'good.tar'
    crypt(options, source=options.archive, destination=good, encrypt=False)
    with tarfile.open(good, 'r:') as archive:
        payload = {entry.name: archive.extractfile(entry).read() for entry in archive}
    ciphertext = bytearray(options.archive.read_bytes())
    ciphertext[len(ciphertext)//2] ^= 128
    bad = work / 'ciphertext.gpg'
    bad.write_bytes(ciphertext)

    def rejects(path, reason):
        options.archive = path
        with tempfile.TemporaryDirectory(dir=work) as directory:
            try:
                verified(options, Path(directory))
            except BackupError as exc:
                assert str(exc).startswith(reason), str(exc)
            else:
                raise AssertionError('Respaldo inválido aceptado')
        print(f'OK: {reason}')

    rejects(bad, 'Cifrado o autenticación GPG')
    incompatible = json.loads(payload['manifest.json'])
    incompatible['format'] = 999
    for index, (changes, reason) in enumerate((
        ({'mongo.archive': None}, 'Respaldo incompleto'),
        ({'postgres.dump': payload['postgres.dump'] + b'changed'}, 'Inventario o SHA-256 no coincide'),
        ({'manifest.json': json.dumps(incompatible).encode()}, 'Formato o política incompatible'),
    )):
        plain, encrypted = work / f'{index}.tar', work / f'{index}.gpg'
        with tarfile.open(plain, 'x:') as archive:
            for name, data in (payload | changes).items():
                if data is not None:
                    entry = tarfile.TarInfo(name)
                    entry.size = len(data)
                    archive.addfile(entry, io.BytesIO(data))
        crypt(options, source=plain, destination=encrypted, encrypt=True)
        rejects(encrypted, reason)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('archive', 'stage', 'key'):
        parser.add_argument(f'--{flag}', type=Path, required=True)
    parser.add_argument('--gpg', default='gpg')
    parser.add_argument('--synthetic-only', required=True, choices=['CONFIRMED'])
    args = parser.parse_args()
    os.umask(0o077)
    with tempfile.TemporaryDirectory(dir=args.stage) as directory:
        check(args, Path(directory))
