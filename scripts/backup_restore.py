"""Explicit, offline SQLite + document bundle. Never targets production by default.

Stop writers and scheduler before backup; secrets are intentionally excluded.
Restore only into a NEW directory, then validate there before switching traffic.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
import zipfile

DATABASE = 'instance/osce_simulator.db'
DATA_DIRS = ('uploads', 'static/images/cases')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_database(path):
    if not path.is_file():raise ValueError('Missing database')
    with closing(sqlite3.connect(path)) as conn:
        if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity check failed')
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('SQLite foreign key check failed')


def backup(root, destination, *, quiesced=False):
    if not quiesced:
        raise ValueError('Stop all writers and scheduler; confirm quiesced=True')
    root=Path(root).resolve(); destination=Path(destination).resolve()
    source=root/DATABASE
    if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(root):
        raise ValueError('Explicit application data root must contain '+DATABASE)
    if destination.is_relative_to(root):
        raise ValueError('Store backup outside the application data root')
    entries={}
    with tempfile.TemporaryDirectory() as temporary:
        copy=Path(temporary)/'snapshot.db'
        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(copy)) as dst:
            src.backup(dst)
        check_database(copy)
        # Fail instead of silently omitting custom/temp upload locations.
        with closing(sqlite3.connect(copy)) as conn:
            tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table,column in (('kine_case_documents','stored_path'),('kine_case_drafts','source_path')):
                if table in tables:
                    for (value,) in conn.execute(f'SELECT {column} FROM {table}'):
                        path=Path(value).resolve()
                        if not path.is_relative_to(root/'uploads') or not path.is_file():
                            raise ValueError('Referenced upload missing or outside bundle root')
        entries[DATABASE]=copy.read_bytes()
    for directory in DATA_DIRS:
        for p in sorted((root/directory).rglob('*')):
            if p.is_symlink() or not p.resolve().is_relative_to(root):
                raise ValueError('Linked files are not supported')
            if p.is_file():
                entries[p.relative_to(root).as_posix()]=p.read_bytes()
    manifest={'format':1, 'original_upload_root':str(root/'uploads'), 'files':{name:sha(data) for name,data in entries.items()},
              'excluded':['secrets','sessions','logs','code','dependencies']}
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as bundle:
        for name,data in entries.items():bundle.writestr(name,data)
        bundle.writestr('manifest.json',json.dumps(manifest,indent=2))
    return manifest


def restore(archive, destination):
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Restore destination must not exist')
    with zipfile.ZipFile(archive) as bundle:
        names=bundle.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate archive entry')
        manifest=json.loads(bundle.read('manifest.json'))
        if manifest.get('format')!=1:raise ValueError('Unknown backup format')
        files=manifest['files']
        if set(names)!=set(files)|{'manifest.json'} or DATABASE not in files:
            raise ValueError('Unexpected archive contents')
        for name,checksum in files.items():
            p=PurePosixPath(name)
            if (p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or
                not (name==DATABASE or any(name.startswith(d+'/') for d in DATA_DIRS))):
                raise ValueError('Unsafe archive path')
            if sha(bundle.read(name))!=checksum:raise ValueError('Backup checksum mismatch')
        # Validation precedes writes. A failed DB check leaves an isolated copy
        # for diagnosis; it never overwrites a running application.
        destination.mkdir(parents=True)
        for name in files:
            p=destination/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(bundle.read(name))
    check_database(destination/DATABASE)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('backup','restore'))
    parser.add_argument('source',type=Path);parser.add_argument('destination',type=Path)
    parser.add_argument('--quiesced',action='store_true')
    args=parser.parse_args()
    if args.operation=='backup':backup(args.source,args.destination,quiesced=args.quiesced)
    else:restore(args.source,args.destination)
    print('Verified:',args.destination)
