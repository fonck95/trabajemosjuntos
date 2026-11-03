"""Comandos de consola (desde admin/, con MONGODB_URI en el entorno o en admin/.env).

    python -m app.cli importar archivo1.xlsx archivo2.xlsx   # carga o actualiza la base única
    python -m app.cli georreferenciar                        # vuelve a ubicar a todos (tras cambiar el nomenclátor)
    python -m app.cli nomenclator                            # recarga geo/gazetteer.json sin pisar lo editado
    python -m app.cli resumen                                # cifras básicas
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config, db
from .pipeline import importar


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("importar")
    p.add_argument("archivos", nargs="+", type=Path)
    sub.add_parser("georreferenciar")
    sub.add_parser("nomenclator")
    sub.add_parser("resumen")
    a = ap.parse_args()

    cfg = config.cargar()
    cliente, base = db.conectar(cfg.mongodb_uri, cfg.mongodb_db or None)
    db.inicializar(base)
    if a.cmd == "importar":
        res = importar.importar(base, a.archivos, "consola")
        print(json.dumps(res.dict(), indent=2, ensure_ascii=False))
    elif a.cmd == "georreferenciar":
        print(json.dumps(importar.georreferenciar(base), indent=2, ensure_ascii=False))
        db.recalcular_completitud(base)
    elif a.cmd == "nomenclator":
        print("lugares nuevos:", db.sembrar_lugares(base))
        print(json.dumps(importar.georreferenciar(base), indent=2, ensure_ascii=False))
    elif a.cmd == "resumen":
        activa = db.ACTIVA
        for txt, n in [
            ("personas", base.personas.count_documents(activa)),
            ("con cédula", base.personas.count_documents({**activa, "cedula": {"$ne": None}})),
            ("ubicadas", base.personas.count_documents({**activa, "lat": {"$ne": None}})),
            ("coincidencias por revisar", base.coincidencias.count_documents({"estado": "pendiente"})),
            ("reuniones", base.reuniones.count_documents({})),
        ]:
            print(f"{txt:>28}: {n}")
    cliente.close()


if __name__ == "__main__":
    main()
