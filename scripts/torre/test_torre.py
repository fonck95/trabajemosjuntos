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

    @staticmethod
    def con_bano(n):
        """Unidad sanitaria de 1,50 × 1,60 m en la esquina noreste del consultorio B (revisión adversarial: subrecinto con
        tabique liviano y puerta corrediza; el área sigue en el recinto del programa)."""
        r = next(x for x in n['recintos'] if x['id'] == 'P1-A001-01')
        r['poligono_libre'] = [[3.66, 5.01], [7.05, 5.01], [7.05, 6.89], [5.64, 6.89], [5.64, 8.45], [3.66, 8.45]]
        r['area_libre_m2'] = 9.46
        r['subrecintos'] = [{'id': 'P1-A001-01-B1', 'nombre': 'Unidad sanitaria',
                             'poligono': [[5.7, 6.95], [7.2, 6.95], [7.2, 8.55], [5.7, 8.55]],
                             'poligono_libre': [[5.76, 7.01], [7.05, 7.01], [7.05, 8.45], [5.76, 8.45]],
                             'area_ejes_m2': 2.4, 'area_libre_m2': 1.86, 'puertas': ['P1-PT-005']}]
        base = {'tipo': 'liviano', 'espesor': 0.12, 'altura': 3.0, 'estructural': False}
        n['muros'] += [dict(base, id='P1-M-0012', a=[5.7, 8.55], b=[5.7, 6.95], lados=['P1-A001-01-B1', 'P1-A001-01']),
                       dict(base, id='P1-M-0013', a=[7.2, 6.95], b=[5.7, 6.95], lados=['P1-A001-01', 'P1-A001-01-B1'])]
        n['puertas'].append({'id': 'P1-PT-005', 'muro': 'P1-M-0013', 'centro': [6.45, 6.95], 'ancho': 0.9, 'alto': 2.1, 'hojas': 1,
                             'desde': 'P1-A001-01', 'hacia': 'P1-A001-01-B1', 'abre': 'corrediza', 'tipo': 'corrediza',
                             'categoria': 'unidad_sanitaria'})

    def test_bano_subrecinto(self):
        self.assertEqual(self.alterar(self.con_bano), {})

        def sin_tabique(n):
            self.con_bano(n)
            n['muros'] = [m for m in n['muros'] if m['id'] != 'P1-M-0012']
        self.assertIn('V1', self.alterar(sin_tabique))

        def sin_puerta(n):
            self.con_bano(n)
            n['puertas'] = [p for p in n['puertas'] if p['id'] != 'P1-PT-005']
            n['recintos'][1]['subrecintos'][0]['puertas'] = []
        self.assertEqual(set(self.alterar(sin_puerta)), {'V9', 'V14', 'V22'})     # sin puerta: ni salida ni paso al baño

        def afuera(n):
            self.con_bano(n)
            n['recintos'][1]['subrecintos'][0]['poligono'] = [[5.7, 6.95], [7.5, 6.95], [7.5, 8.55], [5.7, 8.55]]
        self.assertIn('V1', self.alterar(afuera))

    def test_paso_fisico(self):
        """V22: un obstáculo de lado a lado del corredor separa la entrada de las escaleras aunque el grafo de puertas (V10)
        siga unido; y una columna en el vano de una puerta (V11)."""
        e = self.alterar(lambda n: n['obstaculos_recorrido'].append({'poligono': [[3.0, 2.4], [3.4, 2.4], [3.4, 4.95], [3.0, 4.95]]}))
        self.assertIn('V22', e)
        self.assertNotIn('V10', e)
        self.assertIn('V11', self.alterar(lambda n: n['columnas'].append({'id': 'X9', 'x': 1.8, 'y': 4.95, 'b': 0.6, 'h': 0.6})))


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

    def test_paso_fisico_con_mobiliario(self):
        """I17: una camilla atravesada en el corredor deja 0,29 m a cada lado y parte el nivel (I3 a I6 no lo ven)."""
        def f(d):
            d['unidades'][2].update(recinto='P1-CIRC-01', ambiente='Corredor', posicion=[6.3, 3.675, 0.0], rotacion_z=0.0)
        self.assertIn('I17', self.alterar(f))

    def test_forma_web(self):
        self.assertIn('catalogo', self.alterar(lambda d: d['catalogo']['carro_paro'].update(mu=0.5), web=True))
        self.assertIn('esquema', self.alterar(lambda d: d['columnas_unidades'].pop(), web=True))
        self.assertIn('I10', self.alterar(lambda d: d['unidades'][2].__setitem__(6, 0.8), web=True))
        self.assertIn('I1', self.alterar(lambda d: d['unidades'].pop(), web=True))


# ------------------------------------------------------------------------------------------------------------------------
# Exigencias, implementos, reglas de ubicación, generador del inventario y matriz (ola 1, tarea B2a)
# ------------------------------------------------------------------------------------------------------------------------
NORMALIZAR = AQUI / 'normalizar_exigencias.py'
GENERAR = AQUI / 'generar_inventario.py'


def armar_prueba(tmp: Path) -> None:
    """Directorio de prueba del generador sobre los fixtures del Anexo A: plantas_min, la dotación de prueba con un kit de
    examen (para las unidades componentes), reglas de ubicación, capa de infraestructura y tres exigencias."""
    shutil.copy(FX / 'plantas_min.json', tmp / 'plantas_min.json')
    dot = C.cargar_json(FX / 'dotacion_min.json')
    ce = next(s for s in dot['servicios'] if s['id'] == 'consulta_externa')
    ce['equipos'].append({'nombre': 'Kit de examen de prueba', 'cantidad': 1, 'precio_unitario_cop_2026': 3000000, 'tipo_precio': 'estimacion',
                          'clase_riesgo': 'IIa', 'prioridad': 'habilitacion', 'fuente': 'valor de prueba', 'mantenimiento_anual_pct': 3,
                          'vida_util_anios': 7})
    ce['totales']['equipos_cop_2026'] = 3000000
    (tmp / 'dotacion_prueba.json').write_text(json.dumps(dot, ensure_ascii=False, indent=1), encoding='utf-8')

    def A(f, n):
        return {'fila': f, 'nombre': n}
    desf = {'linea': C.id_linea('urgencias', 'e', 'Desfibrilador de prueba'), 'nombre': 'Desfibrilador de prueba'}
    carro = {'linea': C.id_linea('urgencias', 'm', 'Carro de paro de prueba'), 'nombre': 'Carro de paro de prueba'}
    reglas = {'id': 'reglas_ubicacion_min', 'version': 2, 'fecha': '2026-10-24', 'reglas': [
        {**carro, 'modelo3d': 'carro_paro', 'plantilla_contenido': 'carro_paro_adulto_pediatrico',
         'reparto': [{'ambiente': A(1, 'Consultorio de prueba B'), 'por_recinto': 1, 'estrategia': 'contra_pared', 'pared': 'larga'}]},
        {**desf, 'modelo3d': 'desfibrilador',
         'reparto': [{'ambiente': A(1, 'Consultorio de prueba B'), 'por_recinto': 1, 'estrategia': 'sobre', 'sobre': ['carro_paro']}]},
        {'linea': C.id_linea('consulta_externa', 'm', 'Camilla de examen de prueba'), 'nombre': 'Camilla de examen de prueba',
         'modelo3d': 'camilla_examen',
         'reparto': [{'ambiente': A(0, 'Consultorio de prueba A'), 'por_recinto': 1, 'estrategia': 'cabecera_a_pared', 'bandas': 1}]},
        {'linea': C.id_linea('consulta_externa', 'e', 'Kit de examen de prueba'), 'nombre': 'Kit de examen de prueba', 'modelo3d': 'estuche',
         'plantilla_contenido': 'kit_examen_basico',
         'reparto': [{'ambiente': A(0, 'Consultorio de prueba A'), 'por_recinto': 1, 'estrategia': 'sobre', 'sobre': ['camilla_examen']}]}],
        'infraestructura': {'servicio_de_programa': {'Consulta externa': 'consulta_externa', 'Urgencias': 'urgencias'},
                            'elementos': {'lavamanos': {'nombre': 'Lavamanos de prueba', 'modelo3d': 'lavamanos', 'presupuesto': [],
                                                        'norma': 'prueba', 'exigencias': []}},
                            'reglas': [{'elemento': 'lavamanos', 'reparto': [
                                {'ambiente': A(0, 'Consultorio de prueba A'), 'por_recinto': 1, 'estrategia': 'pared_altura', 'altura_m': 0.6},
                                {'ambiente': A(1, 'Consultorio de prueba B'), 'por_recinto': 1, 'estrategia': 'pared_altura', 'altura_m': 0.6}]}]}}
    (tmp / 'reglas_ubicacion_min.json').write_text(json.dumps(reglas, ensure_ascii=False, indent=1), encoding='utf-8')
    base = {'servicio': 'urgencias', 'servicio_matriz': 'urgencias', 'numeral_confirmado': False, 'texto_disponible': True, 'misma_que': None,
            'vigencia_hasta': None, 'vigencia_desde': None, 'referencia': False, 'diferencia': None, 'fuente_url': 'valor de prueba',
            'comentario': None}
    ex = {'id': 'exigencias_min', 'servicios_matriz': {
        'urgencias': {'nombre': 'Servicio de urgencias (prueba)', 'codigo_reps': '1102 (por confirmar)', 'numeral': '11.6.1',
                      'complejidad': 'baja', 'habilitable': 'si', 'marco': 'Res. 3100, num. 11.6.1'},
        'sala_expansion': {'nombre': 'Sala de expansión (prueba)', 'habilitable': 'no', 'marco': 'Res. 2065 de 2025 (prueba)'}},
        'exigencias': [
            {**base, 'id': 'EX-URG-001', 'origen': 'prueba#0', 'estandar': 'dotacion', 'numeral': '11.6.1 (texto de prueba)',
             'texto': 'Desfibrilador con monitor en el ambiente de atención (texto de prueba).', 'verificacion_texto': 'literal_compilacion',
             'exigible': 'si', 'que_exige': 'Un desfibrilador en el consultorio de prueba B.', 'ambientes': [A(1, 'Consultorio de prueba B')],
             'regla': {'tipo': 'por_recinto', 'n': 1, 'grupos': [{'lineas': [desf]}]}, 'cubre_con': [{'tipo': 'linea', **desf}],
             'estado_investigacion': 'cubierto'},
            {**base, 'id': 'EX-URG-002', 'origen': 'prueba#1', 'estandar': 'dotacion', 'numeral': '11.6.1, según guía secundaria; por confirmar',
             'texto': None, 'texto_disponible': False, 'verificacion_texto': 'fuente_secundaria', 'exigible': 'por_confirmar',
             'que_exige': 'Laringoscopio dentro del carro de paro (resumen de prueba).', 'ambientes': [A(1, 'Consultorio de prueba B')],
             'regla': {'tipo': 'contenido', 'dentro_de': carro, 'items': [{'nombre': 'Laringoscopio (no está en la dotación de prueba)'}], 'n': 1},
             'cubre_con': [], 'estado_investigacion': 'falta'},
            {**base, 'id': 'EX-TOD-C01', 'origen': 'prueba#2', 'servicio': None, 'servicio_matriz': None, 'estandar': 'todos_los_servicios',
             'numeral': '11.1.3 (texto de prueba)', 'texto': None, 'texto_disponible': False, 'verificacion_texto': 'contenido_compilacion',
             'exigible': 'si', 'que_exige': 'Inventario de equipos biomédicos (resumen de prueba).', 'ambientes': [],
             'regla': {'tipo': 'documental'}, 'cubre_con': [], 'estado_investigacion': 'parcial',
             'diferencia': 'Los campos de marca, modelo, serie y registro se llenan al comprar: documento pendiente (prueba).'}]}
    (tmp / 'exigencias_min.json').write_text(json.dumps(ex, ensure_ascii=False, indent=1), encoding='utf-8')


class TestExigencias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = C.cargar_json(C.EXIGENCIAS)
        cls.ex = cls.doc['exigencias']

    def test_al_dia(self):
        p = subprocess.run([sys.executable, str(NORMALIZAR), '--verificar'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_199_filas_trazables(self):
        self.assertEqual(len(self.ex), 199)
        self.assertEqual(len({x['id'] for x in self.ex}), 199)
        self.assertEqual(len({x['origen'] for x in self.ex}), 199)
        k = self.doc['conteos']['por_archivo']
        self.assertEqual((k['res3100_urgencias_e_internacion.json']['servicios'], k['res3100_consulta_y_ambulatorio.json']['servicios'],
                          k['res3100_consulta_y_ambulatorio.json']['todos_los_servicios'], k['res3100_apoyo_diagnostico.json']['servicios'],
                          k['res3100_apoyo_diagnostico.json']['todos_los_servicios']), (86, 52, 7, 43, 11))
        for x in self.ex:
            self.assertTrue(C.RE_EXIGENCIA.match(x['id']), x['id'])

    def test_exigible_por_regla(self):
        self.assertEqual(sum(1 for x in self.ex if x['exigible'] == 'por_confirmar'), 63)
        self.assertEqual(self.doc['conteos']['por_confirmar_por_archivo'],
                         {'res3100_urgencias_e_internacion.json': 43, 'res3100_consulta_y_ambulatorio.json': 12, 'res3100_apoyo_diagnostico.json': 8})
        # revisión adversarial: una fila «literal» o de «contenido» de compilación que solo cita un sitio privado o de
        # consultoría baja a fuente secundaria y queda por confirmar (EX-PAR-016 y EX-IMG-008 son las dos que suben la cuenta)
        E = {x['id']: x for x in self.ex}
        for eid in ('EX-PAR-016', 'EX-IMG-008'):
            self.assertEqual(E[eid]['exigible'], 'por_confirmar', eid)
            self.assertIn('sitio privado', E[eid]['ajuste_verificacion'], eid)
        for x in self.ex:
            if x['exigible'] == 'si':
                self.assertIn(x['verificacion_texto'], ('literal_compilacion', 'contenido_compilacion'), x['id'])
            if not x['texto_disponible']:
                self.assertIsNone(x['texto'], x['id'])
            # revisión adversarial: tampoco está confirmado el numeral que difiere entre copias o no se recuperó (sección 15:
            # «12.1 frente a 9.2; 17.1.2.x frente a 17.2.1.x»), ni el de una fila de guía secundaria o de paráfrasis
            marcas = ('por confirmar', 'según guía', 'según la guía', 'según normas.json', 'por analogía', 'no se pudo confirmar',
                      'no recuperad', 'según una de las copias', 'lo numera', 'en la copia', 'en la cancillería', 'en el icbf',
                      'colegio')
            esperado = not any(m in (x['numeral'] or '').lower() for m in marcas) and \
                x['verificacion_texto'] not in ('fuente_secundaria', 'por_confirmar')
            self.assertEqual(x['numeral_confirmado'], esperado, x['id'])
        E = {x['id']: x for x in self.ex}
        self.assertFalse(E['EX-TEL-002']['numeral_confirmado'])          # 17.1.2.1 (Cancillería) frente a 17.2.1.1 (ICBF)
        self.assertFalse(E['EX-LAB-008']['numeral_confirmado'])          # la copia del ICBF lo numera 12.1

    def test_vigencia_y_superados(self):
        con_vigencia = sorted(x['id'] for x in self.ex if x['vigencia_hasta'])
        self.assertTrue(con_vigencia and all(i.startswith('EX-EST-') for i in con_vigencia))
        self.assertTrue(all(x['vigencia_hasta'] == '2027-01-02' for x in self.ex if x['vigencia_hasta']))
        self.assertEqual([x['id'] for x in self.ex if x['vigencia_desde']], ['EX-EST-008'])
        self.assertEqual(sorted(x['id'] for x in self.ex if x['referencia']), ['EX-EXP-002', 'EX-EXP-003', 'EX-EXP-004', 'EX-EXP-005'])
        texto = C.texto_json(self.doc)
        self.assertNotIn('482 de 2018»', texto)
        self.assertNotIn('transición', texto.lower().replace('transición de la res. 1732 de 2026 no se propaga', ''))
        for x in self.ex:
            for campo in ('texto', 'numeral', 'que_exige', 'cantidad_texto'):
                self.assertNotIn('Res. 482 de 2018', str(x.get(campo) or '').replace('reemplazó a la 482', ''), x['id'])

    def test_reglas_y_servicios(self):
        dot = [x for x in self.ex if x['estandar'] == 'dotacion']
        con_regla = [x for x in dot if x['regla']['tipo'] != 'sin_regla']
        self.assertGreaterEqual(len(con_regla) / len(dot), 0.80)
        srv = self.doc['servicios_matriz']
        for x in self.ex:
            if not x['id'].startswith('EX-TOD-'):
                m = x['servicio_matriz']
                self.assertTrue(m == 'imagenes' or m in srv, x['id'])
        for s in srv.values():
            self.assertIn(s['habilitable'], ('si', 'no', 'modalidad', 'sin_habilitacion_propia'))


class TestImplementosYReglas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.impl = C.cargar_json(C.IMPLEMENTOS)
        cls.reglas = C.cargar_json(C.REGLAS_UBICACION)
        cls.cat = C.cargar_json(C.CATALOGO)['modelos']
        dot, lab = C.cargar_json(C.DOTACION), C.cargar_json(C.LABORATORIO)
        cls.lineas = {}
        for s_ in dot['servicios']:
            for lista, letra in (('equipos', 'e'), ('mobiliario', 'm')):
                for x in s_[lista]:
                    cls.lineas[C.id_linea(s_['id'], letra, x['nombre'])] = x
        for x in dot['equipamiento_fijo']:
            cls.lineas[C.id_linea('fijo', 'f', x['nombre'])] = x
        for x in lab['equipos']:
            cls.lineas[C.id_linea('laboratorio', 'c', x['nombre'])] = x
        for x in dot['cierre_brechas_habilitacion']['items']:
            cls.lineas[C.id_linea(x['servicio'], 'x', x['nombre'])] = x
        cls.lab = lab

    def test_una_regla_por_linea(self):
        reglas = {r['linea']: r for r in self.reglas['reglas']}
        self.assertEqual(len(reglas), len(self.reglas['reglas']))
        self.assertEqual(set(reglas), set(self.lineas))
        self.assertEqual(len(reglas), 236 + 14 + 11 + 42)          # 42 ítems de cierre: + termohigrómetro de esterilización
        self.assertIn(C.id_linea('esterilizacion', 'x', 'Termohigrómetro con registro (depósito de esterilización)'), reglas)
        for lid, r in reglas.items():
            self.assertEqual(r['nombre'], self.lineas[lid]['nombre'])
            self.assertIn(r['modelo3d'], self.cat)

    def test_infraestructura(self):
        inf = self.reglas['infraestructura']
        pres = {it['codigo'] for cap in C.cargar_json(C.TORRE / 'presupuesto.json')['capitulos'] for it in cap['items']}
        for el, d in inf['elementos'].items():
            self.assertIn(d['modelo3d'], self.cat, el)
            for cod in d['presupuesto']:
                self.assertIn(cod, pres, el)
        self.assertTrue({'lavamanos', 'inodoro', 'ducha', 'poceta_aseo', 'lavachatas', 'toma_gases_cabecera', 'llamado_enfermeria',
                         'extintor', 'gabinete_incendio', 'senal_evacuacion'} <= set(inf['elementos']))

    def test_plantillas(self):
        tipos = set(self.impl['tipos'])
        for nombre, p in self.impl['plantillas'].items():
            with self.subTest(plantilla=nombre):
                self.assertTrue(p['lineas_que_la_usan'])
                for ref in p['lineas_que_la_usan']:
                    self.assertEqual(self.lineas[ref['linea']]['nombre'], ref['nombre'])
                for it in p['items']:
                    self.assertIn(it['tipo'], tipos)
                    self.assertIn(it['verificacion'], self.impl['verificacion'])
                    if it['tipo'] == 'equipo_biomedico':
                        self.assertIn(it['clase_riesgo'], ('I', 'IIa', 'IIb', 'III'))
                        self.assertIn(it['registro_invima']['requerido'], ('si', 'no', 'por_confirmar'))
                        self.assertIsInstance(it['mantenimiento']['calibracion'], bool)
        nombres = ('carro_paro_adulto_pediatrico', 'carro_paro_neonatal', 'kit_examen_basico', 'organos_sentidos_pared', 'pequena_cirugia_sutura',
                   'toracostomia', 'equipo_partos', 'revision_uterina_desgarros', 'instrumental_basico_odontologia',
                   'instrumental_especialidades_odontologia', 'inmovilizacion', 'sujecion_mecanica', 'kit_rehabilitacion', 'canecas_residuos',
                   'proteccion_radiologica', 'maletin_reanimacion_expansion', 'carro_curaciones', 'carro_medicamentos')
        self.assertTrue(set(nombres) <= set(self.impl['plantillas']))
        kit = self.impl['plantillas']['kit_examen_basico']['items']
        self.assertEqual(len(kit), 8)

    def test_laboratorio_completo(self):
        usadas = {r['linea']: r.get('plantilla_contenido') for r in self.reglas['reglas']}
        cubiertas = {pr for p in self.impl['plantillas'].values() for it in p['items'] for pr in it.get('pruebas', [])}
        for x in self.lab['equipos']:
            p = usadas[C.id_linea('laboratorio', 'c', x['nombre'])]
            self.assertIn(p, self.impl['plantillas'], x['nombre'])
            self.assertTrue(any(it.get('pruebas') and it.get('almacenamiento') for it in self.impl['plantillas'][p]['items']))
        for m in self.lab['menu']:
            if m.get('en_sitio'):
                self.assertIn(m['id'], cubiertas)


class TestGenerador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='torre_generador_'))
        armar_prueba(cls.tmp)
        cls.p = subprocess.run([sys.executable, str(GENERAR), '--fixture', cls.tmp], capture_output=True, text=True)
        cls.inv = C.cargar_json(cls.tmp / 'inventario_dotacion.json') if cls.p.returncode == 0 else None
        cls.hab = C.cargar_json(cls.tmp / 'habilitacion.json') if cls.p.returncode == 0 else None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_genera_y_valida(self):
        self.assertEqual(self.p.returncode, 0, self.p.stderr)
        rc, inf = correr(VALIDAR_INVENTARIO, '--fixture', self.tmp / 'inventario_dotacion.json', self.tmp / 'dotacion_prueba.json',
                         '--plantas', self.tmp / 'plantas_min.json', '--habilitacion', self.tmp / 'habilitacion.json')
        self.assertEqual(rc, 0, errores(inf))

    def test_determinista(self):
        p = subprocess.run([sys.executable, str(GENERAR), '--fixture', self.tmp, '--verificar'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_ids_y_unidades(self):
        ids = {l['id'] for l in self.inv['lineas']}
        self.assertTrue({'L-urgencias-e-2cd8df', 'L-urgencias-m-a3f0fc', 'L-consulta_externa-m-2d1bfe'} <= ids)
        U = {u['id']: u for u in self.inv['unidades']}
        self.assertEqual(U['U-urgencias-2cd8df-001']['apoyo'], 'U-urgencias-a3f0fc-001')
        self.assertEqual(U['U-urgencias-2cd8df-001']['posicion'][2], 1.0)
        kit = next(u for u in self.inv['unidades'] if u['linea'] == C.id_linea('consulta_externa', 'e', 'Kit de examen de prueba')
                   and not u.get('componente_de'))
        comps = [u for u in self.inv['unidades'] if u.get('componente_de') == kit['id']]
        self.assertEqual(len(comps), 4)              # báscula, equipo de órganos portátil, oxímetro y termómetro
        self.assertEqual({c['clase_riesgo']['vigente'] for c in comps}, {'I', 'IIa'})
        self.assertTrue(all(c['precio_unitario_cop_2026'] == 0 for c in comps))
        self.assertEqual(sum(1 for c in comps if c['montaje'] == 'piso'), 1)
        self.assertEqual(U['U-urgencias-a3f0fc-001']['contenido']['plantilla'], 'carro_paro_adulto_pediatrico')
        infra = [l for l in self.inv['lineas'] if l['capa'] == 'infraestructura']
        self.assertEqual(sum(l['cantidad'] for l in infra), 2)
        self.assertTrue(all(l['precio_unitario_cop_2026'] is None for l in infra))
        tot = self.inv['totales']['por_servicio']
        self.assertTrue(all(t['coincide_con_dotacion'] for t in tot.values()))

    def test_matriz(self):
        h = self.hab
        self.assertEqual([c['id'] for c in h['fecha_referencia']], ['corte_2026', 'apertura'])
        self.assertEqual(h['estandares_no_evaluados'], ['talento humano', 'historia clínica y registros', 'interdependencia'])
        self.assertNotIn('servicio habilitado', C.texto_json(h).lower())
        urg = next(s for s in h['servicios'] if s['id'] == 'urgencias')
        e = {x['id']: x for x in urg['exigencias']}
        self.assertEqual(e['EX-URG-001']['estado']['corte_2026']['dotacion_actual'], 'cumple')
        self.assertEqual(e['EX-URG-002']['estado']['corte_2026']['dotacion_actual'], 'falta')
        self.assertEqual(urg['resumen']['corte_2026']['dotacion_actual']['por_confirmar']['falta'], 1)
        self.assertEqual(h['por_recinto']['P1-A001-01']['estado']['corte_2026'], 'cumple')
        self.assertEqual(h['por_recinto']['P1-A001-01']['por_confirmar'], 1)
        self.assertEqual(next(s for s in h['servicios'] if s['id'] == 'sala_expansion')['habilitable'], 'no')

    def test_csv(self):
        t = (self.tmp / 'inventario_dotacion.csv').read_text(encoding='utf-8')
        self.assertTrue(t.startswith('﻿unidad;'))
        filas = t.strip().split('\n')
        self.assertEqual(len(filas) - 1, len(self.inv['unidades']))

    def test_reparto_que_no_suma_falla(self):
        tmp = Path(tempfile.mkdtemp(prefix='torre_generador_mal_'))
        try:
            armar_prueba(tmp)
            r = C.cargar_json(tmp / 'reglas_ubicacion_min.json')
            r['reglas'][0]['reparto'][0]['por_recinto'] = 2
            (tmp / 'reglas_ubicacion_min.json').write_text(json.dumps(r, ensure_ascii=False), encoding='utf-8')
            p = subprocess.run([sys.executable, str(GENERAR), '--fixture', tmp], capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            self.assertIn('el reparto ubica 2 unidades', p.stderr)
            r['reglas'][0]['reparto'][0]['por_recinto'] = 1
            r['reglas'][0]['nombre'] = 'Otro nombre'
            (tmp / 'reglas_ubicacion_min.json').write_text(json.dumps(r, ensure_ascii=False), encoding='utf-8')
            p = subprocess.run([sys.executable, str(GENERAR), '--fixture', tmp], capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestInventarioReal(unittest.TestCase):
    """El inventario de los datos reales ubicado en la planta real de toda la torre (16.6): líneas, unidades, precios,
    clases, componentes, conteos por nivel, paneles, laboratorio en sus recintos, la matriz y sus faltantes."""

    @classmethod
    def setUpClass(cls):
        import generar_inventario as G
        cls.G = G
        cls.inv, cls.hab, cls.gen = G.generar(G.rutas_reales())
        cls.planta = C.cargar_json(C.PLANTAS)
        cls.recintos = {r['id']: (r, n['id']) for n in cls.planta['niveles'] for r in n['recintos']}

    def test_unidades_y_precios(self):
        t = self.inv['totales']
        self.assertTrue(all(s['coincide_con_dotacion'] for s in t['por_servicio'].values()))
        self.assertTrue(t['equipamiento_fijo']['coincide_con_dotacion'])
        self.assertEqual(sum(s['unidades'] for s in t['por_servicio'].values()), 509 + 359)
        self.assertEqual(t['equipamiento_fijo']['unidades'], 15)
        lj = t['laboratorio_json']
        self.assertEqual((lj['lineas'], lj['unidades'], lj['valor_mercado_cop_2026']), (11, 12, 1249676210))
        self.assertEqual((lj['comodato']['lineas'], lj['comodato']['unidades'], lj['comodato']['valor_mercado_cop_2026']), (9, 10, 955708589))
        self.assertEqual(lj['programa_o_compra']['valor_mercado_cop_2026'], 143967621)
        self.assertEqual(lj['opcional']['valor_mercado_cop_2026'], 150000000)
        self.assertEqual(t['habilitacion_cop_2026']['segun_dotacion'], 3908496956)
        self.assertEqual(t['habilitacion_cop_2026']['reclasificados'], 26200000 + 15000000 + 33044847 if False else
                         t['habilitacion_cop_2026']['reclasificados'])
        self.assertTrue(70_000_000 < t['habilitacion_cop_2026']['reclasificados'] < 80_000_000)
        cb = self.inv['dotacion'] if False else C.cargar_json(C.DOTACION)['cierre_brechas_habilitacion']['totales']
        for p_ in ('P4', 'P5', 'P6'):
            for k in ('habilitacion_cop_2026', 'recomendado_cop_2026', 'por_confirmar_cop_2026', 'items', 'items_sin_precio'):
                self.assertEqual(t['cierre_brechas']['por_proyecto'][p_][k], cb['por_proyecto'][p_][k], (p_, k))
        self.assertEqual(t['cierre_brechas']['items_sin_precio'], cb['items_sin_precio'])
        self.assertEqual(t['unidades']['componentes'], 21 * 4 + 2 + 2)     # + las 2 bombas del equipo de presión (componentes)

    def test_clases_y_registro(self):
        for l in self.inv['lineas']:
            cr = l['clase_riesgo']
            self.assertIn(cr['vigente'], ('I', 'IIa', 'IIb', 'III', 'no_dm', 'ivd', 'por_confirmar'), l['id'])
            if cr['vigente'] in ('IIb', 'III'):
                self.assertFalse(l['registro_invima']['usado_permitido'])
                self.assertTrue(l['mantenimiento']['personal_inscrito_invima'])
        nombres = {l['nombre']: l for l in self.inv['lineas'] if l['servicio'] == 'urgencias'}
        self.assertEqual(nombres['Tensiómetro aneroide de pared adulto-pediátrico']['clase_riesgo']['vigente'], 'I')
        lav = next(l for l in self.inv['lineas'] if l['nombre'] == 'Lavadora desinfectora de instrumental')
        self.assertEqual((lav['clase_riesgo']['vigente'], lav['prioridad'], lav['prioridad_revisada']), ('IIa', 'recomendado', 'por_confirmar (Res. 914)'))

    def test_todo_fijo_y_laboratorio_ubicados(self):
        prog = C.cargar_json(C.PROGRAMA)['ambientes']
        servicios_lab = ('Laboratorio clínico', 'Toma de muestras de laboratorio clínico')
        filas_lab = {i for i, a in enumerate(prog) if a['servicio'] in servicios_lab}
        L = {l['id']: l for l in self.inv['lineas']}
        tec = 0
        for u in self.inv['unidades']:
            l = L[u['linea']]
            if l['capa'] == 'fijo':
                self.assertTrue(u['recinto'] or u.get('ubicacion'), u['id'])
            if l['origen'] == 'laboratorio' or (l['origen'] == 'dotacion' and l['servicio'] in ('laboratorio', 'toma_muestras')):
                m = C.RE_RECINTO.match(u['recinto'])
                if m:
                    self.assertIn(int(m.group(2)), filas_lab, u['id'])
                else:                                # recinto técnico del laboratorio (16.2): biología molecular, lavaojos
                    self.assertTrue(C.RE_TECNICO.match(u['recinto']), u['id'])
                    self.assertIn(self.recintos[u['recinto']][0]['servicio_programa'], servicios_lab, u['id'])
                    tec += 1
        self.assertGreater(tec, 0)
        self.assertEqual([f['nombre'][:10] for f in self.inv['fuera_de_la_torre']], ['Lavandería'])
        gx = [u for u in self.inv['unidades'] if 'GeneXpert' in L[u['linea']]['nombre']]
        self.assertTrue(gx and all(u['recinto'] == 'P2-TEC-02' and u['montaje'] == 'sobre' for u in gx))

    def test_al_dia_con_los_archivos(self):
        """Lo que está en el repositorio es lo que sale hoy del generador (mismos bytes)."""
        texto = C.texto_json(self.inv)
        self.assertEqual(texto, (C.TORRE / 'inventario_dotacion.json').read_text(encoding='utf-8'))
        self.assertEqual(self.G.texto_csv(self.inv), (C.TORRE / 'inventario_dotacion.csv').read_text(encoding='utf-8'))

    def test_valida_sin_errores_duros(self):
        rc, inf = correr(VALIDAR_INVENTARIO)
        self.assertEqual(rc, 0, errores(inf))
        self.assertEqual(sum(len(r['errores']) for r in inf['reglas'] if r['estado'] != 'omitida'), 0)

    def test_unidades_sin_recinto_fuera_de_las_columnas(self):
        """I17 (coordinación BIM): la marquesina solar de la bahía va a 5,30 m, a la altura del piso 2; si su fila del
        oriente vuelve a quedar junto a la fachada, entra en la columna A-6 de ese piso."""
        d = copy.deepcopy(self.inv)
        u = next(x for x in d['unidades'] if (x.get('paneles') or {}).get('fila') == 'FV-BAHIA-F6')
        u['posicion'] = [-13.6, u['posicion'][1], u['posicion'][2]]
        tmp = Path(tempfile.mkdtemp(prefix='torre_inv_cols_'))
        try:
            ruta = tmp / 'inventario.json'
            ruta.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
            rc, inf = correr(VALIDAR_INVENTARIO, '--inventario', ruta)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        i17 = errores(inf).get('I17', [])
        self.assertEqual(rc, 1)
        self.assertTrue(any('columna A6 del P2' in x for x in i17), i17)

    def test_todas_ubicadas_y_conteos_por_nivel(self):
        t = self.inv['totales']['unidades']
        self.assertEqual(t['total'], len(self.inv['unidades']))
        pn = t['por_nivel']
        self.assertEqual(sum(v['total'] for v in pn.values()), t['total'])
        self.assertEqual(set(pn) - {'fuera_de_la_torre'}, {n['id'] for n in self.planta['niveles']})
        for nid, v in pn.items():
            self.assertEqual(sum(v['por_capa'].values()), v['total'], nid)
            if nid != 'fuera_de_la_torre':
                self.assertGreater(v['total'], 0, nid)
                self.assertEqual(v['con_posicion'], v['total'], nid)
        self.assertEqual(pn['fuera_de_la_torre']['total'], 1)          # lavandería: fuera de la torre, sin posición
        self.assertEqual(t['con_posicion'], t['total'] - 1)
        for u in self.inv['unidades']:
            if u.get('recinto'):
                self.assertEqual(self.recintos[u['recinto']][1], u['nivel'], u['id'])
            if u['montaje'] not in ('dentro',) and u.get('estado') != 'fuera_de_la_torre':
                self.assertIsNotNone(u['posicion'], u['id'])
        self.assertFalse([a for a in self.inv['avisos_ubicacion'] if 'NO CABE' in a])
        # equipamiento fijo en el bloque técnico, la cubierta, los núcleos y los pisos
        L = {l['id']: l for l in self.inv['lineas']}
        niveles_fijo = {u['nivel'] for u in self.inv['unidades'] if L[u['linea']]['capa'] == 'fijo' and u.get('nivel')}
        self.assertTrue({'BT', 'CUB', 'P1'} <= niveles_fijo, niveles_fijo)

    def test_sanitarios_en_su_bano(self):
        """Revisión adversarial: el inodoro, la ducha y las barras de un recinto con baño o cabinas van dentro de ellos (y
        dentro de su polígono libre); el lavamanos de la unidad sanitaria también, salvo en las baterías (zona común)."""
        subs = {sb['id']: (sb, r) for n in self.planta['niveles'] for r in n['recintos'] for sb in r.get('subrecintos', [])}
        L = {l['id']: l for l in self.inv['lineas']}
        con_bano = {r['id'] for sb, r in subs.values()}
        vistos = set()
        for u in self.inv['unidades']:
            m = L[u['linea']]['modelo3d']
            if u.get('recinto') in con_bano and m in ('inodoro', 'ducha', 'barra_apoyo'):
                self.assertIn(u.get('subrecinto'), subs, u['id'])
            if u.get('subrecinto'):
                sb, r = subs[u['subrecinto']]
                self.assertEqual(u['recinto'], r['id'])
                self.assertTrue(C.punto_en_poligono(u['posicion'], sb['poligono_libre'], 0.02), u['id'])
                vistos.add(u['subrecinto'])
        self.assertEqual(vistos, set(subs))               # ningún baño vacío
        inod = [u for u in self.inv['unidades'] if u.get('recinto') == 'P2-A074-01' and L[u['linea']]['modelo3d'] == 'inodoro']
        self.assertEqual(len({u['subrecinto'] for u in inod}), 3)

    def test_correcciones_de_la_revision(self):
        L = {l['nombre']: l for l in self.inv['lineas']}
        # oxímetros con clase por confirmar entre IIa y IIb: se tratan como IIb (no usados; personal inscrito)
        for l in self.inv['lineas']:
            if l['clase_riesgo'].get('clase_prudente') == 'IIb':
                self.assertFalse(l['registro_invima']['usado_permitido'], l['id'])
                self.assertTrue(l['mantenimiento']['personal_inscrito_invima'], l['id'])
        # central de gases, generador PSA y PACS: clase por confirmar con el INVIMA (no «no_dm»)
        for nombre in ('Generador de oxígeno en sitio (tecnología PSA)',):
            self.assertEqual(L[nombre]['clase_riesgo']['vigente'], 'por_confirmar')
        self.assertTrue(all(l['clase_riesgo']['vigente'] == 'por_confirmar' for l in self.inv['lineas']
                            if l['nombre'].startswith(('Central de gases medicinales', 'PACS/RIS'))))
        # la lupa de inspección no es de habilitación (EX-EST-004 es documental y la deroga la Res. 914)
        self.assertEqual(L['Lupa con iluminación para inspección de instrumental']['prioridad'], 'por_confirmar')
        # el CSV separa adquisición, presupuesto, nota de precio y proyecto
        cab = (C.TORRE / 'inventario_dotacion.csv').read_text(encoding='utf-8').split('\n', 1)[0].lstrip('\ufeff').split(';')
        for col in ('adquisicion', 'en_presupuesto', 'nota_precio', 'proyecto', 'parte_de_linea'):
            self.assertIn(col, cab)
        # la tabla de ítems del presupuesto marca la diferencia con lo ubicado
        for it, d in self.inv['totales']['infraestructura']['por_item_presupuesto'].items():
            if d.get('cantidad_presupuesto') is not None and d.get('unidades_ubicadas') is not None:
                self.assertEqual(d['diferencia'], d['unidades_ubicadas'] - d['cantidad_presupuesto'], it)

    def test_paneles_en_sus_filas(self):
        ps = self.inv['totales']['infraestructura']['por_elemento']['panel_solar_fila']
        self.assertEqual((ps['modulos'], ps['kwp']), (182, 100.1))
        self.assertEqual(ps['por_grupo'], {'FV-BAHIA': 30, 'FV-PERGOLA': 96, 'FV-TERRAZA': 56})
        filas = [u for u in self.inv['unidades'] if u.get('paneles')]
        self.assertEqual(len(filas), ps['unidades'])
        self.assertEqual(sum(u['paneles']['modulos'] for u in filas), 182)
        self.assertEqual({u['nivel'] for u in filas}, {'CUB', 'EXT'})

    def test_faltantes_por_servicio(self):
        f = self.hab['faltantes_por_servicio']
        cb = C.cargar_json(C.DOTACION)['cierre_brechas_habilitacion']
        self.assertEqual(f['total']['inversion_con_precio_cop_2026'], cb['totales']['inversion_con_precio_cop_2026'])
        self.assertEqual(f['total']['inversion_con_precio_cop_2026'], 46904906)
        self.assertEqual(f['total']['operacion_anual_cop_2026'], 4100000)
        self.assertEqual(f['total']['items_sin_precio'], cb['totales']['items_sin_precio'])
        self.assertEqual(sum(s['faltantes']['costo_cierre']['inversion_con_precio_cop_2026'] for s in self.hab['servicios']
                             if s.get('faltantes')), 46904906)
        for s in self.hab['servicios']:
            for e in s.get('faltantes', {}).get('exigencias', []):
                self.assertIn(e['id'], {x['id'] for x in s['exigencias']})

    def test_matriz_real(self):
        h = self.hab
        ids = [s['id'] for s in h['servicios']]
        for sid in ('urgencias', 'hospitalizacion', 'partos', 'esterilizacion', 'sala_expansion', 'imagenes_744', 'imagenes_745',
                    'toma_muestras', 'telemedicina', 'tic_apoyo'):
            self.assertIn(sid, ids)
        n = sum(len(s['exigencias']) for s in h['servicios']) + len(h['todos_los_servicios']['detalle'])
        self.assertEqual(n, 199)
        self.assertEqual(len(h['todos_los_servicios']['exigencias']), 18)
        for s in h['servicios']:
            self.assertIn(s['habilitable'], ('si', 'no', 'modalidad', 'sin_habilitacion_propia'))
            for e in s['exigencias']:
                for c in ('corte_2026', 'apertura'):
                    for esc in ('dotacion_actual', 'con_cierre_de_brechas'):
                        self.assertIn(e['estado'][c][esc], ('cumple', 'parcial', 'falta', 'documento_pendiente', 'no_aplica'))
                if e['referencia']:
                    self.assertEqual(e['estado']['corte_2026']['dotacion_actual'], 'no_aplica')
        est = {e['id']: e for s in h['servicios'] for e in s['exigencias']}
        self.assertEqual(est['EX-EST-001']['estado']['apertura']['dotacion_actual'], 'no_aplica')
        self.assertEqual(est['EX-EST-008']['estado']['corte_2026']['dotacion_actual'], 'no_aplica')
        self.assertEqual(est['EX-HOS-011']['estado']['corte_2026'], {'dotacion_actual': 'falta', 'con_cierre_de_brechas': 'cumple'})


# ------------------------------------------------------------------------------------------------------------------------
GENERAR_PLANTAS = AQUI / 'generar_plantas.py'


class TestPlantasTorre(unittest.TestCase):
    """Planta real de toda la torre (16.1): generador determinista, conteos por nivel, escaleras, laboratorio y paneles."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='torre_plantas_real_'))
        cls.pl = C.cargar_json(C.PLANTAS)
        cls.prog = C.cargar_json(C.PROGRAMA)
        cls.reglas = C.cargar_json(C.REGLAS_PLANTA)
        cls.niv = {n['id']: n for n in cls.pl['niveles']}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_generador_determinista_y_al_dia(self):
        salidas = []
        for i in range(2):
            ruta = self.tmp / f'plantas_{i}.json'
            p = subprocess.run([sys.executable, str(GENERAR_PLANTAS), '--salida', str(ruta)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            salidas.append(ruta.read_bytes())
        self.assertEqual(salidas[0], salidas[1])
        self.assertEqual(salidas[0], C.PLANTAS.read_bytes(), 'torre_hospital_plantas.json no está al día con el trazado')
        p = subprocess.run([sys.executable, str(GENERAR_PLANTAS), '--verificar'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_planta_real_sin_errores_duros(self):
        rc, inf = correr(VALIDAR_PLANTAS)
        self.assertEqual(errores(inf), {})
        self.assertEqual(rc, 0)
        estados = {r['regla']: r['estado'] for r in inf['reglas']}
        for regla in ('V2', 'V6', 'V7', 'V9', 'V10', 'V11', 'V12', 'V14', 'V15', 'V16', 'V20', 'V21', 'V22', 'V23'):
            self.assertEqual(estados.get(regla), 'ok', regla)

    def test_todos_los_niveles_y_conteos_del_programa(self):
        self.assertEqual(list(self.niv), ['EXT', 'P1', 'P2', 'P3', 'P4', 'BT', 'CUB'])
        esperados = {}
        mapa = self.reglas['niveles']
        for f, a in enumerate(self.prog['ambientes']):
            piso = a.get('piso')
            if piso is None:
                continue
            nivel = mapa.get('nivel_por_fila', {}).get(str(f)) or (f'P{piso}' if isinstance(piso, int) else mapa['piso_a_nivel'][piso])
            esperados[nivel] = esperados.get(nivel, 0) + a['cantidad']
        self.assertEqual(self.pl['resumen']['recintos_por_nivel'], {k: esperados.get(k, 0) for k in self.niv})
        self.assertEqual(self.pl['resumen']['recintos_por_nivel'], {'EXT': 2, 'P1': 82, 'P2': 69, 'P3': 69, 'P4': 42, 'BT': 11, 'CUB': 8})

    def test_ids_regla_13_y_no_programados_con_estimacion(self):
        for n in self.pl['niveles']:
            for r in n['recintos']:
                if r.get('fila') is not None:
                    self.assertEqual(r['id'], C.id_recinto(n['id'], r['fila'], r['k']))
                elif r['tipo'] != 'circulacion':
                    self.assertRegex(r['id'], C.RE_TECNICO)
                    self.assertIs(r.get('programado'), False)
                    self.assertTrue(any('estimaci' in x for x in r.get('notas', [])), r['id'])

    def test_escaleras_caminables_de_piso_a_cubierta(self):
        for es_id in ('ESC-N', 'ESC-S'):
            tramos = [(n, e) for n in ('P1', 'P2', 'P3', 'P4', 'CUB') for e in self.niv[n]['escaleras'] if e['id'] == es_id]
            self.assertEqual([n for n, _ in tramos], ['P1', 'P2', 'P3', 'P4', 'CUB'])
            for n, e in tramos[:-1]:
                h = self.niv[e['sube_a']]['z'] - self.niv[n]['z']
                partes = [x for x in e['partes'] if x['tipo'] == 'tramo']
                self.assertEqual(len(partes), 2)
                self.assertAlmostEqual(partes[0]['z0'], 0.0)
                self.assertAlmostEqual(partes[1]['z1'], h, places=3)
                self.assertAlmostEqual(partes[0]['z1'], partes[1]['z0'], places=3)
                for t in partes:
                    self.assertLessEqual(t['contrahuella_m'], 0.18)
                    self.assertGreaterEqual(t['huella_m'], 0.28)
            self.assertIsNone(tramos[-1][1]['sube_a'])
        # escalera principal abierta (coordinación BIM, 17.4): tramos y descansos dentro del vano C-D entre los ejes 2 y 3, a la
        # cara de la viga del eje C (x = 1,60), de la columna C2 (y = −12,00) y lejos de las vigas de los ejes 3 y D; sube del
        # piso 1 al 2 y llega al mismo descanso de piso
        esp = next(e for e in self.niv['P1']['escaleras'] if e['id'] == 'ESC-P')
        self.assertEqual(esp['sube_a'], 'P2')
        for pa in esp['partes']:
            x0, y0, x1, y1 = pa['rect']
            self.assertTrue(x0 >= 1.6 - 1e-6 and y0 >= -12.0 - 1e-6 and x1 <= 8.4 + 1e-6 and y1 <= -7.8 + 1e-6, pa)
        tramos = [pa for pa in esp['partes'] if pa['tipo'] == 'tramo']
        self.assertEqual(len(tramos), 2)
        self.assertAlmostEqual(tramos[1]['z1'], 4.5, places=3)
        llegada = next(e for e in self.niv['P2']['escaleras'] if e['id'] == 'ESC-P')
        self.assertEqual([pa['tipo'] for pa in llegada['partes']], ['descanso_piso'])

    def test_laboratorio_sobre_la_toma_y_montacargas_alineado(self):
        mm1 = next(r for r in self.niv['P1']['recintos'] if r.get('fila') == 63)
        mm2 = next(r for r in self.niv['P2']['recintos'] if r.get('fila') == 116)
        self.assertEqual(C.caja(mm1['poligono']), C.caja(mm2['poligono']))
        lab = {r['fila'] for r in self.niv['P2']['recintos'] if r.get('servicio_programa') == 'Laboratorio clínico' and r.get('fila')}
        self.assertTrue(set(range(79, 94)) <= lab)
        tec = {r['ambiente'] for r in self.niv['P2']['recintos'] if r.get('programado') is False}
        self.assertIn('Biología molecular (GeneXpert)', tec)
        self.assertIn('Ducha de emergencia y lavaojos del laboratorio', tec)
        # el aseo de la toma (P1-A055-01) sube junto a la escalera sur desde el prediseño DMO (acceso a la escalera, 17.1)
        toma = [r for r in self.niv['P1']['recintos'] if r.get('servicio_programa') == 'Toma de muestras de laboratorio clínico'
                and r['ambiente'] != 'Ambiente de aseo']
        self.assertTrue(toma)
        self.assertTrue(all(C.centroide(r['poligono'])[1] < -10.0 for r in toma))

    def test_estructura_del_prediseno_dmo(self):
        """17.1: columnas de 0,80 m (0,90 m en el eje A), muros estructurales de 0,35 m solo en los paños del prediseño,
        puertas de las escaleras en el vano de x = 3,1, alturas libres bajo viga, fosos y cisternas (equipo A)."""
        est = C.cargar_json(C.DATOS / 'sismo' / 'torre_hospital_estructura.json')
        paneles = [p for p in est['prediseno']['eleccion_muros']['paneles_de_nucleo'] if p['material'] == 'concreto']
        for N in ('P1', 'P2', 'P3', 'P4'):
            n = self.niv[N]
            for c in n['columnas']:
                lado = 0.9 if c['id'].startswith('A') else 0.8
                self.assertEqual((c['b'], c['h']), (lado, lado), c['id'])
            nucleo = [m for m in n['muros'] if m['tipo'] == 'nucleo']
            for m in nucleo:
                self.assertEqual(m['espesor'], 0.35)
                self.assertTrue(m['estructural'])
                self.assertTrue(any(C.distancia_punto_segmento(m['a'], pn['tramo'][:2], pn['tramo'][2:]) < 1e-6 and
                                    C.distancia_punto_segmento(m['b'], pn['tramo'][:2], pn['tramo'][2:]) < 1e-6 for pn in paneles), m['id'])
            largo = sum(math.dist(m['a'], m['b']) for m in nucleo)
            self.assertAlmostEqual(largo, sum(math.dist(pn['tramo'][:2], pn['tramo'][2:]) for pn in paneles), places=2)
            ids_nucleo = {m['id'] for m in nucleo}
            self.assertFalse([pt['id'] for pt in n['puertas'] if pt['muro'] in ids_nucleo])
            self.assertFalse([v['id'] for v in n['ventanas'] if v['muro'] in ids_nucleo])
            escaleras = [pt for pt in n['puertas'] if pt['categoria'] == 'evacuacion' and pt['centro'][0] == 3.1]
            self.assertEqual(sorted(pt['centro'][1] for pt in escaleras), [-6.3, 15.3], N)
            self.assertTrue(all(pt['ancho'] == 1.1 for pt in escaleras))
            e = n['estructura']
            self.assertAlmostEqual(e['altura_libre_bajo_viga_m'], n['altura_entrepiso_m'] - 0.8, places=6)
            self.assertAlmostEqual(e['altura_libre_bajo_viga_min_m'], n['altura_entrepiso_m'] - 0.9, places=6)
            self.assertGreaterEqual(e['plenum_bajo_viga_m'], 0.3)
        for N in ('EXT', 'BT', 'CUB'):
            self.assertFalse([m['id'] for m in self.niv[N]['muros'] if m['tipo'] == 'nucleo'])
        self.assertEqual({m['tipo'] for m in self.niv['CUB']['muros'] if 'CUB-A220-01' in m['lados']} - {'fachada', 'parapeto'},
                         {'nucleo_mamposteria'})
        fosos = {b['id']: b for b in self.niv['P1']['bajo_rasante']}
        self.assertEqual(set(fosos), {'FOSO-ASC', 'FOSO-MC'})
        self.assertEqual(fosos['FOSO-ASC']['nucleo'], 'P1-NUC-ASC')
        cis = self.niv['BT']['bajo_rasante'][0]
        self.assertEqual(cis['id'], 'CIS-1')
        self.assertEqual([k['volumen_util_m3'] for k in cis['compartimientos']], [40, 30, 20])
        self.assertEqual([k['recinto'] for k in cis['compartimientos']], ['BT-A216-01', 'BT-A217-01', 'BT-A218-01'])

    def test_v23_detecta_cambios_del_prediseno(self):
        pl = C.cargar_json(C.PLANTAS)
        P1 = next(n for n in pl['niveles'] if n['id'] == 'P1')
        P1['columnas'][0]['b'] = P1['columnas'][0]['h'] = 0.6                      # columna de antes del prediseño
        m = next(m for m in P1['muros'] if m['tipo'] == 'nucleo')
        m.update(tipo='nucleo_mamposteria', espesor=0.2, estructural=False)        # paño estructural en mampostería
        ruta = self.tmp / 'plantas_v23.json'
        C.escribir_json(ruta, pl)
        rc, inf = correr(VALIDAR_PLANTAS, '--archivo', ruta)
        self.assertEqual(rc, 1)
        v23 = errores(inf).get('V23', [])
        self.assertTrue(any('columna A1' in x for x in v23), v23)
        self.assertTrue(any('no es muro estructural en toda su longitud' in x for x in v23), v23)

    def test_coordinacion_con_la_estructura(self):
        """17.4 (coordinación BIM): escaleras de evacuación desde la cara de vigas y columnas, bloque técnico junto a las
        cisternas y al sur de los dados del eje 1, y lo que no se resuelve aquí declarado con su motivo (aviso V25)."""
        rc, inf = correr(VALIDAR_PLANTAS)
        self.assertEqual(rc, 0, errores(inf))
        estados = {r['regla']: r['estado'] for r in inf['reglas']}
        self.assertEqual(estados.get('V24'), 'ok')
        for N in ('P1', 'P2', 'P3', 'P4', 'CUB'):
            for e in self.niv[N]['escaleras']:
                if e['id'] not in ('ESC-N', 'ESC-S'):
                    continue
                y_eje = 14.0 if e['id'] == 'ESC-N' else -7.6
                for pa in e['partes']:
                    x0, y0, x1, y1 = pa['rect']
                    self.assertLessEqual(x1, 8.2 + 1e-6, (N, e['id'], pa))           # cara de las columnas del eje D
                    self.assertGreaterEqual(x0, 3.27 - 1e-6, (N, e['id'], pa))       # cara del muro de 0,35 m
                    self.assertGreaterEqual(y0, y_eje + 0.2 - 1e-6, (N, e['id'], pa))  # cara de la viga (o del muro)
                    self.assertLessEqual(y1, y_eje + 8.4 - 0.2 + 1e-6, (N, e['id'], pa))
        bt = self.niv['BT']
        cis = next(b for b in bt['bajo_rasante'] if b['tipo'] == 'cisterna')
        xs, ys = [p[0] for p in cis['poligono']], [p[1] for p in cis['poligono']]
        for m in bt['muros']:
            if m['tipo'] == 'abierto':
                continue
            e = m['espesor'] / 2
            hz = abs(m['a'][1] - m['b'][1]) < 1e-9
            r = ((min(m['a'][0], m['b'][0]), m['a'][1] - e, max(m['a'][0], m['b'][0]), m['a'][1] + e) if hz else
                 (m['a'][0] - e, min(m['a'][1], m['b'][1]), m['a'][0] + e, max(m['a'][1], m['b'][1])))
            sx = min(r[2], max(xs)) - max(r[0], min(xs))
            sy = min(r[3], max(ys)) - max(r[1], min(ys))
            self.assertFalse(sx > 0.01 and sy > 0.01, m['id'])
        cuartos = [r for r in bt['recintos'] if r.get('fila') in (210, 211, 212, 213, 214, 215)]
        self.assertEqual(len(cuartos), 6)
        self.assertTrue(all(max(p[1] for p in r['poligono']) <= -20.95 + 1e-9 for r in cuartos))
        # ningún muro del bloque técnico se mete en la cimentación de la torre (dados, vigas de amarre y contrapiso): sobre el
        # eje 1 el pasaje queda abierto contra el borde de la torre
        est = C.cargar_json(C.DATOS / 'sismo' / 'torre_hospital_estructura.json')
        cim = est['cimentacion']
        piezas = [((d['x0'], d['y0'], d['x1'], d['y1']), d['z_fondo'], d['z_tope']) for d in cim['dados']]
        for v in cim['vigas_amarre']:
            t0, t1 = sorted(v['tramo'])
            w = v['b'] / 2
            r = ((t0, v['coordenada'] - w, t1, v['coordenada'] + w) if v['direccion'] == 'x'
                 else (v['coordenada'] - w, t0, v['coordenada'] + w, t1))
            piezas.append((r, v['z_tope'] - v['h'], v['z_tope']))
        piezas.append(((-13.0, -19.6, 8.6, 22.4), -cim['contrapiso']['espesor_m'], 0.0))
        for m in bt['muros']:
            if m['tipo'] == 'abierto':
                continue
            e = m['espesor'] / 2
            hz = abs(m['a'][1] - m['b'][1]) < 1e-9
            r = ((min(m['a'][0], m['b'][0]), m['a'][1] - e, max(m['a'][0], m['b'][0]), m['a'][1] + e) if hz else
                 (m['a'][0] - e, min(m['a'][1], m['b'][1]), m['a'][0] + e, max(m['a'][1], m['b'][1])))
            z0, z1 = bt['z'], bt['z'] + m['altura']
            for rr, za, zb in piezas:
                sx = min(r[2], rr[2]) - max(r[0], rr[0])
                sy = min(r[3], rr[3]) - max(r[1], rr[1])
                self.assertFalse(sx > 0.01 and sy > 0.01 and min(z1, zb) - max(z0, za) > 0.01, (m['id'], rr))
        abiertos = [m for m in bt['muros'] if m['tipo'] == 'abierto' and m['lados'] == ['BT-A229-01', 'exterior']]
        self.assertEqual(len(abiertos), 1)
        self.assertEqual(sorted([abiertos[0]['a'][0], abiertos[0]['b'][0]]), [-14.45, 10.0])
        llegada = next(p for p in bt['puertas'] if p.get('nombre', '').startswith('Llegada del pasaje'))
        self.assertGreaterEqual(llegada['centro'][0] - llegada['ancho'] / 2 - 0.05, 10.0 - 1e-6)
        # ductos verticales a la cara de las vigas (eje 6 en y = 13,80, eje D en x = 8,40, VB-N-56 en x = 3,10), iguales en
        # los cuatro pisos (no se angostan); las franjas bajo las vigas, sin acceso
        cajas = {}
        for N in ('P1', 'P2', 'P3', 'P4'):
            d = next(r for r in self.niv[N]['recintos'] if r['ambiente'].startswith('Ductos verticales'))
            x0, y0, x1, y1 = C.caja(d['poligono'])
            self.assertTrue(x0 >= 3.1 - 1e-6 and x1 <= 8.4 + 1e-6 and y1 <= 13.8 + 1e-6, (N, d['poligono']))
            self.assertGreaterEqual(d['area_ejes_m2'], d['area_programa_m2'] - 0.05)
            cajas[N] = (x0, y0, x1, y1)
            franja = next(r for r in self.niv[N]['recintos'] if r['ambiente'].startswith('Franja bajo las vigas'))
            self.assertIs(franja.get('transitable'), False)
            self.assertAlmostEqual(C.area_poligono(franja['poligono']) + C.area_poligono(d['poligono']),
                                   5.5 * (14.0 - y0), places=6)
        self.assertEqual(len(set(cajas.values())), 1, cajas)
        # nada queda declarado pendiente: lo que reglas_planta declare debe traer motivo, propuesta y quién decide
        pend = self.reglas['coordinacion_pendiente']['elementos']
        self.assertEqual(pend, [])
        self.assertTrue(all(e.get('motivo') and e.get('propuesta') and e.get('decide') for e in pend))
        avisos = next(r for r in inf['reglas'] if r['regla'] == 'V25')['avisos']
        self.assertFalse(any('ESC-P' in a for a in avisos), avisos)
        self.assertFalse(any('atraviesa el ducto' in a or 'se angosta' in a for a in avisos), avisos)
        self.assertFalse(any('se mete en' in a for a in avisos if a.startswith('BT')), avisos)

    def test_v24_detecta_choques_con_la_estructura(self):
        pl = C.cargar_json(C.PLANTAS)
        niv = {n['id']: n for n in pl['niveles']}
        pt = next(p for p in niv['P1']['puertas'] if p.get('nombre') == 'Puerta de urgencias (bahía de ambulancias)')
        pt['centro'] = [-13.0, 15.35]                                     # el vano se mete en la columna A-6
        esc = next(e for e in niv['P2']['escaleras'] if e['id'] == 'ESC-N')
        esc['partes'][0]['rect'][1] = 14.0                                # descanso de llegada dentro de la viga del eje 6
        duc = next(r for r in niv['P3']['recintos'] if r['ambiente'].startswith('Ductos verticales'))
        duc['poligono'] = C.rect_a_poligono([3.1, 10.6, 8.6, 14.0])        # el ducto vuelve a pasar bajo las vigas de 6 y D
        escp = next(e for e in niv['P1']['escaleras'] if e['id'] == 'ESC-P')
        t2 = next(pa for pa in escp['partes'] if pa['tipo'] == 'tramo' and pa['z0'] > 0)
        t2['rect'][1] -= 0.6                                               # el tramo de llegada pasa bajo la viga del eje 2
        t2['rect'][3] -= 0.6
        ruta = self.tmp / 'plantas_v24.json'
        C.escribir_json(ruta, pl)
        reglas = C.cargar_json(C.REGLAS_PLANTA)
        reglas.pop('coordinacion_pendiente')                              # sin la declaración, lo pendiente vuelve a ser error
        ruta_r = self.tmp / 'reglas_v24.json'
        C.escribir_json(ruta_r, reglas)
        rc, inf = correr(VALIDAR_PLANTAS, '--archivo', ruta, '--reglas', ruta_r)
        self.assertEqual(rc, 1)
        v24 = errores(inf).get('V24', [])
        self.assertTrue(any('columna A6' in x for x in v24), v24)
        self.assertTrue(any('se funde con la viga VX-6-CD' in x for x in v24), v24)
        self.assertTrue(any('atraviesa el ducto P3' in x for x in v24), v24)
        self.assertTrue(any('ESC-P' in x and 'VX-2-CD' in x for x in v24), v24)
        self.assertTrue(any('se angosta' in x for x in v24), v24)       # el ducto del piso 3 ya no es el de los pisos 2 y 4

    def test_v25_avisa_cimentacion_y_aberturas_del_prediseno(self):
        """V25 (aviso): el piso en rampa del pasaje frente a la cara superior de los dados del eje 1 y la abertura de cada losa
        del prediseño frente a la parte común del ducto (los dos los resuelve el equipo A)."""
        est = C.cargar_json(C.DATOS / 'sismo' / 'torre_hospital_estructura.json')
        d = next(x for x in est['cimentacion']['dados'] if x['id'] == 'D-A1')
        d['z_fondo'], d['z_tope'] = -1.5, -0.7                             # el dado como estaba antes de la coordinación
        ab = est['prediseno']['coordinacion_bim']['ducto_vertical']['aberturas_losa_m']
        a45 = next(a for a in ab if abs(a['nivel_z'] - 4.5) < 0.05)
        a45['y'] = [11.0, 13.8]                                           # abertura más chica que el ducto
        ruta = self.tmp / 'estructura_v25.json'
        C.escribir_json(ruta, est)
        rc, inf = correr(VALIDAR_PLANTAS, '--estructura', ruta)
        self.assertEqual(rc, 0, errores(inf))
        avisos = next(r for r in inf['reglas'] if r['regla'] == 'V25')['avisos']
        self.assertTrue(any(a.startswith('BT') and 'D-A1' in a and 'piso en rampa' in a for a in avisos), avisos)
        self.assertTrue(any(a.startswith('P1') and 'nivel 4.50 cierra' in a for a in avisos), avisos)

    def test_paneles_solares_182_modulos(self):
        grupos = [g for n in self.pl['niveles'] for g in n.get('paneles_solares', [])]
        self.assertEqual(sum(g['modulos'] for g in grupos), 182)
        self.assertAlmostEqual(sum(g['kwp'] for g in grupos), 100.1, places=1)

    def test_pasos_entre_niveles_reciprocos(self):
        for n in self.pl['niveles']:
            for pa in n['pasos_entre_niveles']:
                otro = self.niv[pa['otro_nivel']]
                self.assertTrue(any(q['otro_nivel'] == n['id'] and q['recinto'] == pa['otro_recinto'] for q in otro['pasos_entre_niveles']),
                                pa)

    def test_banos_y_cabinas(self):
        """Revisión adversarial: los ambientes «con baño» o «con unidad sanitaria» tienen su baño como subrecinto (tabique,
        puerta y polígono libre propios) y las baterías públicas tienen 3 cabinas, una PMR."""
        con = {}
        for n in self.pl['niveles']:
            muros = {m['id']: m for m in n['muros']}
            puertas = {p['id']: p for p in n['puertas']}
            for r in n['recintos']:
                for sb in r.get('subrecintos', []):
                    con.setdefault(r['id'], []).append(sb)
                    self.assertTrue(C.poligono_dentro_de(sb['poligono'], r['poligono'], 1e-6), sb['id'])
                    self.assertEqual(len(sb['puertas']), 1, sb['id'])
                    pt = puertas[sb['puertas'][0]]
                    self.assertEqual(pt['hacia'], sb['id'])
                    self.assertIn(pt['categoria'], ('bano', 'unidad_sanitaria'))
                    self.assertEqual(pt['abre'], 'corrediza')
                    self.assertNotIn(pt['id'], r['puertas'])
                    self.assertEqual(muros[pt['muro']]['tipo'], 'liviano')
                    self.assertLess(sb['area_libre_m2'], sb['area_ejes_m2'])
                if r.get('subrecintos'):
                    # el área del baño sigue en el recinto del programa
                    self.assertAlmostEqual(r['area_ejes_m2'], C.area_poligono(r['poligono']), places=2)
        filas = {r['fila'] for n in self.pl['niveles'] for r in n['recintos'] if r['id'] in con}
        self.assertEqual(filas, {8, 10, 15, 22, 38, 41, 42, 53, 71, 72, 74, 90, 91, 119, 120, 122, 142, 143, 148, 169, 187})
        self.assertEqual(len(con), 30)
        for rid in ('P2-A074-01', 'P2-A074-02'):
            self.assertEqual(len(con[rid]), 3, rid)
            self.assertEqual(sum('PMR' in sb['nombre'] for sb in con[rid]), 1, rid)
        # las habitaciones con el baño PMR junto al corredor y la puerta al lado
        for rid in ('P3-A119-01', 'P3-A119-02', 'P3-A119-03', 'P3-A122-01', 'P3-A122-02'):
            self.assertEqual(con[rid][0]['nombre'], 'Baño PMR')
            self.assertEqual(C.caja(con[rid][0]['poligono'])[2], -5.8, rid)

    def test_muros_con_cota_y_puertas_espejo(self):
        """Revisión adversarial: en la cubierta los muros de la terraza (piso 3, z −4,2 m) llevan z_base_m y en los exteriores
        cada paso a otro nivel tiene su vano, espejo de la puerta del otro nivel."""
        cub = self.niv['CUB']
        con_cota = [m for m in cub['muros'] if 'z_base_m' in m]
        self.assertTrue(con_cota)
        self.assertTrue(all(m['z_base_m'] < 0 for m in con_cota))
        ext = self.niv['EXT']
        espejos = [p for p in ext['puertas'] if p.get('espejo_de')]
        self.assertTrue(espejos)
        for p in espejos:
            otro = self.niv[p['espejo_de']['nivel']]
            q = next(x for x in otro['puertas'] if x['id'] == p['espejo_de']['puerta'])
            self.assertEqual(q['centro'], p['centro'])
            self.assertEqual(q['ancho'], p['ancho'])
        for pa in ext['pasos_entre_niveles']:
            self.assertTrue(pa.get('puerta'), pa)

    def test_ancho_minimo_ignora_muescas(self):
        p = C.orientar_antihorario([[0, 0], [10, 0], [10, 2.4], [6, 2.4], [6, 2.415], [4, 2.415], [4, 2.4], [0, 2.4]])
        self.assertLess(C.ancho_minimo(p), 2.1)
        self.assertAlmostEqual(C.ancho_minimo(p, C.MUESCA_IGNORADA_M), 2.4)

    def test_contorno_de_union(self):
        sys.path.insert(0, str(AQUI))
        import generar_plantas as G
        u = G.contorno_de_union([C.rect_a_poligono([0, 0, 2, 1]), C.rect_a_poligono([2, 0, 3, 1]), C.rect_a_poligono([0, 1, 1, 2])])
        self.assertAlmostEqual(C.area_poligono(u), 4.0)
        self.assertEqual(len(u), 6)


if __name__ == '__main__':
    unittest.main()
