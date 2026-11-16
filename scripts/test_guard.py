"""Bootstrap réservé aux tests : aucune importation de la fabrique Flask.

Garde de régression Python (pas un bac à sable OS contre du code hostile).
Le lanceur utilise en plus une copie de sources et compare les données réelles.
"""
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys


def main():
    run_root = Path(sys.argv[1]).resolve()
    real_repo = Path(sys.argv[2]).resolve()
    source = run_root / 'source'
    os.chdir(source)
    sys.path[:0] = [str(source), str(source / 'tests')]
    events = {'network_blocked': 0, 'writes_blocked': 0,
              'real_reads_blocked': 0, 'sqlite_memory': 0, 'sqlite_temporary': 0,
              'sqlite_blocked': 0, 'null_device_writes': 0, 'loopback_probes_blocked': 0}
    refused = []

    def inside(value, directory):
        if isinstance(value, int) or value is None:
            return False
        try:
            path = Path(os.fsdecode(value)).resolve()
            return path.is_relative_to(directory)
        except (ValueError, TypeError):
            return False

    def require_write(value):
        if isinstance(value, int):
            return  # Descripteur déjà ouvert ; stdout/stderr de pytest notamment.
        if Path(os.fsdecode(value)).resolve() == Path(os.devnull).resolve():
            events['null_device_writes'] += 1
            return  # Périphérique sans stockage, utilisé par les bibliothèques.
        if not inside(value, run_root):
            events['writes_blocked'] += 1
            refused.append({'event': 'write', 'target': os.fsdecode(value)})
            raise PermissionError('Test write outside isolated run refused')

    def audit(event, args):
        if event in ('socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'socket.bind'):
            if event == 'socket.bind' and args[1] in (('::1', 0), ('127.0.0.1', 0)):
                # urllib3 vérifie ainsi la disponibilité IPv6 à l'import.
                # Refuser quand même le bind ; compter cette sonde séparément
                # d'une tentative de connexion IA ou de résolution DNS.
                events['loopback_probes_blocked'] += 1
                raise PermissionError('Local network feature probe disabled')
            events['network_blocked'] += 1
            refused.append({'event': event, 'target': repr(args[1] if event != 'socket.getaddrinfo' else args[:2])})
            raise PermissionError('Network disabled during deterministic tests')
        if event == 'subprocess.Popen':
            raise PermissionError('Child processes disabled inside Python tests')
        if event == 'sqlite3.connect':
            database = os.fsdecode(args[0])
            if database == ':memory:':
                events['sqlite_memory'] += 1
            elif database.startswith('file:') or not inside(database, run_root):
                events['sqlite_blocked'] += 1
                raise PermissionError('SQLite target outside temporary run refused')
            else:
                events['sqlite_temporary'] += 1
        if event == 'open':
            path, mode, flags = args
            if inside(path, real_repo):
                events['real_reads_blocked'] += 1
                raise PermissionError('Real application files unavailable inside tests')
            if (flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                require_write(path)
        if event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime'):
            require_write(args[0])
        if event in ('os.rename', 'os.link', 'os.symlink'):
            require_write(args[0])
            require_write(args[1])

    sys.addaudithook(audit)
    self_checks = {}
    for name, operation in [
        ('network', lambda: socket.create_connection(('127.0.0.1', 9))),
        ('real_database', lambda: sqlite3.connect(real_repo / 'instance/osce_simulator.db')),
        ('external_write', lambda: (run_root.parent / 'forbidden.txt').write_text('blocked')),
        ('real_read', lambda: (real_repo / 'app.py').read_text()),
    ]:
        try:
            operation()
        except PermissionError:
            self_checks[name] = True
        else:
            raise RuntimeError('Isolation guard self-check failed: ' + name)
    before = dict(events)
    refused.clear()

    import pytest

    class Evidence:
        def pytest_sessionfinish(self, session, exitstatus):
            result = {'self_checks': self_checks, 'self_check_events': before,
                      'suite_events': {k: events[k] - before[k] for k in events},
                      'collected': session.testscollected, 'exit_code': int(exitstatus),
                      'refused': refused,
                      'app_factory_called': False}
            # Observe actual calls separately below; importing init_db only loads definitions.
            result['app_factory_called'] = factory_calls[0] > 0
            (run_root / 'guard.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

    factory_calls = [0]

    def profile(frame, event, arg):
        if event == 'call' and frame.f_code.co_name == 'create_app' and Path(frame.f_code.co_filename).name == 'app.py':
            factory_calls[0] += 1

    sys.setprofile(profile)
    try:
        return pytest.main(['-q', '-p', 'no:cacheprovider', '-o', 'log_file=' + str(run_root / 'pytest.log'),
                            '--basetemp', str(run_root / 'pytest-tmp'),
                            '--junitxml', str(run_root / 'pytest.xml'), *sys.argv[3:]],
                           plugins=[Evidence()])
    finally:
        sys.setprofile(None)


if __name__ == '__main__':
    raise SystemExit(main())
