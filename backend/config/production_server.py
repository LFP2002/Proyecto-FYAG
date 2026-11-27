"""Single Daphne instance per private socket volume. Never bind a TCP port."""
import http.client
import os
from pathlib import Path
import socket
import sys

SOCKET = Path('/run/fyag/daphne.sock')


class Connection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(SOCKET))


def main():
    if sys.argv[1:] in (['live'], ['ready']):
        with_connection = Connection(os.environ['FYAG_PUBLIC_HOST'], timeout=3)
        try:
            with_connection.request('GET', f'/health/{sys.argv[1]}/', headers={'X-FYAG-Client-IP': '127.0.0.1'})
            return int(with_connection.getresponse().status != 200)
        except OSError:
            return 1
        finally:
            with_connection.close()
    if sys.argv[1:]:
        return 2
    SOCKET.unlink(missing_ok=True)
    # Nginx runs with the same unprivileged UID, and other services cannot mount this volume.
    os.umask(0o077)
    os.execvp('daphne', ['daphne', '-u', str(SOCKET), '--verbosity', '0', '--websocket_connect_timeout', '5',
                         '--websocket-max-message-size', '1024', '--websocket-max-frame-size', '1024',
                         'config.asgi:application'])


if __name__ == '__main__':
    sys.exit(main())
