# Compone data/edificios/torre_hospital.json desde el programa médico-arquitectónico (data/proyectos/torre_hospital/programa.json):
# las alas del antiguo Centro Vida con "estado": "demoler" y la torre de servicios de primer nivel con "estado": "nuevo".
# Uso: python3 scripts/modelos/componer_torre.py [salida.json]
import json, sys
import os
R = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
b = json.load(open(f'{R}/data/edificios/bienestar_anciano.json'))
prog = json.load(open(f'{R}/data/proyectos/torre_hospital/programa.json'))
OUT = sys.argv[1] if len(sys.argv) > 1 else f'{R}/data/edificios/torre_hospital.json'
LAD = {'ladrillo': {}}
ter = '#b4643f'   # terracota del ladrillo (continúa el ladrillo rojo de las alas de la Shell que se demuelen)
blanco = '#eeede8'
vol = []
# --- lo que se demuele
for v in b['volumenes']:
    v = dict(v); v['estado'] = 'demoler'; vol.append(v)
fach_ladrillo = lambda extra: {**{'material': 'ladrillo_visto', 'color': ter, **LAD,
    'ventanas': {'tipo': 'franja', 'alto': 2.0, 'antepecho': 1.0, 'lados': ['O', 'N', 'S', 'E']},
    'losas_expresadas': {'voladizo': 0.6, 'espesor': 0.35, 'color': blanco, 'cubierta': True},
    'parasoles': [{'tipo': 'vertical', 'profundidad': 0.6, 'separacion': 0.9, 'color': '#a3532f', 'lados': ['O']},
                  {'tipo': 'horizontal', 'profundidad': 0.9, 'separacion': 0.7, 'color': '#d8d7d1', 'lados': ['N', 'S']}],
    'coronacion': {'material': 'panel_compuesto', 'color': '#e6e5e0'}}, **extra}
techo_plano = {'tipo': 'plano', 'parapeto': 1.2, 'material': 'concreto', 'color': '#e9e8e3'}
# --- obra nueva (marco de bienestar_anciano.json: x este, y norte)
vol += [
    {'id': 'torre_norte', 'estado': 'nuevo', 'nombre': 'Torre, pisos 1 a 3, cuerpo norte (urgencias, consulta, hospitalización y partos)',
     'centro': [-2.2, 7.4], 'largo': 30.0, 'ancho': 21.6, 'rumbo_eje': 0, 'base': 0, 'altura_alero': 12.9, 'pisos': 3, 'techo': techo_plano,
     # puerta de urgencias frente a la bahía (fachada occidental, y = 15) y puerta lateral al patio norte
     'fachada': fach_ladrillo({'puertas': [{'lado': 'O', 'pos': (22.4 - 15.0) / 30.0, 'ancho': 2.6, 'alto': 2.8}, {'lado': 'N', 'pos': 0.25, 'ancho': 1.8, 'alto': 2.4}]})},
    {'id': 'torre_sur', 'estado': 'nuevo', 'nombre': 'Torre, pisos 1 a 3, cuerpo sur (vestíbulo, toma de muestras, laboratorio y esterilización)',
     'centro': [-2.2, -13.6], 'largo': 12.0, 'ancho': 21.6, 'rumbo_eje': 0, 'base': 0, 'altura_alero': 12.9, 'pisos': 3, 'techo': techo_plano,
     # puerta principal en la fachada occidental, en el vestíbulo (y ≈ -13, programa.json) y la de servicio al pasaje del sur
     'fachada': fach_ladrillo({'puertas': [{'lado': 'O', 'pos': (-7.6 + 13.0) / 12.0, 'ancho': 3.2, 'alto': 3.0}, {'lado': 'S', 'pos': 0.5, 'ancho': 1.8, 'alto': 2.4}]})},
    {'id': 'torre_piso4', 'estado': 'nuevo', 'nombre': 'Piso 4: terapias, telesalud, odontología y sala de crisis (retrocede 12 m en el sur)',
     'centro': [-2.2, 7.4], 'largo': 30.0, 'ancho': 21.6, 'rumbo_eje': 0, 'base': 12.9, 'altura_alero': 17.1, 'pisos': 1, 'techo': techo_plano,
     'fachada': {'material': 'panel_compuesto', 'color': '#e4e3de', 'panel': {'ancho': 1.2, 'alto': 0.7},
                 'lados_material': {'N': 'muro_cortina', 'S': 'muro_cortina'},
                 'muro_cortina': {'modulo': 1.2, 'enjuta': 0.9, 'color_vidrio': '#2c4452', 'color_perfil': '#c9cdd0', 'color_enjuta': '#56626a'},
                 'ventanas': {'tipo': 'franja', 'alto': 2.2, 'antepecho': 0.9, 'lados': ['O', 'E']},
                 'parasoles': [{'tipo': 'vertical', 'profundidad': 0.6, 'separacion': 1.2, 'color': '#a3532f', 'lados': ['O']}],
                 'losas_expresadas': {'voladizo': 0.6, 'espesor': 0.35, 'color': blanco, 'cubierta': True},
                 'coronacion': {'material': 'panel_compuesto', 'color': '#e6e5e0'}}},
    # núcleos de circulación vertical en concreto a la vista (hito técnico, como el proyecto tipo del DNP)
    {'id': 'nucleo_escalera_norte', 'estado': 'nuevo', 'nombre': 'Escalera protegida norte (2,40 m) hasta la cubierta',
     'centro': [6.05, 18.2], 'largo': 8.4, 'ancho': 5.9, 'rumbo_eje': 0, 'base': 0, 'altura_alero': 20.4, 'pisos': 5,
     'techo': {'tipo': 'plano', 'parapeto': 0.5, 'material': 'concreto', 'color': '#d6d5d0'}, 'fachada': {'material': 'concreto_visto', 'color': '#bdbbb5', 'ventanas': {'tipo': 'ventana', 'ancho': 0.9, 'alto': 2.6, 'antepecho': 0.8, 'separacion': 4.2, 'lados': ['E']}}},
    {'id': 'nucleo_escalera_sur', 'estado': 'nuevo', 'nombre': 'Escalera protegida sur (2,40 m) hasta la cubierta',
     'centro': [6.05, -3.4], 'largo': 8.4, 'ancho': 5.9, 'rumbo_eje': 0, 'base': 0, 'altura_alero': 20.4, 'pisos': 5,
     'techo': {'tipo': 'plano', 'parapeto': 0.5, 'material': 'concreto', 'color': '#d6d5d0'}, 'fachada': {'material': 'concreto_visto', 'color': '#bdbbb5', 'ventanas': {'tipo': 'ventana', 'ancho': 0.9, 'alto': 2.6, 'antepecho': 0.8, 'separacion': 4.2, 'lados': ['E']}}},
    {'id': 'nucleo_ascensores', 'estado': 'nuevo', 'nombre': 'Dos ascensores camilleros y montacargas (sobrerrecorrido sin cuarto de máquinas)',
     'centro': [4.8, 4.4], 'largo': 5.6, 'ancho': 3.4, 'rumbo_eje': 0, 'base': 0, 'altura_alero': 18.9, 'pisos': 5,
     'techo': {'tipo': 'plano', 'parapeto': 0.4, 'material': 'concreto', 'color': '#d6d5d0'}, 'fachada': {'material': 'concreto_visto', 'color': '#b7b5af'}},
    {'id': 'bloque_tecnico', 'estado': 'nuevo', 'nombre': 'Bloque técnico: subestación, planta eléctrica, tableros, gases medicinales, bombas y depósito de cadáveres',
     'centro': [-3.8, -22.8], 'largo': 31.4, 'ancho': 4.0, 'rumbo_eje': 90, 'base': 0, 'altura_alero': 4.0, 'pisos': 1,
     'techo': {'tipo': 'plano', 'parapeto': 0.6, 'material': 'concreto', 'color': '#e2e1dc'},
     'fachada': {'material': 'concreto_visto', 'color': '#c4c2bc', 'ventanas': {'tipo': 'celosia', 'ancho': 1.6, 'alto': 0.8, 'antepecho': 2.4, 'separacion': 4.0, 'lados': ['S', 'N']},
                 'puertas': [{'lado': 'S', 'pos': 0.2, 'ancho': 2.4, 'alto': 2.6}, {'lado': 'S', 'pos': 0.5, 'ancho': 1.2, 'alto': 2.2}, {'lado': 'S', 'pos': 0.8, 'ancho': 1.2, 'alto': 2.2}]}},
    {'id': 'residuos_central', 'estado': 'nuevo', 'nombre': 'Unidad de almacenamiento central de residuos',
     'centro': [-22.25, -26.0], 'largo': 4.5, 'ancho': 4.0, 'rumbo_eje': 90, 'base': 0, 'altura_alero': 3.0, 'pisos': 1,
     'techo': {'tipo': 'plano', 'parapeto': 0.3, 'material': 'concreto', 'color': '#e2e1dc'},
     'fachada': {'material': 'pañete_pintado', 'color': '#e8e6df', 'ventanas': {'tipo': 'celosia', 'ancho': 1.2, 'alto': 0.5, 'antepecho': 2.2, 'separacion': 2.5, 'lados': ['largo']},
                 'puertas': [{'lado': 'O', 'pos': 0.5, 'ancho': 2.0, 'alto': 2.4}]}},
]
el = []
# --- lo que existe y se conserva o se demuele
for e in b['elementos']:
    e = dict(e)
    if e['tipo'] in ('zona_verde', 'cubierta_ligera'): e['estado'] = 'demoler'
    if e['tipo'] == 'arbol' and e['centro'] in ([-22.5, 5.5], [-11.0, 22.5]): e['estado'] = 'demoler'   # palma (se trasplanta) y árbol sobre la huella
    el.append(e)
# --- exteriores nuevos (polígonos de programa.json → implantacion.patios_y_exteriores)
pat = {p['id']: p for p in prog['implantacion']['patios_y_exteriores']}
rect = lambda c, L, A: [[c[0] - A / 2, c[1] - L / 2], [c[0] + A / 2, c[1] - L / 2], [c[0] + A / 2, c[1] + L / 2], [c[0] - A / 2, c[1] + L / 2]]
el += [
    {'tipo': 'parqueadero', 'estado': 'nuevo', 'nombre': 'Patio de urgencias y retorno de ambulancias', 'poligono': pat['patio_urgencias']['poligono']},
    # salida de las ambulancias: rodean por el norte el árbol del portón (-22; 25) usando ≈ 2 m del patio del hospital (programa.json, accesos)
    {'tipo': 'parqueadero', 'estado': 'nuevo', 'nombre': 'Salida de ambulancias por el norte del árbol del portón',
     'poligono': [[-19.0, 24.0], [-16.5, 24.0], [-17.4, 27.6], [-20.0, 29.3], [-25.0, 29.3], [-28.4, 26.6], [-28.0, 24.0], [-25.6, 24.0], [-25.6, 26.0], [-24.0, 27.1], [-21.0, 27.1], [-19.6, 26.0]]},
    {'tipo': 'zona_verde', 'estado': 'nuevo', 'nombre': 'Isla del retorno con la palma trasplantada', 'poligono': rect([-22.25, 13.0], 12.0, 3.5)},
    {'tipo': 'plaza', 'estado': 'nuevo', 'nombre': 'Plaza de los mangos (acceso principal con rampa y escalera)', 'poligono': pat['plaza_principal']['poligono']},
    {'tipo': 'patio', 'estado': 'nuevo', 'nombre': 'Patio norte de luz y ventilación', 'poligono': pat['patio_norte']['poligono']},
    {'tipo': 'anden', 'estado': 'nuevo', 'nombre': 'Franja de servicio entre la torre y el bloque central', 'poligono': pat['patio_oriente']['poligono']},
    {'tipo': 'parqueadero', 'estado': 'nuevo', 'nombre': 'Vía de servicio', 'poligono': pat['via_servicio']['poligono']},
    {'tipo': 'patio', 'estado': 'nuevo', 'nombre': 'Patio de maniobra sobre las cisternas', 'poligono': pat['patio_servicio']['poligono']},
    {'tipo': 'arbol', 'estado': 'nuevo', 'centro': [-22.25, 13.0], 'altura': 7, 'copa': 4},
    {'tipo': 'arbol', 'estado': 'nuevo', 'centro': [-29.0, 6.0], 'altura': 8, 'copa': 6},
    {'tipo': 'arbol', 'estado': 'nuevo', 'centro': [-28.5, -1.5], 'altura': 7, 'copa': 5},
    {'tipo': 'bahia_ambulancias', 'estado': 'nuevo', 'centro': [-16.6, 15.0], 'largo': 13.2, 'ancho': 7.2, 'rumbo_eje': 0, 'cubierta': False},
    {'tipo': 'marquesina_acceso', 'estado': 'nuevo', 'centro': [-15.6, -13.0], 'largo': 10.0, 'ancho': 5.2, 'rumbo_eje': 0, 'altura': 3.9},
    {'tipo': 'puente', 'estado': 'nuevo', 'nombre': 'Galería cerrada de conexión con el hospital actual (3 m, camas y camillas)',
     'desde': [8.6, 4.4], 'hasta': [13.9, 4.4], 'altura': 0.0, 'ancho': 3.0, 'alto': 3.0, 'estructura': 'viga'},
    {'tipo': 'cubierta_ligera', 'estado': 'nuevo', 'nombre': 'Pasaje de servicio cubierto', 'centro': [-5.45, -20.2], 'largo': 28.1, 'ancho': 1.2, 'rumbo_eje': 90, 'altura': 2.9, 'material': 'termoacustica'},
    {'tipo': 'jardinera', 'estado': 'nuevo', 'centro': [-17.5, -4.5], 'largo': 5.0, 'ancho': 1.4, 'rumbo_eje': 0},
    {'tipo': 'jardinera', 'estado': 'nuevo', 'centro': [-26.0, -11.5], 'largo': 4.0, 'ancho': 1.4, 'rumbo_eje': 90},
    {'tipo': 'banca', 'estado': 'nuevo', 'centros': [[-19.5, -10.5], [-23.0, -12.5], [-26.5, -4.0]], 'rumbo': 90, 'respaldo': True},
    {'tipo': 'luminaria', 'estado': 'nuevo', 'centros': [[-18.5, -1.5], [-25.0, -2.0], [-19.0, -13.0], [-27.0, 18.0], [-27.0, 6.0]], 'rumbo': 90},
    {'tipo': 'letrero_institucional', 'estado': 'nuevo', 'texto': 'E.S.E. HOSPITAL HÉCTOR ABAD GÓMEZ', 'volumen': 'torre_piso4', 'lado': 'O', 'altura': 0.9},
    {'tipo': 'letrero_institucional', 'estado': 'nuevo', 'texto': 'URGENCIAS', 'centro': [-20.35, 15.0], 'rumbo': 270, 'base': 5.55, 'altura': 0.75, 'color': '#d62828'},
    # cubierta técnica del piso 4 (17,1 m): condensadoras tras pantalla, tanques de respaldo, manejadora de aire
    {'tipo': 'equipo_cubierta', 'estado': 'nuevo', 'equipo': 'pantalla', 'centro': [-5.5, 17.6], 'largo': 9.0, 'ancho': 7.0, 'rumbo_eje': 90, 'altura': 2.4},
    {'tipo': 'equipo_cubierta', 'estado': 'nuevo', 'equipo': 'chiller', 'centro': [-5.5, 17.6], 'largo': 5.5, 'ancho': 2.2, 'rumbo_eje': 90},
    {'tipo': 'equipo_cubierta', 'estado': 'nuevo', 'equipo': 'tanque', 'centro': [-11.0, 19.5], 'diametro': 2.2, 'altura': 2.0},
    {'tipo': 'equipo_cubierta', 'estado': 'nuevo', 'equipo': 'tanque', 'centro': [-11.0, 16.2], 'diametro': 2.2, 'altura': 2.0},
    {'tipo': 'equipo_cubierta', 'estado': 'nuevo', 'equipo': 'uma', 'centro': [0.5, 18.5], 'largo': 3.2, 'ancho': 1.6, 'rumbo_eje': 0},
]
ad = {
    'kwp_plan': 100,
    # baterías LFP de 400 kWh / 150 kW en el cuarto de baterías del bloque técnico (presupuesto 19.03): no se dibuja contenedor
    'bess': {'kwh': 400, 'kw': 150, 'tipo': 'cuarto', 'interior': True, 'ubicacion': 'cuarto de baterías del bloque técnico'},
    'fv': [
        {'tipo': 'pergola', 'volumen': 'torre_piso4', 'centro': [-5.0, 4.0], 'largo': 20.0, 'ancho': 15.0, 'rumbo_eje': 0, 'altura': 3.6, 'filas': 12, 'columnas': 8},
        {'volumen': 'torre_sur', 'faldon': 'plano', 'filas': 7, 'columnas': 8, 'inclinacion': 10, 'azimut': 180, 'orientacion_modulo': 'horizontal'},
        {'tipo': 'marquesina', 'centro': [-16.6, 15.0], 'largo': 13.2, 'ancho': 7.2, 'rumbo_eje': 0, 'altura': 5.3, 'filas': 6, 'columnas': 5},
    ],
    'inversores': {'n': 2, 'kw': 50, 'volumen': 'bloque_tecnico', 'lado': 'N', 'pos': 0.35},
    'domotica': ['medidor bidireccional por frontera (torre y edificio actual)', 'gateway IoT enlazado al CCED de la alcaldía', 'gestión de la planta eléctrica y del tablero de transferencia con prioridades (urgencias, partos, cadena de frío, laboratorio)', 'control de aires, extracción y presiones de salas (negativa en aislamiento, positiva en partos y esterilización)', 'monitoreo de neveras de vacunas y del laboratorio con alarmas', 'llamado de enfermería, control de acceso y CCTV integrados'],
    'obras_civiles': ['demolición de los pabellones del antiguo Centro Vida, el kiosco y los corredores; retiro de la teja de fibrocemento por personal autorizado (posible asbesto, Ley 1968 de 2019)', 'cimentación y estructura de pórticos de concreto para grupo de uso IV (NSR-10), con protección de raíces del mango grande', 'cisternas enterradas para 72 h de agua y tanque de aguas lluvias de ~20 m³', 'subestación, planta eléctrica y transferencia en el bloque técnico; red de gases medicinales', 'galería cerrada de 3 m hasta el hospital actual con junta y muro cortafuego'],
    'notas': ('Torre de servicios de primer nivel de la E.S.E. Hospital Héctor Abad Gómez sobre el sitio del antiguo Centro Vida (reubicado): '
              'programa, áreas y niveles de data/proyectos/torre_hospital/programa.json. Paneles: pérgola sobre la cubierta del piso 4 (los equipos quedan debajo), '
              'terraza del cuerpo sur y marquesina de la bahía de ambulancias. El nodo hospital del plan tiene 100 kWp (límite para acreditar excedentes 1:1): '
              'la solar de 100 kWp (presupuesto 19.01 y 19.02) y las baterías de 400 kWh del nodo van en la torre (proyecto P7); el edificio actual ya no lleva paneles ni contenedor.'),
}
spec = {
    'id': 'torre_hospital', 'nombre': 'Torre de servicios de primer nivel — E.S.E. Hospital Héctor Abad Gómez (sitio del antiguo Centro Vida)',
    'nodo_microrred': 'hospital', 'direccion': b.get('direccion'), 'lat': b['lat'], 'lon': b['lon'],
    'ubicacion': {'confianza': 'media', 'metodo': 'Sitio del antiguo Centro Vida, alas occidentales del predio del hospital (levantamiento de bienestar_anciano.json y verificación); el usuario aclaró que el Centro Vida fue reubicado y que la idea es demoler estas construcciones para la torre.'},
    'fuentes': b.get('fuentes', []),
    'volumenes': vol, 'elementos': el, 'adecuaciones': ad,
    'incertidumbres': ['El terreno tiene desniveles de hasta 2,8 m hacia la vía del occidente; el modelo lo dibuja plano (los niveles están en programa.json).',
                       'La torre es un anteproyecto volumétrico a partir del programa médico-arquitectónico: los planos definitivos salen de los estudios y diseños (proyecto 1 de los que se deben articular).'] + b.get('incertidumbres', [])[:4],
}
json.dump(spec, open(OUT, 'w'), ensure_ascii=False, indent=1)
print('ok', len(vol), 'volúmenes', len(el), 'elementos')
