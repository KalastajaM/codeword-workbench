#!/usr/bin/env python3
"""Start locally by default; hosted deployment requires explicit configuration."""
import argparse
import os
from pathlib import Path
from app import __version__
from app.server import make_server


def runtime_options(argv=None, environ=None):
    env = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description='Run Codeword Workbench locally or in explicit hosted mode.')
    parser.add_argument('--port', type=int, default=None)
    parser.add_argument('--data-dir', type=Path, default=None)
    parser.add_argument('--version', action='version', version='Codeword Workbench ' + __version__)
    args = parser.parse_args(argv)
    if env.get('CODEWORD_HOSTED') != '1':
        return {'port':args.port if args.port is not None else 8765, 'data_dir':args.data_dir}
    try:
        port = args.port if args.port is not None else int(env.get('PORT', '8080'))
    except ValueError:
        raise ValueError('PORT must be a whole-number TCP port.') from None
    if not 1 <= port <= 65535:
        raise ValueError('Hosted PORT must be between 1 and 65535.')
    origin = env.get('CODEWORD_PUBLIC_ORIGIN')
    if not origin and env.get('RAILWAY_PUBLIC_DOMAIN'):
        origin = 'https://' + env['RAILWAY_PUBLIC_DOMAIN']
    return {'port':port, 'data_dir':args.data_dir or Path(env.get('CODEWORD_DATA_DIR','/data')),
            'host':'0.0.0.0', 'public_origin':origin,
            'access_password':env.get('CODEWORD_ACCESS_PASSWORD'),
            'allow_public':env.get('CODEWORD_ALLOW_PUBLIC') == '1'}


def main():
    try:
        options = runtime_options()
        server = make_server(**options)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    address = options.get('public_origin') or f'http://127.0.0.1:{server.server_port}'
    print(f'Codeword Workbench is ready at {address}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopping Codeword Workbench.')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
