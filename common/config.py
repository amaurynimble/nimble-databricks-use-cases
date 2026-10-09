"""Install settings shared by every notebook.

00_install writes them to a small JSON file in your workspace home folder, so the other notebooks
pick up the same catalog, schema, secret scope and warehouse without asking again.
"""
import json
import os

DEFAULTS = {
    "catalog": "main",
    "schema": "nimble_use_cases",
    "secret_scope": "nimble",
    "secret_key": "api_key",
    "warehouse_id": "",
}


def _path(user):
    return f"/Workspace/Users/{user}/.nimble_use_cases.json"


def load(user):
    cfg = dict(DEFAULTS)
    try:
        with open(_path(user)) as f:
            cfg.update(json.load(f))
    except (FileNotFoundError, ValueError):
        pass
    return cfg


def save(user, cfg):
    with open(_path(user), "w") as f:
        json.dump(cfg, f, indent=1)
    return _path(user)


def fq(cfg, name):
    """Fully qualified name inside the install schema, e.g. main.nimble_use_cases.shelf_products."""
    return f"{cfg['catalog']}.{cfg['schema']}.{name}"
