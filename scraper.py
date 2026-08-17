import os
import re
import time
import datetime
import requests
import unicodedata
import pandas as pd
from bs4 import BeautifulSoup

CACHE_FILE = "futbolfantasy_players.csv"
DATA_FOLDER = "Data"

def format_number(n):
    '''Formatea un número amb punts com a separador de milers per a visualitzacions.'''
    try:
        n_int = int(n)
        return f"{n_int:,}".replace(",", ".")
    except:
        return n

def normalitzar_text(text):
    '''Normalitza el text eliminant accents, majúscules i caràcters especials.'''
    if not text:
        return ""
    text = text.lower()
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9\\s]', '', text).strip()

def trobar_jugador(nom_buscat, df_players):
    '''Cerca un jugador utilitzant un algorisme de coincidència flexible i lliure d'accents.'''
    nom_norm = normalitzar_text(nom_buscat)
    
    # 1. Coincidència exacta o parcial del nom
    for _, row in df_players.iterrows():
        p_nom_norm = normalitzar_text(row['jugador'])
        if nom_norm == p_nom_norm or nom_norm in p_nom_norm or p_nom_norm in nom_norm:
            return row
            
    # 2. Coincidència pel slug de la URL d'enllaç
    for _, row in df_players.iterrows():
        slug = row['href'].split('/')[-1].replace('-', ' ')
        slug_norm = normalitzar_text(slug)
        if nom_norm == slug_norm or nom_norm in slug_norm or slug_norm in nom_norm:
            return row
            
    return None

def descarregar_dades_mercat_analytics(force_update=False):
    '''
    Descarrega les dades de mercat i d'alineació/lesions dels 20 equips de LaLiga,
    unint-les en un DataFrame mestre i desant-ho a la cache i a l'arxiu diari de la carpeta 'Data/'.
    '''
    # Per assegurar que es resolen les rutes relatives correctament en Streamlit i Jupyter
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cache_path = os.path.join(base_dir, CACHE_FILE)
    data_dir_path = os.path.join(base_dir, DATA_FOLDER)
    
    if not force_update and os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path)
            if 'jugador' in df.columns and 'prob' in df.columns:
                print(f"📁 Carregant dades des de la cache local ràpida unificada: {cache_path}...")
                return df
        except Exception as e:
            print(f"Error carregant cache: {e}")
            pass
        
    print("🔍 [1/3] Iniciant la descàrrega de dades de mercat des de FutbolFantasy...")
    start_time = time.time()
    
    url_mercado = 'https://www.futbolfantasy.com/analytics/laliga-fantasy/mercado'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(url_mercado, headers=headers)
        if response.status_code != 200:
            raise Exception(f"No s'ha pogut carregar la pàgina de mercat: {response.status_code}")
            
        soup = BeautifulSoup(response.text, 'html.parser')
        elements = soup.find_all(class_='elemento_jugador')
    except Exception as e:
        print(f"❌ Error en connectar al servidor de FutbolFantasy: {e}")
        # Retorna el fitxer de cache antic si hi ha un error de connexió!
        if os.path.exists(cache_path):
            return pd.read_csv(cache_path)
        return pd.DataFrame()
        
    print(f"📄 S'han trobat {len(elements)} jugadors al mercat. Processant preus...")
    market_players = []
    
    for el in elements:
        nombre = el.get('data-nombre', 'Unknown').strip().title()
        
        val = el.get('data-valor', '0')
        val1 = el.get('data-valor1', '0')
        diff = el.get('data-diferencia1', '0')
        val7 = el.get('data-valor7', '0') # puja_maxima_rentable clàssica de fantasy.ipynb
        pos = el.get('data-posicion', 'N/A')
        eq_id = el.get('data-equipo', 'N/A')
        
        market_players.append({
            "jugador": nombre,
            "diferencia_valor": int(diff) if diff.replace('-','').isdigit() else 0,
            "valor_actual": int(val) if val.isdigit() else 0,
            "valor_anterior": int(val1) if val1.isdigit() else 0,
            "puja_maxima_rentable": int(val7) if val7.isdigit() else 0,
            "posicion": pos,
            "team_id": eq_id,
            "href": f"https://www.futbolfantasy.com/jugadores/{nombre.lower().replace(' ', '-')}"
        })
        
    df_market = pd.DataFrame(market_players)
    
    print("🔍 [2/3] Buscant els enllaços dels 20 equips de LaLiga...")
    url_home = 'https://www.futbolfantasy.com/'
    try:
        res_home = requests.get(url_home, headers=headers)
        soup_home = BeautifulSoup(res_home.text, 'html.parser')
        team_links = sorted(list(set([a['href'] for a in soup_home.find_all('a', href=True) if '/laliga/equipos/' in a['href']])))
    except Exception as e:
        print(f"❌ Error descarregant els equips de LaLiga: {e}")
        team_links = []
        
    print(f"📄 S'han trobat {len(team_links)} equips. Descarregant alineacions, lesions i sancions...")
    lineup_data = {}
    
    for idx, t_url in enumerate(team_links):
        team_slug = t_url.split('/')[-1]
        try:
            t_res = requests.get(t_url, headers=headers)
            if t_res.status_code != 200:
                continue
            t_soup = BeautifulSoup(t_res.text, 'html.parser')
            
            for a in t_soup.find_all('a', href=True):
                href = a['href']
                if '/jugadores/' not in href:
                    continue
                href = href.split('?')[0].rstrip('/')
                
                if href not in lineup_data:
                    lineup_data[href] = {
                        'prob': '0%',
                        'lesion': '-1',
                        'sancion': '0'
                    }
                
                for k in ['data-probabilidad', 'data-lesion', 'data-sancionado']:
                    v = a.get(k)
                    if v:
                        key_name = 'prob' if k == 'data-probabilidad' else ('lesion' if k == 'data-lesion' else 'sancion')
                        old_v = lineup_data[href][key_name]
                        if not old_v or old_v in ['0', 'N/A', '', '0%', '-1'] or (v and v not in ['0', 'N/A', '', '0%', '-1']):
                            lineup_data[href][key_name] = v
        except Exception as e:
            print(f"    ❌ Error processant {team_slug}: {e}")
            
    print("🔍 [3/3] Unint base de dades de mercat amb probabilitats de titularitat i lesions...")
    df_market['prob'] = '0%'
    df_market['lesion'] = '-1'
    df_market['sancion'] = '0'
    
    def clean_href(h):
        return h.split('?')[0].rstrip('/').lower() if h else ""
        
    df_market['href_clean'] = df_market['href'].apply(clean_href)
    clean_lineup = {clean_href(k): v for k, v in lineup_data.items()}
    
    for idx, row in df_market.iterrows():
        h_clean = row['href_clean']
        if h_clean in clean_lineup:
            df_market.at[idx, 'prob'] = clean_lineup[h_clean]['prob']
            df_market.at[idx, 'lesion'] = clean_lineup[h_clean]['lesion']
            df_market.at[idx, 'sancion'] = clean_lineup[h_clean]['sancion']
            
    df_market = df_market.drop(columns=['href_clean'])
    
    # Assegurar tipus de dades
    df_market['lesion'] = df_market['lesion'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    df_market['sancion'] = df_market['sancion'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    # 1. Desar a la cache local ràpida
    df_market.to_csv(cache_path, index=False)
    
    # 2. Desar còpia diària en brut
    os.makedirs(data_dir_path, exist_ok=True)
    hoy = datetime.date.today().strftime("%Y-%m-%d")
    nombre_csv = f"data_{hoy}.csv"
    ruta_csv = os.path.join(data_dir_path, nombre_csv)
    df_market.to_csv(ruta_csv, index=False, encoding="utf-8-sig")
    
    print("✨ Procés complet finalitzat correctament!")
    return df_market
