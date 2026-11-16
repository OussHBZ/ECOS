"""Run the existing suite on copied sources, temporary data and no live AI.

From workspace root: <isolated-python> -I ECOS/scripts/run_tests.py --label baseline
No install, application factory, init command or production migration is run here.
Each invocation preserves its separate evidence and temporary workspace.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO.parent
PROOF_ROOT = WORKSPACE / 'output/cahier-charge-21-10/preuves/t01'
TEMP_ROOT = WORKSPACE / 'tmp/t01'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_state():
    files = {}
    for directory in ('instance', 'uploads', 'static/images/cases', 'flask_session_data', 'flask_session', 'logs'):
        base = REPO / directory
        if base.exists():
            files.update({p.relative_to(REPO).as_posix(): digest(p)
                          for p in base.rglob('*') if p.is_file()})
    cfg = REPO / '.venv/pyvenv.cfg'
    if cfg.is_file():
        files['.venv/pyvenv.cfg'] = digest(cfg)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--task', choices=('t01', 't02', 't03', 't04', 't05', 't06', 't07', 't08', 't09-t12', 't13-t16', 't17-t19', 't20-t22'), default='t01')
    parser.add_argument('pytest_args', nargs='*', default=['tests'])
    args = parser.parse_args()
    if not args.label.replace('-', '').replace('_', '').isalnum():
        parser.error('Use a simple unique label')
    if sys.prefix == sys.base_prefix:
        parser.error('Use a dedicated venv (no shared runtime/site-packages)')
    if any(Path(p).resolve().is_relative_to(REPO / '.venv') for p in sys.path if p):
        parser.error('Existing application venv must not be reused')
    proof = PROOF_ROOT.parent / args.task / args.label
    proof.mkdir(parents=True, exist_ok=False)
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix=args.label + '-', dir=TEMP_ROOT)).resolve()
    source = run_root / 'source'
    source.mkdir()
    before = protected_state()
    (proof / 'protected-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    paths = subprocess.run(['git', '-C', str(REPO), 'ls-files', '-co', '--exclude-standard', '-z'],
                           check=True, capture_output=True).stdout.decode('utf-8').split('\0')
    copied = {}
    for name in sorted(set(filter(None, paths))):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Source outside repo')
        if relative.parts[0] in ('instance', 'uploads', 'logs', 'flask_session_data', '.git', '.venv', '.claude'):
            continue
        if relative.suffix not in ('.py', '.js', '.cjs', '.html', '.css', '.json', '.ini', '.txt', '.lock'):
            continue
        original = REPO / relative
        if not original.is_file():
            continue
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        copied[name] = digest(destination)
    temp = run_root / 'temp'
    temp.mkdir()
    # Whitelist, rather than forwarding the user's API keys, tracing or Python path.
    env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT', 'PATH', 'LANG') if k in os.environ}
    env.update(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp),
               USERPROFILE=str(run_root), APPDATA=str(run_root), LOCALAPPDATA=str(run_root),
               PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', SEED_DEMO_ACCOUNTS='false',
               LANGCHAIN_TRACING_V2='false', LANGSMITH_TRACING='false', PYTHONUTF8='1')
    command = [sys.executable, '-I', '-B', '-X', 'utf8', str(source / 'scripts/test_guard.py'),
               str(run_root), str(REPO), *(args.pytest_args or ['tests'])]
    py = subprocess.run(command, cwd=source, env=env, capture_output=True, encoding='utf-8', errors='replace')
    (proof / 'pytest.txt').write_text(py.stdout + py.stderr, encoding='utf-8')
    for filename in ('pytest.xml', 'guard.json'):
        if (run_root / filename).is_file():
            shutil.copyfile(run_root / filename, proof / filename)
    node = shutil.which('node')
    js_command = [node, '--test', 'tests/test_case_form_ui.cjs', *(
        ['tests/test_security_ui.cjs'] if (source / 'tests/test_security_ui.cjs').exists() else []
    ), *(['tests/test_kine_session_ui.cjs'] if (source / 'tests/test_kine_session_ui.cjs').exists() else []),
        *(['tests/test_rehabilitation_ui.cjs'] if (source / 'tests/test_rehabilitation_ui.cjs').exists() else []),
        *(['tests/test_criteria_ui.cjs'] if (source / 'tests/test_criteria_ui.cjs').exists() else []),
        *(['tests/test_interruptions_ui.cjs'] if (source / 'tests/test_interruptions_ui.cjs').exists() else []),
        *(['tests/test_delivery_ui.cjs'] if (source / 'tests/test_delivery_ui.cjs').exists() else []),
        *(['tests/test_app_shell_ui.cjs'] if (source / 'tests/test_app_shell_ui.cjs').exists() else [])] if node else []
    js = subprocess.run(js_command, cwd=source, env=env, capture_output=True,
                        encoding='utf-8', errors='replace') if node else None
    (proof / 'node.txt').write_text(js.stdout + js.stderr if js else 'Node unavailable', encoding='utf-8')
    after = protected_state()
    (proof / 'protected-after.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    guard = json.loads((proof / 'guard.json').read_text()) if (proof / 'guard.json').exists() else {}
    suites = []
    if (proof / 'pytest.xml').exists():
        suites = [dict(s.attrib) for s in ET.parse(proof / 'pytest.xml').iter('testsuite')]
    clean_guard = guard.get('suite_events', {})
    no_guard_violation = bool(guard) and all(clean_guard.get(k) == 0 for k in
        ('network_blocked', 'writes_blocked', 'real_reads_blocked', 'sqlite_blocked'))
    summary = {
        'python': sys.version, 'executable': sys.executable, 'prefix': sys.prefix,
        'base_prefix': sys.base_prefix, 'run_root': str(run_root),
        'commit': subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'],
                                 check=True, capture_output=True, text=True).stdout.strip(),
        'copied_sha256': copied, 'python_command': command, 'python_exit': py.returncode,
        'node_command': js_command, 'node_exit': js.returncode if js else None,
        'pytest_suites': suites, 'protected_files': len(before), 'protected_changed': changed,
        'guard': guard, 'distributions': sorted(f'{d.metadata["Name"]}=={d.version}'
                                               for d in importlib.metadata.distributions()),
        'success': py.returncode == 0 and js is not None and js.returncode == 0 and
                   not changed and no_guard_violation,
    }
    (proof / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('python_exit', 'node_exit', 'pytest_suites',
                                            'protected_changed', 'guard', 'success')}, indent=2))
    print('Evidence:', proof)
    return 0 if summary['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
