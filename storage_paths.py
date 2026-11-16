"""Resolve a restored upload tree without rewriting immutable case snapshots."""
import os
from flask import current_app


def upload_path(stored):
    path = os.path.abspath(stored or '')
    previous = current_app.config.get('KINE_RESTORED_UPLOAD_ROOT')
    current = current_app.config.get('UPLOAD_FOLDER')
    if previous and current:
        previous = os.path.abspath(previous)
        try:
            if os.path.commonpath((previous, path)) == previous:
                path = os.path.abspath(os.path.join(current, os.path.relpath(path, previous)))
        except ValueError:
            pass
    return path
