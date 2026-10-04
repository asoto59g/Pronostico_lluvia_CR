import streamlit as st
import streamlit.components.v1 as components
import json
import urllib.request
from datetime import datetime
import numpy as np
import pandas as pd
import folium
import geopandas as gpd
from shapely.geometry import Point
from shapely.prepared import prep
import concurrent.futures
import base64
import os

# ==========================================
# CONFIGURACIÓN DE STREAMLIT Y ESTILOS VISUALES
# ==========================================
st.set_page_config(page_title="Pronóstico Lluvia CR", layout="wide")

# Función para convertir la imagen local a base64
@st.cache_data
def get_base64_of_bin_file(bin_file):
    if os.path.exists(bin_file):
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()
    return ""

# Cargar la imagen proporcionada
img_base64 = get_base64_of_bin_file("Panorama de selva tropical lluviosa.png")

# Inyección de CSS dinámico usando f-string (se usan dobles llaves {{ }} para escapar el CSS)
css_bg = f"""
<style>
    /* Imagen de fondo inyectada en base64, escalable para PC y teléfono */
    .stApp {{
        background-image: url("data:image/png;base64,{img_base64}");
        background-repeat: no-repeat;
        background-position: center center;
        background-attachment: fixed;
        background-size: cover;
        -webkit-background-size: cover;
        -moz-background-size: cover;
        -o-background-size: cover;
    }}
    
    /* Oscurecer un poco el fondo para que el texto resalte sobre la selva */
    .stApp::before {{
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(10, 20, 15, 0.35); /* Tono ligeramente verdoso/oscuro */
        z-index: -1;
    }}

    /* Estilo general de textos para alto contraste */
    h1, h2, h3, h4, p, span, label {{
        color: #ffffff !important;
        text-shadow: 0px 2px 5px rgba(0,0,0,0.9);
    }}

    /* Botones transparentes con bordes neón */
    .stButton > button {{
        background: rgba(10, 30, 20, 0.4) !important;
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(0, 255, 150, 0.5) !important;
        border-radius: 20px !important;
        color: #ffffff !important;
        box-shadow: 0 4px 15px rgba(0, 255, 150, 0.15) !important;
        transition: all 0.3s ease !important;
        font-weight: bold !important;
    }}
    
    .stButton > button:hover {{
        background: rgba(0, 255, 150, 0.2) !important;
        border: 1px solid rgba(0, 255, 150, 1) !important;
        box-shadow: 0 4px 20px rgba(0, 255, 150, 0.4) !important;
        transform: translateY(-2px);
    }}

    /* Cajas de input numérico traslúcidas */
    .stNumberInput input {{
        background-color: rgba(10, 30, 20, 0.5) !important;
        color: #00ffaa !important;
        border: 1px solid rgba(0, 255, 150, 0.3) !important;
        border-radius: 12px !important;
        font-weight: bold;
    }}
    
    .stNumberInput input:focus {{
        border: 1px solid rgba(0, 255, 150, 1) !important;
        box-shadow: 0 0 10px rgba(0, 255, 150, 0.3) !important;
    }}

    /* Ocultar barra superior y pie de página de Streamlit */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{background: transparent !important;}}
    
    /* Contenedor principal de Streamlit convertido en un panel cristalino */
    .block-container {{
        background: rgba(15, 25, 20, 0.45);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 25px;
        padding: 3rem 2rem !important;
        margin-top: 2rem;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.6);
    }}
</style>
"""
st.markdown(css_bg, unsafe_allow_html=True)

# Título y Subtítulo adaptados al tema oscuro
st.title("🌧️️ Pronóstico Lluvia (ECMWF & GFS) Costa Rica")
st.markdown("<h4 style='color: #a0efc8; font-size: 15px; font-weight: 400;'>⚠️ <i>Nota: El pronóstico máximo es de 15 días. El cálculo espacial requiere un poco de paciencia.</i></h4>", unsafe_allow_html=True)
st.write("")

# Controles de Interfaz
col1, col2, col3, col4 = st.columns([1.5, 1, 1, 2])

with col1:
    dias_input = st.number_input("Días a acumular:", min_value=1, max_value=15, value=15, step=1)

with col2:
    st.write("") 
    st.write("")
    btn_ejecutar = st.button("🚀 Procesar Mapa", use_container_width=True)

with col3:
    st.write("")
    st.write("")
    if st.button("🔄 Reiniciar", use_container_width=True):
        st.rerun()

st.markdown("---")

# ==========================================
# LÓGICA PRINCIPAL (INTACTA)
# ==========================================
if btn_ejecutar:
    with st.spinner(f"Consultando la API para {dias_input} días y calculando la interpolación IDW..."):
        DIAS = dias_input
        FECHA_EJECUCION = datetime.now().strftime("%d/%m/%Y")

        try:
            df_est = pd.read_csv('EstIMN.csv', sep=';', encoding='latin1')
            gdf_cr = gpd.read_file('costa_rica.geojson')
            geom_cr = gdf_cr.geometry.union_all()
            geom_cr_prep = prep(geom_cr)
        except FileNotFoundError as e:
            st.error(f"Error cargando archivos base: {e}. Asegúrese de tener 'EstIMN.csv' y 'costa_rica.geojson' en el directorio.")
            st.stop()

        def obtener_pronostico(row):
            lat, lon = row['Latitud'], row['Longitud']
            try:
                url = (
                    f"https://api.open-meteo.com/v1/forecast?"
                    f"latitude={lat}&longitude={lon}"
                    f"&daily=precipitation_sum&models=ecmwf_ifs025,gfs_seamless"
                    f"&forecast_days={DIAS}&timezone=America%2FCosta_Rica"
                )
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    
                precip_ecmwf = sum([p for p in data['daily'].get('precipitation_sum_ecmwf_ifs025', []) if p is not None])
                precip_gfs = sum([p for p in data['daily'].get('precipitation_sum_gfs_seamless', []) if p is not None])
                
                return round(precip_ecmwf, 1), round(precip_gfs, 1)
            except Exception:
                return 0.0, 0.0

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            resultados = list(executor.map(obtener_pronostico, [row for _, row in df_est.iterrows()]))

        df_est['Lluvia_ECMWF'] = [r[0] for r in resultados]
        df_est['Lluvia_GFS'] = [r[1] for r in resultados]

        df_est.to_csv('EstIMN_Pronostico_Modelos.csv', index=False, sep=';', encoding='utf-8-sig')

        minx, miny, maxx, maxy = gdf_cr.total_bounds
        resolution = 0.02  

        grid_x = np.arange(minx - 0.1, maxx + 0.1, resolution)
        grid_y = np.arange(miny - 0.1, maxy + 0.1, resolution)
        gx, gy = np.meshgrid(grid_x, grid_y)

        pts_obs = df_est[['Longitud', 'Latitud']].values
        grid_pts = np.vstack([gx.ravel(), gy.ravel()]).T

        dist_matrix = np.hypot(grid_pts[:, 0:1] - pts_obs[:, 0].T, grid_pts[:, 1:2] - pts_obs[:, 1].T)
        dist_matrix[dist_matrix == 0] = 1e-10
        weights = 1.0 / (dist_matrix ** 2)
        sum_weights = np.sum(weights, axis=1)

        vals_ecmwf = df_est['Lluvia_ECMWF'].values
        idw_ecmwf = np.sum(weights * vals_ecmwf, axis=1) / sum_weights
        grid_ecmwf = idw_ecmwf.reshape(gx.shape)

        vals_gfs = df_est['Lluvia_GFS'].values
        idw_gfs = np.sum(weights * vals_gfs, axis=1) / sum_weights
        grid_gfs = idw_gfs.reshape(gx.shape)

        mask = np.zeros(gx.shape, dtype=bool)
        for i in range(gy.shape[0]):
            for j in range(gx.shape[1]):
                pt = Point(gx[i, j], gy[i, j])
                if geom_cr_prep.contains(pt):
                    mask[i, j] = True

        grid_ecmwf_masked = np.where(mask, grid_ecmwf, np.nan)
        grid_gfs_masked = np.where(mask, grid_gfs, np.nan)

        RANGOS_COLOR = [
            (0, 0, "#e5d5bb", "0"),
            (0, 1, "#ffffcf", "0 - 1"),
            (1, 10, "#dbffff", "1 - 10"),
            (10, 25, "#91dcfc", "10 - 25"),
            (25, 50, "#72b8fd", "25 - 50"),
            (50, 75, "#4f8cff", "50 - 75"),
            (75, 100, "#4d4cff", "75 - 100"),
            (100, 125, "#484ddc", "100 - 125"),
            (125, 150, "#4e4d91", "125 - 150"),
            (150, 175, "#ab4fa2", "150 - 175"),
            (175, 200, "#ac4dc5", "175 - 200"),
            (200, 225, "#ca4df1", "200 - 225"),
            (225, 250, "#d764a9", "225 - 250"),
            (250, 275, "#9e54a1", "250 - 275"),
            (275, 400, "#ff7f00", "275 - 400"),
            (400, 600, "#e41a1c", "400 - 600"),
            (600, 9999, "#000000", "> 600")
        ]

        def raster_to_rgba(grid_masked):
            rgba_data = np.zeros((grid_masked.shape[0], grid_masked.shape[1], 4), dtype=np.uint8)
            for i in range(grid_masked.shape[0]):
                for j in range(grid_masked.shape[1]):
                    val = grid_masked[i, j]
                    if np.isnan(val):
                        rgba_data[i, j] = (0, 0, 0, 0)
                    else:
                        for vmin, vmax, hex_c, _ in RANGOS_COLOR:
                            if vmin <= val <= vmax:
                                h = hex_c.lstrip('#')
                                rgb = tuple(int(h[k:k+2], 16) for k in (0, 2, 4))
                                rgba_data[i, j] = (rgb[0], rgb[1], rgb[2], 255)
                                break
            return np.flipud(rgba_data)

        rgba_ecmwf = raster_to_rgba(grid_ecmwf_masked)
        rgba_gfs = raster_to_rgba(grid_gfs_masked)

        js_grid_data = []
        for i in range(0, grid_y.shape[0], 2):
            for j in range(0, grid_x.shape[0], 2):
                if not np.isnan(grid_ecmwf_masked[i, j]):
                    js_grid_data.append([
                        round(float(grid_y[i]), 3),
                        round(float(grid_x[j]), 3),
                        round(float(grid_ecmwf_masked[i, j]), 1),
                        round(float(grid_gfs_masked[i, j]), 1)
                    ])

        m = folium.Map(location=[9.7489, -83.7534], zoom_start=8, tiles=None)

        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri World Imagery', name='Esri Satellite'
        ).add_to(m)

        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri World Street Map', name='Esri Calles'
        ).add_to(m)

        folium.GeoJson(
            'costa_rica.geojson',
            name="Frontera Costa Rica",
            style_function=lambda x: {
                'fillColor': 'transparent',
                'color': '#2b5c8f',
                'weight': 1.5,
                'fillOpacity': 0
            }
        ).add_to(m)

        bounds_map = [[grid_y.min(), grid_x.min()], [grid_y.max(), grid_x.max()]]

        folium.raster_layers.ImageOverlay(
            image=rgba_ecmwf, bounds=bounds_map, opacity=0.8,
            name="Modelo ECMWF", show=True
        ).add_to(m)

        folium.raster_layers.ImageOverlay(
            image=rgba_gfs, bounds=bounds_map, opacity=0.8,
            name="Modelo GFS", show=False
        ).add_to(m)

        folium.LayerControl(position='topright', collapsed=False).add_to(m)

        html_panel = f"""
        <div id="panel-titulo" style="position: fixed; top: 80px; left: 10px; width: 320px; z-index:9999; 
                    background-color: white; padding: 10px 12px; border-radius: 8px; 
                    box-shadow: 0 0 10px rgba(0,0,0,0.3); font-family: Arial, sans-serif; transition: all 0.3s ease;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <h3 style="margin:0; color:#1a252f; font-size:13px; font-weight:bold;">
                    Pronóstico Lluvia ({DIAS} días)
                </h3>
                <button id="btn-toggle-titulo" onclick="toggleTitulo()" 
                        style="background: #e74c3c; color: white; border: none; border-radius: 4px; 
                               padding: 2px 6px; font-size: 11px; cursor: pointer; font-weight: bold;">
                    &lt;&lt;
                </button>
            </div>
            
            <div id="contenido-titulo" style="font-size:11px; color:#555; line-height:1.3;">
                <b>Emisión:</b> {FECHA_EJECUCION}<br>
                <b>Fuente:</b> Open-Meteo API (ECMWF & GFS)
                
                <div style="margin-top: 8px; padding-top: 6px; border-top: 1px solid #eee;">
                    <label for="opacity-slider" style="font-weight:bold; color:#333;">
                        Transparencia Capa (IDW):
                    </label>
                    <input id="opacity-slider" type="range" min="0" max="100" value="80" 
                           style="width:100%; margin-top:3px; height: 14px;">
                </div>
            </div>
        </div>

        <button id="btn-open-titulo" onclick="toggleTitulo()" 
                style="display:none; position: fixed; top: 80px; left: 10px; z-index:9999; 
                       background: #1a252f; color: white; border: none; border-radius: 4px; 
                       padding: 5px 8px; font-size: 11px; cursor: pointer; font-weight: bold; box-shadow: 0 0 5px rgba(0,0,0,0.3);">
            &gt;&gt; Título
        </button>

        <button id="btn-open-capas" 
                style="display:none; position: fixed; top: 10px; right: 10px; z-index:9999; 
                       background: #2c3e50; color: white; border: none; border-radius: 4px; 
                       padding: 5px 8px; font-size: 11px; cursor: pointer; font-weight: bold; box-shadow: 0 0 5px rgba(0,0,0,0.3);">
            &lt;&lt; Capas
        </button>

        <div style="position: fixed; bottom: 20px; right: 20px; width: 140px; z-index:9999; 
                    background-color: white; padding: 8px 10px; border-radius: 8px; 
                    box-shadow: 0 0 10px rgba(0,0,0,0.3); font-family: Arial, sans-serif; font-size:11px; max-height:360px; overflow-y:auto;">
            <div style="font-weight:bold; font-size:11px; margin-bottom:4px; text-align:center;">Lluvia (mm)</div>
        """

        for _, _, color, label in RANGOS_COLOR:
            html_panel += f"""
            <div style="display: flex; align-items: center; margin-bottom: 2px;">
                <div style="width: 18px; height: 11px; background-color: {color}; border: 1px solid #666; margin-right: 6px;"></div>
                <span>{label}</span>
            </div>
            """

        html_panel += f"""
        </div>

        <style>
            .leaflet-control-layers {{ font-size: 11px !important; padding: 6px 10px !important; border-radius: 6px !important; }}
        </style>

        <script>
            var gridValores = {json.dumps(js_grid_data)};
            
            function toggleTitulo() {{
                var panel = document.getElementById('panel-titulo');
                var btnOpen = document.getElementById('btn-open-titulo');
                if (panel.style.display === 'none') {{ panel.style.display = 'block'; btnOpen.style.display = 'none'; }} 
                else {{ panel.style.display = 'none'; btnOpen.style.display = 'block'; }}
            }}

            document.addEventListener("DOMContentLoaded", function() {{
                var slider = document.getElementById('opacity-slider');
                if (slider) {{
                    slider.addEventListener('input', function(e) {{
                        var val = e.target.value / 100.0;
                        var overlays = document.querySelectorAll('.leaflet-image-layer');
                        overlays.forEach(function(el) {{ el.style.opacity = val; }});
                    }});
                }}

                var layerControl = document.querySelector('.leaflet-control-layers');
                if (layerControl) {{
                    var headerContainer = document.createElement('div');
                    headerContainer.style.cssText = 'overflow: hidden; margin-bottom: 6px; border-bottom: 1px solid #ddd; padding-bottom: 3px;';
                    headerContainer.innerHTML = '<span style="font-weight:bold; font-size:11px; float:left;">Capas</span><button id="btn-toggle-capas" style="background:#e74c3c; color:white; border:none; border-radius:3px; padding:1px 6px; font-size:10px; cursor:pointer; float:right; font-weight:bold;">&gt;&gt;</button>';
                    layerControl.insertBefore(headerContainer, layerControl.firstChild);
                }}

                document.addEventListener('click', function(e) {{
                    if (e.target && e.target.id === 'btn-toggle-capas') {{
                        var lc = document.querySelector('.leaflet-control-layers');
                        var btnOpenC = document.getElementById('btn-open-capas');
                        if (lc) lc.style.display = 'none';
                        if (btnOpenC) btnOpenC.style.display = 'block';
                    }}
                    if (e.target && e.target.id === 'btn-open-capas') {{
                        var lc = document.querySelector('.leaflet-control-layers');
                        var btnOpenC = document.getElementById('btn-open-capas');
                        if (lc) lc.style.display = 'block';
                        if (btnOpenC) btnOpenC.style.display = 'none';
                    }}
                }});

                var mapEl = document.querySelector('.folium-map');
                if (mapEl && window[mapEl.id]) {{
                    var mapObj = window[mapEl.id];
                    var tooltip = L.tooltip({{sticky: true, direction: 'top'}});

                    function mostrarTooltip(lat, lng, latlngObj) {{
                        var minDist = 0.05;
                        var ptEncontrado = null;

                        for (var k = 0; k < gridValores.length; k++) {{
                            var dLat = Math.abs(gridValores[k][0] - lat);
                            var dLng = Math.abs(gridValores[k][1] - lng);
                            if (dLat < minDist && dLng < minDist) {{
                                minDist = dLat + dLng;
                                ptEncontrado = gridValores[k];
                            }}
                        }}

                        if (ptEncontrado) {{
                            tooltip.setLatLng(latlngObj)
                                   .setContent('<b>Lluvia Acumulada:</b><br>ECMWF: ' + ptEncontrado[2] + ' mm<br>GFS: ' + ptEncontrado[3] + ' mm')
                                   .addTo(mapObj);
                        }} else {{
                            mapObj.closeTooltip(tooltip);
                        }}
                    }}

                    mapObj.on('mousemove', function(e) {{ mostrarTooltip(e.latlng.lat, e.latlng.lng, e.latlng); }});
                    mapObj.on('click', function(e) {{ mostrarTooltip(e.latlng.lat, e.latlng.lng, e.latlng); }});
                }}
            }});
        </script>
        """

        m.get_root().html.add_child(folium.Element(html_panel))
        m.save("index.html")
        
    st.success("✅ Procesamiento completado. Mapa actualizado.")
    
    with open("index.html", "r", encoding="utf-8") as f:
        html_mapa = f.read()
    
    components.html(html_mapa, height=750, scrolling=True)