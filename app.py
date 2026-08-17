import os
import re
import datetime
import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st

# Importar funcions del scraper modularitzat
from scraper import descarregar_dades_mercat_analytics, trobar_jugador, format_number, normalitzar_text

# ==============================================================================
# 📱 CONFIGURACIÓ DE LA PÀGINA DE STREAMLIT (OPTIMITZADA PER A MÒBIL)
# ==============================================================================
st.set_page_config(
    page_title="LaLiga Fantasy App",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed" # Amagat per defecte al mòbil per guanyar espai
)

# Estils CSS customitzats per a millorar la visualització en dispositius mòbils (mètrics grans, etc.)
st.markdown("""
<style>
    .stMetric {
        background-color: #f8f9fa;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #dee2e6;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    div[data-testid="stMetricValue"] {
        font-size: 22px !important;
        font-weight: bold;
    }
    .main .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 1.5rem !important;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# ⚙️ CONFIGURACIÓ DE LES PLANTILLES DE LA TEVA LLIGA (SEASONS 2026/27)
# Modifica aquestes llistes quan vulguis fer transferències. Els noms no han de ser exactes!
# ==============================================================================
EL_MEU_EQUIP = [
    "Dituro", "Zubeldia", "Hancko", "Natan", "Kike Salas", 
    "Diego Llorente", "Paredes", "Bigas", "Le Normand", 
    "Unai Lopez", "Pepelu", "Febas", "Puerta", "De frutos", "Raul Moro"
]

COMPETIDORS = {
    "Carre": [
        "Courtois", "Szczesny", "Marcos Alonso", "Tenaglia", "Areso", 
        "Ximo Navarro", "Noubi", "Urko", "Canales", "Carlos Alvarez", 
        "Gueye", "Angel Perez", "Aubameyang", "Hugo Duro", "Satriano"
    ],
    "Suec": [
        "El Hilali", "Tárrega", "Hjulmand", "Larrubia", "De Galarreta", 
        "Williot", "Aimar", "Iker Muñoz", "Ayoze", "Lucas Boye", 
        "Isi", "Toni Martinez"
    ]
}

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fantasy_history.csv")
CACHE_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "futbolfantasy_players.csv")

# ==============================================================================
# 🔌 GESTIÓ DEL MOTOR D'ACTUALITZACIÓ (SIDEBAR)
# ==============================================================================
st.sidebar.title("⚙️ Configuració")

# Mostrar la data i hora de la darrera actualització de dades
if os.path.exists(CACHE_FILE_PATH):
    mtime = os.path.getmtime(CACHE_FILE_PATH)
    last_update = datetime.datetime.fromtimestamp(mtime)
    st.sidebar.info(f"📅 Darrere Actualització:\\n{last_update.strftime('%d/%m/%Y a les %H:%M')}")
else:
    st.sidebar.warning("⚠️ No s'han trobat dades locals. Cal realitzar un scrape.")

# Botó d'actualització interactiu al mòbil
if st.sidebar.button("🔄 Actualitzar Mercat Online"):
    with st.spinner("⚡ Carregant dades en temps real de FutbolFantasy (15s)..."):
        try:
            # Descarregar dades del mercat i de les 20 alineacions unificades
            df_all = descarregar_dades_mercat_analytics(force_update=True)
            st.sidebar.success("🎉 Dades unificades correctament!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error actualitzant dades: {e}")

# ==============================================================================
# 📥 CARREGA DE DADES I ASSIGNACIÓ DE PROPIETARIS
# ==============================================================================
df_all = descarregar_dades_mercat_analytics(force_update=False)

if df_all.empty:
    st.error("❌ No s'han pogut descarregar ni carregar les dades de FutbolFantasy. Prems el botó d'actualització de la barra lateral per provar online.")
    st.stop()

# Normalitzar lesions i sancions per compatibilitat de types de pandas
df_all['lesion'] = df_all['lesion'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
df_all['sancion'] = df_all['sancion'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

# Assignar propietaris de forma unificada
df_all['propietario'] = ""

for nom in EL_MEU_EQUIP:
    jugador = trobar_jugador(nom, df_all)
    if jugador is not None:
        df_all.loc[df_all['jugador'] == jugador['jugador'], 'propietario'] = 'JO (El meu equip)'

for rival, llista in COMPETIDORS.items():
    for nom in llista:
        jugador = trobar_jugador(nom, df_all)
        if jugador is not None:
            df_all.loc[df_all['jugador'] == jugador['jugador'], 'propietario'] = rival

df_validos = df_all[df_all['propietario'] != ""].copy()

# ==============================================================================
# 🏆 FUNCIONS AUXILIARS DE REGISTRE HISTÒRIC D'SNAPSHOTS
# ==============================================================================
def inicialitzar_dades_simulades_si_no_existeix(today_str, df_val, competidors):
    if os.path.exists(HISTORY_FILE):
        return
    
    today = datetime.datetime.strptime(today_str, "%Y-%m-%d")
    mock_records = []
    totals_actuals = df_val.groupby('propietario')['valor_actual'].sum().to_dict()

    for days_back in range(4, 0, -1):
        d = today - datetime.timedelta(days=days_back)
        d_str = d.strftime("%Y-%m-%d")
        
        for owner, val in totals_actuals.items():
            val_M = val / 1_000_000
            factor_creixement = 1.0 - (days_back * 0.01) if owner == 'JO (El meu equip)' else 1.0 - (days_back * 0.005)
            mock_records.append({
                'date': d_str,
                'rival': owner,
                'team_value_M': val_M * factor_creixement,
                'daily_gain_K': val_M * 10,
                'player_count': len(EL_MEU_EQUIP) if owner == 'JO (El meu equip)' else len(competidors.get(owner, []))
            })
            
    df_mock = pd.DataFrame(mock_records)
    df_mock.to_csv(HISTORY_FILE, index=False)

def registrar_snapshot_historial(df_val, competidors):
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    inicialitzar_dades_simulades_si_no_existeix(today_str, df_val, competidors)
    
    records_avui = []
    df_grouped = df_val.groupby('propietario')
    
    for owner, group in df_grouped:
        records_avui.append({
            'date': today_str,
            'rival': owner,
            'team_value_M': group['valor_actual'].sum() / 1_000_000,
            'daily_gain_K': group['diferencia_valor'].sum() / 1_000,
            'player_count': len(group)
        })
            
    df_avui = pd.DataFrame(records_avui)
    if df_avui.empty:
        return
        
    if os.path.exists(HISTORY_FILE):
        df_hist = pd.read_csv(HISTORY_FILE)
        df_hist = df_hist[~((df_hist['date'] == today_str) & (df_hist['rival'].isin(df_avui['rival'])))]
        df_final = pd.concat([df_hist, df_avui], ignore_index=True)
    else:
        df_final = df_avui
        
    df_final = df_final.sort_values(by=['date', 'rival']).reset_index(drop=True)
    df_final.to_csv(HISTORY_FILE, index=False)

# Auto-registrar l'estat d'avui en carregar
registrar_snapshot_historial(df_validos, COMPETIDORS)

# ==============================================================================
# 🎮 INTERFICIE D'USUARI EN PESTANYES (TABS - DISSENY RESPONSIVE MÒBIL)
# ==============================================================================
st.title("⚽ LaLiga Fantasy - Dashboard Mòbil")

tab_resum, tab_plantilles, tab_mercat, tab_mapa = st.tabs([
    "📊 Resum Lliga", "👥 Plantilles", "🎯 Mercat i Fitxatges", "🌍 Mapa Dispersió"
])

# ------------------------------------------------------------------------------
# TAB 1: 📊 RESUM LLIGA (KPIs i Gràfics de Línies)
# ------------------------------------------------------------------------------
with tab_resum:
    # 1. Targetes de KPIs del meu equip
    df_meu = df_validos[df_validos['propietario'] == 'JO (El meu equip)'].copy()
    
    if not df_meu.empty:
        val_total_meu = df_meu['valor_actual'].sum() / 1_000_000
        reval_diaria_meu = df_meu['diferencia_valor'].sum() / 1_000
        lesionats_meu = len(df_meu[(df_meu['lesion'] != '-1') | (df_meu['sancion'] != '0')])
        
        # Mètrics moderns de Streamlit
        col1, col2, col3 = st.columns(3)
        col1.metric("Valor del teu Equip", f"{val_total_meu:.2f} M €")
        col2.metric(
            "Generació Econòmica Avui", 
            f"{reval_diaria_meu:+.1f} K €",
            delta=f"{reval_diaria_meu:+.1f} K €",
            delta_color="normal" if reval_diaria_meu >= 0 else "inverse"
        )
        col3.metric("Jugadors Baixa/Dubte 🏥", f"{lesionats_meu} jugadors")
        
    st.markdown("---")
    
    # 2. Carregar dades històriques i filtrar pels competidors actuals
    if os.path.exists(HISTORY_FILE):
        df_hist = pd.read_csv(HISTORY_FILE)
        competidors_actius = list(COMPETIDORS.keys()) + ['JO (El meu equip)']
        df_hist = df_hist[df_hist['rival'].isin(competidors_actius)]
        
        # Gràfic 1: Valoració total al llarg del temps
        st.subheader("📈 Evolució de la Valoració de les Plantilles (M €)")
        fig_trend = px.line(
            df_hist,
            x='date',
            y='team_value_M',
            color='rival',
            markers=True,
            hover_name='rival',
            hover_data={'date': True, 'team_value_M': ':.2f M €', 'player_count': True},
            color_discrete_map={'JO (El meu equip)': '#007bff'}
        )
        fig_trend.update_layout(
            xaxis_title="Data de l'Snapshot",
            yaxis_title="Valor en Milions (M €)",
            legend_title="Equips",
            hovermode="x unified",
            margin=dict(l=10, r=10, t=30, b=10),
            height=380
        )
        st.plotly_chart(fig_trend, use_container_width=True)
        
        st.markdown("---")
        
        # Gràfic 2: Canvi diari acumulatiu d'economia
        st.subheader("💰 Economia Diària: Variació de Valor respecte Ahir (K €)")
        fig_econ = px.line(
            df_hist,
            x='date',
            y='daily_gain_K',
            color='rival',
            markers=True,
            hover_name='rival',
            hover_data={'date': True, 'daily_gain_K': ':.1f K €'},
            color_discrete_map={'JO (El meu equip)': '#007bff'}
        )
        # Línia de base zero de l'economia
        fig_econ.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5)
        fig_econ.update_layout(
            xaxis_title="Data de l'Snapshot",
            yaxis_title="Revalorització (K €)",
            legend_title="Equips",
            hovermode="x unified",
            margin=dict(l=10, r=10, t=30, b=10),
            height=380
        )
        st.plotly_chart(fig_econ, use_container_width=True)
    else:
        st.info("💡 Encara no hi ha prou dades per mostrar els gràfics històrics de tendència. S'aniran gravant cada dia!")

# ------------------------------------------------------------------------------
# TAB 2: 👥 PLANTILLES (Rosters per Propietari)
# ------------------------------------------------------------------------------
with tab_plantilles:
    st.subheader("👥 Explorador de Plantilles de la Lliga")
    
    opcions_rivals = ["JO (El meu equip)"] + list(COMPETIDORS.keys())
    propietari_sel = st.selectbox("Selecciona un Propietari per inspeccionar:", opcions_rivals)
    
    # Filtrar jugadors d'aquest propietari
    df_rival = df_validos[df_validos['propietario'] == propietari_sel].copy()
    
    if not df_rival.empty:
        # Formatejar decimals per fer-ho maco
        df_rival['val_M'] = df_rival['valor_actual'] / 1_000_000
        df_rival['diff_K'] = df_rival['diferencia_valor'] / 1_000
        
        df_rival['Estat Físic'] = df_rival['lesion'].apply(lambda x: '🏥 Lesionat/Dubte' if x != '-1' else '🟢 Disponible')
        df_rival['Sanció'] = df_rival['sancion'].apply(lambda x: '🟥 Sancionat' if x != '0' else '🟢 Disponible')
        
        # Taula ordenada per titularitat i valor de plantilla
        df_rival_show = df_rival[['jugador', 'posicion', 'prob', 'val_M', 'diff_K', 'Estat Físic', 'Sanció']].copy()
        df_rival_show.columns = ['Jugador', 'Posició', 'Prob. Titularitat', 'Valor (M €)', 'Variació Diària (K €)', 'Estat Físic', 'Sanció']
        
        df_rival_show = df_rival_show.sort_values(by=['Prob. Titularitat', 'Valor (M €)'], ascending=[False, False]).reset_index(drop=True)
        
        # Mètrics d'equip d'aquest rival
        r_val_total = df_rival['valor_actual'].sum() / 1_000_000
        r_diff_total = df_rival['diferencia_valor'].sum() / 1_000
        
        col_r1, col_r2 = st.columns(2)
        col_r1.metric("Valor Plantilla", f"{r_val_total:.2f} M €")
        col_r2.metric("Variació Diària", f"{r_diff_total:+.1f} K €")
        
        # Pintar la taula amb colors segons probabilitats
        def color_probabilitat(val):
            try:
                val_num = int(str(val).replace('%', ''))
                if val_num >= 80:
                    return 'background-color: #d4edda; color: #155724'
                elif val_num >= 50:
                    return 'background-color: #fff3cd; color: #856404'
                else:
                    return 'background-color: #f8d7da; color: #721c24'
            except:
                return ''
                
        st.dataframe(
            df_rival_show.style.map(color_probabilitat, subset=['Prob. Titularitat'])
                               .format({'Valor (M €)': '{:.2f} M €', 'Variació Diària (K €)': '{:+.1f} K €'}),
            use_container_width=True,
            height=500
        )
    else:
        st.warning("No s'ha trobat cap jugador per a aquest propietari.")

# ------------------------------------------------------------------------------
# TAB 3: 🎯 MERCAT I FITXATGES (Buscador i Gangues)
# ------------------------------------------------------------------------------
with tab_mercat:
    st.subheader("🎯 Cercador de Jugadors (Fitxes de Licitació)")
    
    # 1. Buscador complet unificat
    llista_noms_jugadors = sorted(df_all['jugador'].unique())
    nom_sel = st.selectbox("Escriu o selecciona un jugador per obrir la seva fitxa:", llista_noms_jugadors)
    
    jug_info = trobar_jugador(nom_sel, df_all)
    
    if jug_info is not None:
        # Calcular variables del teu model clàssic de 14 dies!
        valor_actual = jug_info['valor_actual']
        diff_diaria = jug_info['diferencia_valor']
        
        val_14d = valor_actual + (diff_diaria * 14)
        gan_creixement = val_14d - valor_actual
        gan_maquina = val_14d * 0.10
        gan_total = gan_creixement + gan_maquina
        
        puja_max = val_14d * 0.9
        puja_ideal = valor_actual + (val_14d - valor_actual) * 0.6
        puja_recomanada = format_number(int(puja_ideal)) + " €" if puja_ideal >= valor_actual else "no fichar"
        
        propietari_final = jug_info['propietario'] if jug_info['propietario'] else "Lliure (Al Mercat)"
        estat_fisic_icon = "🏥 Molèsties/Lesió" if jug_info['lesion'] != '-1' else "🟢 Disponible"
        sancio_icon = "🟥 Sancionat" if jug_info['sancion'] != '0' else "🟢 Disponible"
        
        # Renderitzar una fitxa mètrica interactiva al mòbil
        st.markdown(f"""
        <div style="background-color: #f1f3f5; padding: 18px; border-radius: 10px; border-left: 5px solid #28a745; margin-bottom: 20px;">
            <h3 style="margin-top:0px; color:#212529;">{jug_info['jugador']}</h3>
            <p style="margin-bottom:6px;"><b>Propietari:</b> <span style="background-color:#e9ecef; padding:2px 6px; border-radius:4px;">{propietari_final}</span> | <b>Posició:</b> {jug_info['posicion']}</p>
            <p style="margin-bottom:6px;"><b>Probabilitat Titularitat:</b> <span style="font-weight:bold; color:#155724;">{jug_info['prob']}</span></p>
            <p style="margin-bottom:6px;"><b>Estat Físic:</b> {estat_fisic_icon} | <b>Sanció:</b> {sancio_icon}</p>
            <hr style="margin: 10px 0; border: 0; border-top: 1px solid #dee2e6;">
            <p style="font-size:15px; margin-bottom:4px;">💰 <b>Valor actual:</b> {format_number(valor_actual)} €</p>
            <p style="font-size:15px; margin-bottom:4px; color:{'#28a745' if diff_diaria >= 0 else '#dc3545'}">📈 <b>Variació Diària:</b> {'+' if diff_diaria > 0 else ''}{format_number(diff_diaria)} €</p>
            <p style="font-size:15px; margin-bottom:4px;">📊 <b>Valor Projectat a 14 dies:</b> {format_number(int(val_14d))} €</p>
            <p style="font-size:15px; margin-bottom:12px; color:#28a745;">💸 <b>Guany Total Esperat (14d + Màquina):</b> {format_number(int(gan_total))} €</p>
            <h4 style="margin:10px 0 5px 0; color:#0056b3;">🔑 Licitacions Model (Especulació):</h4>
            <p style="font-size:16px; margin-bottom:4px; color:#d9534f;">🚨 <b>Sostre de Licitació (Puja Màxima):</b> {format_number(int(puja_max))} €</p>
            <p style="font-size:18px; margin-bottom:0px; font-weight:bold; color:#28a745;">💎 <b>Puja Ideal Recomanada:</b> {puja_recomanada}</p>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("---")
    
    # 2. Recomanacions automàtiques (Top 10 Gangues lliures)
    st.subheader("🔥 Top 10 Oportunitats d'Especulació (Jugadors Lliures)")
    
    df_free = df_all[df_all['propietario'] == ""].copy()
    
    if not df_free.empty:
        df_rec = df_free.assign(
            valor_14d = lambda x: x.valor_actual + (x.diferencia_valor * 14),
            gan_crec = lambda x: x.valor_14d - x.valor_actual,
            gan_maq = lambda x: x.valor_14d * 0.10,
            gan_total = lambda x: x.gan_crec + x.gan_maq
        )
        
        # Normalitzar score 0-100%
        min_g = df_rec['gan_total'].min()
        max_g = df_rec['gan_total'].max()
        if max_g != min_g:
            df_rec['score'] = (df_rec['gan_total'] - min_g) / (max_g - min_g) * 100
        else:
            df_rec['score'] = 100.0
            
        df_rec['puja_max'] = df_rec['valor_14d'] * 0.9
        df_rec['puja_ideal'] = df_rec['valor_actual'] + (df_rec['valor_14d'] - df_rec['valor_actual']) * 0.6
        df_rec['puja_recomanada'] = df_rec['puja_ideal'].where(df_rec['puja_ideal'] >= df_rec['valor_actual'], -1)
        
        # Només els que pugen avui
        df_top = df_rec[df_rec['diferencia_valor'] > 0].sort_values(by='score', ascending=False).head(10).reset_index(drop=True)
        
        taula_g = pd.DataFrame()
        taula_g['Jugador'] = df_top['jugador']
        taula_g['Posició'] = df_top['posicion']
        taula_g['Valor actual'] = df_top['valor_actual'].apply(format_number) + " €"
        taula_g['Pugen/Dia'] = df_top['diferencia_valor'].apply(lambda x: f"+{format_number(x)}") + " €"
        taula_g['Puja Ideal'] = df_top['puja_recomanada'].apply(lambda x: format_number(int(x)) + " €" if x != -1 else "no fichar")
        taula_g['Score Licitació'] = df_top['score']
        
        st.dataframe(
            taula_g.style.background_gradient(cmap='Greens', subset=['Score Licitació'])
                         .format({'Score Licitació': '{:.1f}%'}),
            use_container_width=True,
            height=380
        )
    else:
        st.info("No hi ha jugadors lliures al mercat.")

# ------------------------------------------------------------------------------
# TAB 4: 🌍 MAPA DE DISPERSIÓ (Scatter Plot Interactiu)
# ------------------------------------------------------------------------------
with tab_mapa:
    st.subheader("🌍 Mapa de Jugadors de la Lliga (Scatter Plot Interactiu)")
    
    # Estructurar dataframe per Plotly
    records_disp = []
    for idx, row in df_validos.iterrows():
        records_disp.append({
            'Jugador': row['jugador'],
            'Posició': row['posicion'],
            'Valor (M €)': row['valor_actual'] / 1_000_000,
            'Variació (K €)': row['diferencia_valor'] / 1_000,
            'Propietari': row['propietario']
        })
        
    df_disp = pd.DataFrame(records_disp)
    
    if not df_disp.empty:
        fig_players = px.scatter(
            df_disp,
            x='Valor (M €)',
            y='Variació (K €)',
            color='Propietari',
            symbol='Propietari',
            hover_name='Jugador',
            hover_data={
                'Posició': True,
                'Valor (M €)': ':.2f M €',
                'Variació (K €)': ':.1f K €',
                'Propietari': True
            }
        )
        
        # Línia de revalorització zero
        fig_players.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5, line_width=1.5)
        
        fig_players.update_traces(
            marker=dict(size=12, opacity=0.85, line=dict(width=1, color='DarkSlateGrey'))
        )
        
        fig_players.update_layout(
            xaxis_title="Valor de Mercat de l'Snapshot (Milions d'Euros - M €)",
            yaxis_title="Variació de Preu Diària (Milers d'Euros - K €)",
            legend_title="Propietari",
            hovermode="closest",
            margin=dict(l=10, r=10, t=10, b=10),
            height=500
        )
        
        st.plotly_chart(fig_players, use_container_width=True)
    else:
        st.warning("No hi ha jugadors suficients per dibuixar el mapa de dispersió.")
