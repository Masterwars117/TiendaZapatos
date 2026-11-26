"""Genera contraseñas una vez en los volúmenes privados del demo."""

import os
from pathlib import Path
from secrets import token_hex
from tempfile import NamedTemporaryFile


def ensure_password(path):
    if path.is_file():
        return
    # Publica un archivo completo y conserva el de una instalación previa.
    with NamedTemporaryFile(mode="w", encoding="ascii", dir=path.parent) as temporary:
        temporary.write(token_hex(24))
        temporary.flush()
        os.chmod(temporary.name, 0o444)
        try:
            os.link(temporary.name, path)
        except FileExistsError:
            pass


if __name__ == "__main__":
    for name in ("root", "replication", "federated"):
        ensure_password(Path("/run/zapateria-admin") / name)
    ensure_password(Path("/run/zapateria-reader/password"))
    print("Credenciales del demo preparadas.")
