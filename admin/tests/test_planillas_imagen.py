"""La foto de una planilla física se valida y se limpia antes de guardarse (app/planillas.py, `validar_imagen`): solo
JPEG o PNG con la firma de su tipo, sin metadatos (EXIF, GPS, comentarios, textos de PNG) y cortada en su fin, de modo
que nada escondido después de la imagen (un archivo políglota) llega a la base ni al modelo. Imágenes inventadas con
Pillow."""
import struct
import zlib

import pytest

from app import planillas as pl
from ayudas_planillas import GPS_TEXTO, _trozo, abre, gif, jpeg, png


def _codigo(f, *args):
    with pytest.raises(pl.ErrorPlanilla) as e:
        f(*args)
    return e.value.status_code, e.value.detail["codigo"]


def test_jpeg_sin_exif_gps_ni_comentarios_y_legible():
    crudo = jpeg(comentario=b"COMENTARIO-SECRETO")
    assert b"Exif" in crudo and GPS_TEXTO in crudo and b"COMENTARIO-SECRETO" in crudo and b"DESCRIPCION" in crudo
    im = pl.validar_imagen(crudo, "image/jpeg")
    assert (im.ancho, im.alto, im.media_type) == (1200, 900, "image/jpeg")
    for secreto in (b"Exif", GPS_TEXTO, b"COMENTARIO-SECRETO", b"DESCRIPCION-SECRETA", b"FabricanteInventado"):
        assert secreto not in im.datos
    # Ningún segmento APPn salvo el JFIF mínimo que se pone, ni COM
    assert im.datos.startswith(b"\xff\xd8" + pl._JFIF) and im.datos.endswith(b"\xff\xd9")
    assert b"\xff\xe1" not in im.datos[:200] and b"\xff\xfe" not in im.datos[:200]
    pil = abre(im.datos)
    assert pil.size == (1200, 900) and not pil.getexif()
    # Limpiar dos veces da lo mismo (es determinista: la misma foto tiene el mismo SHA-256)
    assert pl.validar_imagen(im.datos, "image/jpeg").datos == im.datos


def test_jpeg_poliglota_se_corta_en_eoi():
    carga = b"<html><script>alert(1)</script></html>PK\x03\x04"
    im = pl.validar_imagen(jpeg(exif=False, despues=carga), "image/jpeg")
    assert carga not in im.datos and b"<script>" not in im.datos and im.datos.endswith(b"\xff\xd9")
    assert abre(im.datos).size == (1200, 900)


def test_jpeg_progresivo_y_en_gris_se_aceptan():
    assert abre(pl.validar_imagen(jpeg(progresivo=True), "image/jpeg").datos).size == (1200, 900)
    assert abre(pl.validar_imagen(jpeg(modo="L"), "image/jpeg").datos).mode == "L"


def test_jpeg_raro_o_cortado_se_rechaza():
    assert _codigo(pl.validar_imagen, jpeg(modo="CMYK"), "image/jpeg") == (422, "imagen")  # 4 componentes
    entero = jpeg()
    assert _codigo(pl.validar_imagen, entero[:len(entero) // 2], "image/jpeg") == (422, "imagen")  # sin EOI
    assert _codigo(pl.validar_imagen, b"\xff\xd8\xff\xe0\x00\x02" + b"\x00" * 50, "image/jpeg") == (422, "imagen")
    # Un marcador de JPEG sin pérdida (SOF3) no es de una cámara
    raro = entero.replace(b"\xff\xc0", b"\xff\xc3", 1)
    assert _codigo(pl.validar_imagen, raro, "image/jpeg") == (422, "imagen")


def test_png_con_lista_cerrada_de_fragmentos_y_cortado_en_iend():
    crudo = png(despues=b"<?php echo 1; ?>")
    for secreto in (b"TEXTO-SECRETO", b"ITXT-SECRETO", b"eXIf", b"iCCP", b"tIME", b"<?php"):
        assert secreto in crudo
    im = pl.validar_imagen(crudo, "image/png")
    for secreto in (b"TEXTO-SECRETO", b"ITXT-SECRETO", b"zTXt", b"eXIf", b"iCCP", b"tIME", b"<?php", b"tEXt", b"iTXt"):
        assert secreto not in im.datos
    assert b"gAMA" in im.datos and im.datos.endswith(b"IEND\xaeB`\x82")
    assert abre(im.datos).size == (1000, 800)
    assert abre(pl.validar_imagen(png(modo="L", textos=False), "image/png").datos).mode == "L"


def test_png_con_crc_malo_o_critico_desconocido_se_rechaza():
    crudo = png(textos=False)
    malo = bytearray(crudo)
    malo[40] ^= 0xFF  # un byte dentro de un fragmento: su CRC ya no coincide
    assert _codigo(pl.validar_imagen, bytes(malo), "image/png") == (422, "imagen")
    desconocido = crudo[:33] + _trozo(b"ZZZZ", b"x") + crudo[33:]  # crítico (mayúscula) y desconocido
    assert _codigo(pl.validar_imagen, desconocido, "image/png") == (422, "imagen")
    sin_fin = crudo[:-12]
    assert _codigo(pl.validar_imagen, sin_fin, "image/png") == (422, "imagen")
    # Un auxiliar desconocido (minúscula) se quita sin más
    aux = crudo[:33] + _trozo(b"zzZz", b"carga") + crudo[33:]
    assert b"carga" not in pl.validar_imagen(aux, "image/png").datos


def test_tipo_y_firma_tienen_que_coincidir():
    j = jpeg(exif=False)
    assert _codigo(pl.validar_imagen, j, "image/png") == (415, "tipo")
    assert _codigo(pl.validar_imagen, png(textos=False), "image/jpeg") == (415, "tipo")
    assert _codigo(pl.validar_imagen, gif(), "image/gif") == (415, "tipo")
    assert _codigo(pl.validar_imagen, gif(), "image/jpeg") == (415, "tipo")
    assert _codigo(pl.validar_imagen, b"<html></html>", "image/jpeg") == (415, "tipo")
    assert pl.tipo_de("image/jpeg; charset=binary") == "image/jpeg" and pl.tipo_de("IMAGE/PNG") == "image/png"
    assert pl.tipo_de("image/webp") == "image/webp" and pl.tipo_de(None) is None


@pytest.mark.parametrize("ancho,alto,bien", [(150, 150, False), (200, 150, True), (2600, 1800, True),
                                             (2601, 1800, False), (1800, 2700, False), (2600, 99, False),
                                             (2600, 100, True)])
def test_dimensiones(ancho, alto, bien):
    datos = jpeg(ancho, alto, exif=False)
    if bien:
        im = pl.validar_imagen(datos, "image/jpeg")
        assert (im.ancho, im.alto) == (ancho, alto)
    else:
        assert _codigo(pl.validar_imagen, datos, "image/jpeg") == (422, "dimensiones")


def test_png_dimensiones_de_la_cabecera():
    im = pl.validar_imagen(png(400, 2600, textos=False), "image/png")
    assert (im.ancho, im.alto) == (400, 2600)
    # La cabecera miente el tamaño: el CRC no coincide y se rechaza
    crudo = bytearray(png(400, 300, textos=False))
    crudo[16:20] = struct.pack(">I", 2400)
    assert _codigo(pl.validar_imagen, bytes(crudo), "image/png") == (422, "imagen")
    # Con el CRC rehecho, la imagen declara otras dimensiones: se aceptan las de la cabecera
    ihdr = bytes(crudo[12:29])
    crudo[29:33] = struct.pack(">I", zlib.crc32(ihdr) & 0xFFFFFFFF)
    assert pl.validar_imagen(bytes(crudo), "image/png").ancho == 2400
