"""Comandos de consola (desde admin/, con MONGODB_URI en el entorno o en admin/.env).

    python -m app.cli migrar                                 # lleva la base al esquema vigente (antes de desplegar)
    python -m app.cli importar archivo1.xlsx archivo2.xlsx   # carga o actualiza la base única
    python -m app.cli importar planilla.xlsx --capturado-por 5   # planilla de campo llenada por el planillero 5
    python -m app.cli georreferenciar                        # vuelve a ubicar a todos (tras cambiar el nomenclátor)
    python -m app.cli nomenclator                            # recarga geo/gazetteer.json sin pisar lo editado
    python -m app.cli resumen                                # cifras básicas
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config, db, migraciones
from .pipeline import importar


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrar")
    p = sub.add_parser("importar")
    p.add_argument("archivos", nargs="+", type=Path)
    p.add_argument("--capturado-por", type=int, default=None, help="uid del planillero que llenó la planilla")
    sub.add_parser("georreferenciar")
    sub.add_parser("nomenclator")
    sub.add_parser("resumen")
    a = ap.parse_args()

    cfg = config.cargar()
    cliente, base = db.conectar(cfg.mongodb_uri, cfg.mongodb_db or None)
    db.inicializar(base)  # también migra el esquema y reconcilia
    if a.cmd == "migrar":
        print(json.dumps({"version": migraciones.version(base),
                          **(base.meta.find_one({"_id": "esquema"}, {"_id": 0, "pasos": 1}) or {})},
                         indent=2, ensure_ascii=False, default=str))
    elif a.cmd == "importar":
        res = importar.importar(base, a.archivos, "consola", capturado_por=a.capturado_por)
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
