"""Pruebas de los scripts de la torre: utilidades de comun.py (ids de la regla 1.3, geometría, marco, JSON determinista,
referencias a ambientes), catálogo de equipos, fixtures del Anexo A y reglas de validar_plantas.py y validar_inventario.py
(cada regla se prueba con un fixture alterado a propósito).

Uso: python3 scripts/torre/test_torre.py [-v]
Solo biblioteca estándar.
"""
from __future__ import annotations

import copy
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import comun as C  # noqa: E402

VALIDAR_PLANTAS = AQUI / 'validar_plantas.py'
VALIDAR_INVENTARIO = AQUI / 'validar_inventario.py'
FX = C.FIXTURES


def correr(script: Path, *args) -> tuple[int, dict]:
    p = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True)
    try:
        informe = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise AssertionError(f'{script.name} no imprimió JSON:\n{p.stdout}\n{p.stderr}')
    return p.returncode, informe


def errores(informe: dict) -> dict[str, list[str]]:
    return {r['regla']: r['errores'] for r in informe['reglas'] if r['errores'] and r['estado'] != 'omitida'}


# ------------------------------------------------------------------------------------------------------------------------
class TestIdentificadores(unittest.TestCase):
    def test_h6_del_anexo_a2(self):
        self.assertEqual(C.h6('dotacion', 'consulta_externa', 'm', 'Camilla de examen de prueba'), '2d1bfe')
        self.assertEqual(C.h6('dotacion', 'urgencias', 'm', 'Carro de paro de prueba'), 'a3f0fc')
        self.assertEqual(C.h6('dotacion', 'urgencias', 'e', 'Desfibrilador de prueba'), '2cd8df')

    def test_ids_de_linea_y_unidad(self):
        lid = C.id_linea('urgencias', 'e', 'Desfibrilador de prueba')
        self.assertEqual(lid, 'L-urgencias-e-2cd8df')
        self.assertEqual(C.partes_linea(lid), ('urgencias', 'e', '2cd8df'))
        self.assertEqual(C.id_unidad_de_linea(lid, 1), 'U-urgencias-2cd8df-001')
        self.assertEqual(C.id_componente('U-partos-7e21aa-001', 2), 'U-partos-7e21aa-001-c2')
        self.assertTrue(C.RE_UNIDAD.match('U-partos-7e21aa-001-c2'))
        self.assertEqual(C.id_linea('laboratorio', 'c', 'X'), f'L-laboratorio-c-{C.sha1_texto("laboratorio|laboratorio|c|X")[:6]}')
        self.assertEqual(C.id_linea('hospitalizacion', 'x', 'Y'),
                         f'L-hospitalizacion-x-{C.sha1_texto("cierre_brechas|hospitalizacion|x|Y")[:6]}')
        with self.assertRaises(ValueError):
            C.h6('dotacion', 'urgencias', 'z', 'X')

    def test_el_id_no_depende_del_orden(self):
        nombres = ['A', 'B', 'C']
        ids = {n: C.id_linea('urgencias', 'e', n) for n in nombres}
        self.assertEqual(ids, {n: C.id_linea('urgencias', 'e', n) for n in reversed(nombres)})

    def test_ids_de_planta_y_exigencias(self):
        self.assertEqual(C.id_recinto(1, 15, 2), 'P1-A015-02')
        self.assertEqual(C.id_recinto('BT', 200, 1), 'BT-A200-01')
        self.assertEqual(C.id_circulacion(3, 1), 'P3-CIRC-01')
        self.assertEqual(C.id_muro(2, 137), 'P2-M-0137')
        self.assertEqual(C.id_puerta(1, 14), 'P1-PT-014')
        self.assertEqual(C.id_ventana(1, 6), 'P1-VN-006')
        self.assertEqual(C.id_exigencia('URG', 7), 'EX-URG-007')
        self.assertEqual(C.id_exigencia_todos('C', 3), 'EX-TOD-C03')
        for bueno in ('EX-URG-007', 'EX-TOD-C03', 'EX-TOD-A11', 'EX-ROD-001'):
            self.assertTrue(C.RE_EXIGENCIA.match(bueno), bueno)
        for malo in ('EX-XXX-001', 'EX-TOD-B01', 'EX-URG-7'):
            self.assertFalse(C.RE_EXIGENCIA.match(malo), malo)


class TestGeometria(unittest.TestCase):
    def test_areas_y_rectangulos(self):
        L = [[0, 0], [4, 0], [4, 1], [1, 1], [1, 3], [0, 3]]
        self.assertAlmostEqual(C.area_poligono(L), 6.0)
        self.assertEqual(sum((r[2] - r[0]) * (r[3] - r[1]) for r in C.rectangulos(L)), 6.0)
        self.assertAlmostEqual(C.ancho_minimo(L), 1.0)
        self.assertAlmostEqual(C.ancho_minimo(C.rect_a_poligono([0, 0, 3.6, 2.55])), 2.55)
        cuadro = C.rect_a_poligono([0, 0, 2, 2])
        self.assertAlmostEqual(C.area_interseccion(L, cuadro), 3.0)
        self.assertAlmostEqual(C.area_union([L, cuadro]), 7.0)
        self.assertAlmostEqual(C.area_interseccion(cuadro, C.rect_a_poligono([2, 0, 3, 1])), 0.0)

    def test_poligono_libre_del_anexo_a1(self):
        # consultorio A: fachada (0,20) al occidente y al norte, livianos (0,12) al sur y al oriente
        p = C.rect_a_poligono([0, 4.95, 3.6, 8.55])
        libre = C.redondear_todo(C.desplazar_adentro(p, [0.06, 0.06, 0.10, 0.10]), 3)
        self.assertEqual(libre, [[0.1, 5.01], [3.54, 5.01], [3.54, 8.45], [0.1, 8.45]])
        self.assertAlmostEqual(C.area_poligono(libre), 11.8336, places=4)
        # consultorio B: núcleo (0,30) al oriente
        p = C.rect_a_poligono([3.6, 4.95, 7.2, 8.55])
        self.assertEqual(C.redondear_todo(C.desplazar_adentro(p, [0.06, 0.15, 0.10, 0.06]), 3),
                         [[3.66, 5.01], [7.05, 5.01], [7.05, 8.45], [3.66, 8.45]])

    def test_escalon_en_bordes_colineales(self):
        p = [[0, 0], [2, 0], [4, 0], [4, 2], [0, 2]]
        self.assertEqual(C.redondear_todo(C.desplazar_adentro(p, [0.1, 0.2, 0.1, 0.1, 0.1]), 3),
                         [[0.1, 0.1], [2.0, 0.1], [2.0, 0.2], [3.9, 0.2], [3.9, 1.9], [0.1, 1.9]])

    def test_contencion_y_bordes(self):
        q = C.rect_a_poligono([0, 0, 4, 3])
        self.assertTrue(C.punto_en_poligono((0, 1), q))
        self.assertFalse(C.punto_estrictamente_dentro((0, 1), q))
        self.assertTrue(C.poligono_dentro_de(C.rect_a_poligono([1, 1, 2, 2]), q))
        self.assertFalse(C.poligono_dentro_de(C.rect_a_poligono([3, 1, 5, 2]), q))
        self.assertTrue(C.segmento_en_borde((1, 0), (3, 0), q))
        self.assertFalse(C.segmento_en_borde((1, 0.5), (3, 0.5), q))
        comunes = C.bordes_comunes(q, C.rect_a_poligono([4, 1, 6, 5]))
        self.assertEqual(comunes, [((4, 1), (4, 3))])
        self.assertAlmostEqual(C.largo_cubierto((0, 0), (4, 0), [((0, 0), (1, 0)), ((0.5, 0), (2, 0)), ((3, 0), (5, 0))]), 3.0)

    def test_huellas_giradas(self):
        h = C.rect_girado(1.8, 7.3, 0.65, 1.85, math.pi)
        xs, ys = [v[0] for v in h], [v[1] for v in h]
        self.assertAlmostEqual(min(xs), 1.475)
        self.assertAlmostEqual(max(ys), 8.225)
        lx, ly = C.a_local((1.8, 8.0), 1.8, 7.3, math.pi)
        self.assertAlmostEqual(lx, 0.0, places=9)
        self.assertAlmostEqual(ly, -0.7)          # la espalda (−y local) mira al norte con un giro de 180°
        a = C.rect_girado(0, 0, 1, 1, 0.0)
        self.assertTrue(C.convexos_se_traslapan(a, C.rect_girado(0.5, 0.5, 1, 1, math.pi / 4)))
        self.assertFalse(C.convexos_se_traslapan(a, C.rect_girado(1.0, 0, 1, 1, 0.0)))

    def test_rejilla(self):
        rej = C.Rejilla(0, 0, 10, 1, 0.10)
        rej.pintar_rect(0, 0, 10, 1)
        d = rej.distancias([(0, 5)])
        self.assertAlmostEqual(d[5 * rej.nx + rej.nx - 1], 9.9, places=6)
        rej.pintar_rect(5, 0, 5.1, 0.8, 0)              # tabique con un paso de 0,2 m arriba
        d = rej.distancias([(0, 5)])
        self.assertFalse(math.isinf(d[5 * rej.nx + rej.nx - 1]))
        h = rej.holgura()
        self.assertLessEqual(h[9 * rej.nx + 52], 0.2)

    def test_barrido_de_puertas(self):
        muro = {'a': [0, 4.95], 'b': [3.6, 4.95], 'espesor': 0.12}
        pol = {'C': C.rect_a_poligono([0, 2.4, 7.2, 4.95]), 'A': C.rect_a_poligono([0, 4.95, 3.6, 8.55])}
        pt = {'centro': [1.8, 4.95], 'ancho': 1.0, 'hojas': 1, 'desde': 'C', 'hacia': 'A', 'abre': 'adentro', 'bisagra': 'izquierda'}
        (h,) = C.hojas_puerta(pt, muro, pol)
        self.assertEqual(h['lado'], 'A')
        self.assertAlmostEqual(h['bisagra'][0], 1.3)
        self.assertTrue(C.en_sector((1.6, 5.4), h['bisagra'], h['radio'], h['ang0'], h['ang1']))
        self.assertFalse(C.en_sector((1.6, 4.5), h['bisagra'], h['radio'], h['ang0'], h['ang1']))
        self.assertEqual(len(C.hojas_puerta({**pt, 'abre': 'doble', 'hojas': 2}, muro, pol)), 4)
        self.assertEqual(C.hojas_puerta({**pt, 'abre': 'corrediza'}, muro, pol), [])


class TestMarcoYJson(unittest.TestCase):
    def test_marco(self):
        self.assertEqual(C.a_three([1.0, 2.0, 0.5], 4.5), (1.0, 5.0, -2.0))
        self.assertEqual(C.desde_three((1.0, 5.0, -2.0), 4.5), (1.0, 2.0, 0.5))
        self.assertEqual(C.a_wgs84(0, 0), (C.ANCLA['lat'], C.ANCLA['lon']))
        self.assertEqual(C.giro_three(1.5708), 1.5708)
        self.assertEqual(C.angulo_normalizado(-90), 270)

    def test_redondeos(self):
        self.assertEqual(str(C.redondear(-0.0001, 2)), '0.0')
        self.assertEqual(C.redondear_todo({'a': [1.23456, (2.0001,)]}, 2), {'a': [1.23, [2.0]]})
        self.assertTrue(C.es_multiplo(4.95, 0.05))
        self.assertFalse(C.es_multiplo(4.95, 0.6))
        self.assertTrue(C.es_multiplo(8.4, 0.6, -13.0 + 13.0))

    def test_json_determinista(self):
        datos = {'b': [[0, 0], [1.5, 2]], 'a': 'ñandú', 'c': {'x': list(range(60))}}
        self.assertEqual(C.texto_json(datos), C.texto_json(copy.deepcopy(datos)))
        self.assertIn('ñandú', C.texto_json(datos))
        self.assertIn('"b": [[0, 0], [1.5, 2]]', C.texto_json(datos))
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / 'x.json'
            self.assertTrue(C.escribir_json(ruta, datos))
            self.assertFalse(C.escribir_json(ruta, datos))
            self.assertEqual(C.cargar_json(ruta), datos)
            self.assertEqual(C.insumos_sha1([ruta]), {'x.json': C.sha1_archivo(ruta)})


class TestAmbientes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.amb = C.cargar_json(C.PROGRAMA)['ambientes']

    def test_nombres_repetidos_fallan(self):
        rep = C.nombres_repetidos(self.amb)
        self.assertIn('Ambiente de aseo', rep)
        with self.assertRaises(C.ErrorAmbiente):
            C.resolver_ambiente('Ambiente de aseo', self.amb)
        with self.assertRaises(C.ErrorAmbiente):
            C.resolver_ambiente({'fila': 0, 'nombre': 'otro nombre'}, self.amb)

    def test_referencias_validas(self):
        self.assertEqual(C.resolver_ambiente(0, self.amb), 0)
        self.assertEqual(C.resolver_ambiente({'fila': 4, 'nombre': self.amb[4]['nombre']}, self.amb), 4)
        filas = C.nombres_repetidos(self.amb)['Ambiente de aseo']
        f = filas[0]
        self.assertEqual(C.resolver_ambiente({'servicio_programa': self.amb[f]['servicio'], 'nombre': 'Ambiente de aseo'},
                                             self.amb), f)


class TestCatalogo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = C.cargar_json(C.CATALOGO)
        texto = (C.TORRE / 'ESPECIFICACION_INTEGRACION.md').read_text(encoding='utf-8')
        anexo = texto[texto.index('## Anexo C'):texto.index('## Decisiones de la revisión')]
        cls.ids_anexo = {m.group(1) for m in re.finditer(r'^\|[^|]+\|\s*`([a-z0-9_]+)`\s*\|', anexo, re.M)} - {'modelo3d'}
        # 16.5 (prevalece): modelos que se agregan al Anexo C
        s165 = texto[texto.index('### 16.5'):texto.index('### 16.6')]
        s165 = s165[:s165.index('Mismas reglas')]
        cls.ids_165 = set(re.findall(r'`([a-z0-9_]+)`', s165))

    def test_lista_cerrada_del_anexo_c(self):
        self.assertEqual(len(self.ids_anexo), 118)
        self.assertEqual(len(self.ids_165), 29)
        self.assertFalse(self.ids_anexo & self.ids_165)
        self.assertEqual(set(self.cat['modelos']), self.ids_anexo | self.ids_165)
        self.assertEqual(len(self.cat['modelos']), 147)

    def test_campos_de_cada_modelo(self):
        anclajes, montajes = set(self.cat['anclajes']), set(self.cat['montajes'])
        for mid, m in self.cat['modelos'].items():
            with self.subTest(modelo=mid):
                self.assertIn(m['familia'], self.cat['familias'])
                self.assertEqual(len(m['dim_m']), 3)
                self.assertTrue(all(x > 0 for x in m['dim_m']))
                self.assertIn(m['anclaje'], anclajes)
                self.assertIn(m['montaje'], montajes)
                self.assertTrue(m['masa_kg'] is None or m['masa_kg'] > 0)
                self.assertTrue(0 < m['h_cg_m'] <= m['dim_m'][2] or m['montaje'] == 'cielo')
                self.assertIn(m['apoyo'], self.cat['friccion_por_defecto'])
                self.assertEqual(m['mu'], self.cat['friccion_por_defecto'][m['apoyo']]['mu'])
                self.assertAlmostEqual(m['b_m'], min(m['dim_m'][0], m['dim_m'][1]) / 2, places=3)
                self.assertEqual(m['contenedor'], bool(m.get('compartimientos')))
                self.assertEqual(m['tipo_dato'], 'estimacion')

    def test_valores_del_contrato(self):
        M = self.cat['modelos']
        self.assertEqual(M['cama_hospitalaria']['dim_m'], [1.0, 2.2, 0.95])
        self.assertEqual((M['cama_hospitalaria']['masa_kg'], M['cama_hospitalaria']['h_cg_m'], M['cama_hospitalaria']['mu']), (150, 0.55, 0.3))
        self.assertEqual(M['carro_paro']['compartimientos'], ['superficie', 'cajón 1', 'cajón 2', 'cajón 3', 'cajón 4', 'cajón 5', 'lateral'])
        self.assertEqual(M['silla_ruedas']['mu'], 0.02)
        self.assertEqual(M['camilla_examen']['mu'], 0.5)
        self.assertTrue(M['rayos_x_convencional']['posiciones_fijas'])
        self.assertEqual(M['ascensor_cabina']['montaje'], 'en_nucleo')


class TestFixtures(unittest.TestCase):
    def test_validadores_en_verde(self):
        rc, inf = correr(VALIDAR_PLANTAS, '--fixture', FX / 'plantas_min.json')
        self.assertEqual(rc, 0, errores(inf))
        rc, inf = correr(VALIDAR_INVENTARIO, '--fixture', FX / 'inventario_min_datos.json', FX / 'dotacion_min.json')
        self.assertEqual(rc, 0, errores(inf))
        rc, inf = correr(VALIDAR_INVENTARIO, '--web', FX / 'inventario_min.json')
        self.assertEqual(rc, 0, errores(inf))

    def test_ids_de_los_fixtures_por_la_regla(self):
        inv = C.cargar_json(FX / 'inventario_min_datos.json')
        self.assertEqual({l['id'] for l in inv['lineas']},
                         {'L-urgencias-e-2cd8df', 'L-urgencias-m-a3f0fc', 'L-consulta_externa-m-2d1bfe'})
        for l in inv['lineas']:
            srv, letra, h = C.partes_linea(l['id'])
            self.assertEqual(h, C.h6(l['origen'], srv, letra, l['nombre']))
        web = C.cargar_json(FX / 'inventario_min.json')
        self.assertEqual({l['id'] for l in web['lineas']}, {l['id'] for l in inv['lineas']})
        datos = {u['id']: u for u in inv['unidades']}
        for fila in web['unidades']:
            u = dict(zip(web['columnas_unidades'], fila))
            self.assertEqual([u['x'], u['y'], u['z']], datos[u['id']]['posicion'])
            self.assertEqual(u['recinto'], datos[u['id']]['recinto'])

    def test_huellas_de_insumos(self):
        inv = C.cargar_json(FX / 'inventario_min_datos.json')
        self.assertEqual(inv['insumos_sha1']['dotacion_min.json'], C.sha1_archivo(FX / 'dotacion_min.json'))
        self.assertEqual(inv['insumos_sha1']['plantas_min.json'], C.sha1_archivo(FX / 'plantas_min.json'))
        self.assertEqual(inv['sha256_dotacion'], C.sha256_archivo(FX / 'dotacion_min.json'))

    def test_dos_niveles_con_escalera_y_ascensor(self):
        pl = C.cargar_json(FX / 'plantas_min.json')
        self.assertEqual([n['id'] for n in pl['niveles']], ['P1', 'P2'])
        for n in pl['niveles']:
            self.assertEqual({c['id'] for c in n['conexiones_verticales']}, {'ESC', 'ASC'})
            self.assertEqual(len([r for r in n['recintos'] if r['tipo'] != 'circulacion']), 4)
        filas = sorted(r['fila'] for n in pl['niveles'] for r in n['recintos'] if 'fila' in r)
        self.assertEqual(filas, list(range(8)))


class TestReglasPlantas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = C.cargar_json(FX / 'plantas_min.json')
        cls.tmp = Path(tempfile.mkdtemp(prefix='torre_plantas_'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def alterar(self, cambio) -> dict:
        d = copy.deepcopy(self.base)
        cambio(d['niveles'][0])
        ruta = self.tmp / 'plantas.json'
        ruta.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        rc, inf = correr(VALIDAR_PLANTAS, '--fixture', ruta)
        e = errores(inf)
        self.assertEqual(rc, 1 if e else 0)
        return e

    def test_lados_de_muro(self):
        e = self.alterar(lambda n: n['muros'][0].update(lados=['P1-CIRC-01', 'P1-A000-01']))
        self.assertIn('V1', e)

    def test_traslape(self):
        def f(n):
            n['recintos'][0]['poligono'] = [[0, 4.95], [4.2, 4.95], [4.2, 8.55], [0, 8.55]]
        self.assertIn('V4', self.alterar(f))

    def test_teselado(self):
        def f(n):
            n['contorno'] = [[0, 0], [9.6, 0], [9.6, 9.6], [0, 9.6]]
        self.assertIn('V5', self.alterar(f))

    def test_puerta_angosta_y_fuera_del_muro(self):
        self.assertIn('V11', self.alterar(lambda n: n['puertas'][0].update(ancho=0.8)))
        self.assertIn('V11', self.alterar(lambda n: n['puertas'][0].update(centro=[0.3, 4.95])))

    def test_barridos_que_se_cruzan(self):
        def f(n):
            n['puertas'][0].update(centro=[2.9, 4.95], bisagra='derecha')
            n['puertas'].append({'id': 'P1-PT-005', 'muro': 'P1-M-0003', 'centro': [3.6, 5.7], 'ancho': 1.0, 'alto': 2.1,
                                 'hojas': 1, 'desde': 'P1-A001-01', 'hacia': 'P1-A000-01', 'abre': 'adentro',
                                 'bisagra': 'derecha', 'tipo': 'batiente', 'categoria': 'consultorio'})
            for r in n['recintos'][:2]:
                r['puertas'].append('P1-PT-005')
            n['recintos'][0]['acceso'].append('P1-A001-01')
            n['recintos'][1]['acceso'].append('P1-A000-01')
        self.assertEqual(set(self.alterar(f)), {'V12'})

    def test_sin_puerta(self):
        def f(n):
            n['puertas'] = [p for p in n['puertas'] if p['id'] != 'P1-PT-003']
        e = self.alterar(f)
        self.assertIn('V9', e)
        self.assertIn('V10', e)

    def test_minimo_1633(self):
        self.assertIn('V7', self.alterar(lambda n: n['recintos'][0].update(minimo_1633={'m2': 13.0, 'lado_m': 2.5, 'cita': 'prueba'})))

    def test_corredor_angosto(self):
        def f(n):
            for m in n['muros']:
                if m['id'] in ('P1-M-0001', 'P1-M-0002', 'P1-M-0004'):
                    m.update(tipo='nucleo', espesor=0.30, altura=4.5, estructural=True)
            c = n['recintos'][3]
            c.update(poligono_libre=[[0.1, 2.55], [7.05, 2.55], [7.05, 4.8], [0.1, 4.8]], area_libre_m2=15.64, ancho_libre_m=2.25)
        e = self.alterar(f)
        self.assertIn('V13', e)       # 2,25 m libres < 2,40 m
        self.assertIn('V1', e)        # y los polígonos libres de los consultorios ya no corresponden a sus muros

    def test_sin_salida(self):
        def f(n):
            n['nucleos'][0]['tipo'] = 'ascensor'
        self.assertIn('V14', self.alterar(f))

    def test_rayos_x_sin_plomo(self):
        self.assertIn('V18', self.alterar(lambda n: n['recintos'][0].update(ambiente='Sala de rayos X de prueba')))


class TestReglasInventario(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='torre_inventario_'))
        for n in ('plantas_min.json', 'dotacion_min.json', 'habilitacion_min.json'):
            shutil.copy(FX / n, cls.tmp / n)
        cls.base = C.cargar_json(FX / 'inventario_min_datos.json')
        cls.web = C.cargar_json(FX / 'inventario_min.json')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def alterar(self, cambio, web=False) -> dict:
        d = copy.deepcopy(self.web if web else self.base)
        cambio(d)
        ruta = self.tmp / ('inventario_min.json' if web else 'inventario_min_datos.json')
        ruta.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        args = ('--web', ruta) if web else ('--fixture', ruta, self.tmp / 'dotacion_min.json')
        rc, inf = correr(VALIDAR_INVENTARIO, *args)
        e = errores(inf)
        self.assertEqual(rc, 1 if e else 0)
        return e

    def test_ids_estables(self):
        self.assertIn('I1', self.alterar(lambda d: d['unidades'][0].update(id='U-urgencias-2cd8de-001')))
        self.assertIn('I1', self.alterar(lambda d: d['lineas'][0].update(nombre='Desfibrilador de prueba 2')))

    def test_precios(self):
        self.assertIn('I2', self.alterar(lambda d: d['lineas'][0].update(precio_unitario_cop_2026=1)))

    def test_posiciones(self):
        self.assertIn('I3', self.alterar(lambda d: d['unidades'][1]['posicion'].__setitem__(0, 7.0)))

    def test_traslape_de_huellas(self):
        def f(d):
            u = d['unidades'][1]
            u.update(recinto='P1-A000-01', ambiente='Consultorio de prueba A', posicion=[1.8, 7.3, 0.0])
            d['unidades'][0].update(recinto='P1-A000-01', ambiente='Consultorio de prueba A', posicion=[1.8, 7.3, 1.0])
        self.assertIn('I4', self.alterar(f))

    def test_barrido_de_puerta(self):
        self.assertIn('I5', self.alterar(lambda d: d['unidades'][2]['posicion'].__setitem__(1, 6.0)))

    def test_paso_libre(self):
        self.assertEqual(set(self.alterar(lambda d: d['unidades'][2].update(dim_m=[3.2, 1.85, 0.75])))
                         - {'I3'}, {'I6'})

    def test_exigencias(self):
        self.assertIn('I7', self.alterar(lambda d: d['lineas'][0]['exigencias'][0].update(exigible='por_confirmar')))
        self.assertIn('I7', self.alterar(lambda d: d['lineas'][2].pop('nota_exigencias')))

    def test_clase_de_riesgo(self):
        self.assertIn('I8', self.alterar(lambda d: d['lineas'][0]['clase_riesgo'].update(vigente='IIb (revisar)')))
        self.assertIn('I8', self.alterar(lambda d: d['lineas'][0]['mantenimiento'].update(personal_inscrito_invima=False)))

    def test_apoyo(self):
        self.assertIn('I10', self.alterar(lambda d: d['unidades'][0]['posicion'].__setitem__(2, 0.9)))

    def test_sin_recinto(self):
        self.assertIn('I11', self.alterar(lambda d: d['unidades'][2].update(recinto=None)))

    def test_forma_web(self):
        self.assertIn('catalogo', self.alterar(lambda d: d['catalogo']['carro_paro'].update(mu=0.5), web=True))
        self.assertIn('esquema', self.alterar(lambda d: d['columnas_unidades'].pop(), web=True))
        self.assertIn('I10', self.alterar(lambda d: d['unidades'][2].__setitem__(6, 0.8), web=True))
        self.assertIn('I1', self.alterar(lambda d: d['unidades'].pop(), web=True))


if __name__ == '__main__':
    unittest.main()
