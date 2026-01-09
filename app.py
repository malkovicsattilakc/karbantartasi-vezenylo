import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import pydeck as pdk
from datetime import datetime, date, time

# -----------------------------
# KONFIGURÁCIÓ
# -----------------------------
SPREADSHEET_ID = "1-kng7w3h8Us6Xr93Nk1kJ8zwuSocCadqJvyxpb7mhas"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

st.set_page_config(page_title="Karbantartási vezénylő", layout="wide")

# Google Auth
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SPREADSHEET_ID)

# Munkalapok
sheet_naplo = sh.worksheet("Naplo")
sheet_vez = sh.worksheet("Vezenylesek")
sheet_allomasok = sh.worksheet("Allomasok")
sheet_tech = sh.worksheet("Technikusok")

def load_all_data():
    # A get_all_records() néha elcsúszik, ha üresek a fejlécek, tisztítjuk az oszlopneveket
    naplo_data = pd.DataFrame(sheet_naplo.get_all_records())
    naplo_data.columns = [c.strip() for c in naplo_data.columns] # Szóközök eltávolítása a nevekből
    return {
        "allomasok": pd.DataFrame(sheet_allomasok.get_all_records()),
        "naplo": naplo_data,
        "tech": pd.DataFrame(sheet_tech.get_all_records()),
        "vez": pd.DataFrame(sheet_vez.get_all_records())
    }

data = load_all_data()

# Oszlopnevek rögzítése a biztonság kedvéért (a te táblázatod alapján)
COL_ALLOMAS_NAPLO = "Állomás neve:" 
COL_STATUSZ = "Státusz"

# -----------------------------
# TÁBLÁZAT MÓDOSÍTÓ FUNKCIÓK
# -----------------------------
def update_status(row_idx, new_status):
    # A gspread-nél a 2. sortól kezdődnek az adatok, és +1 a fejléc miatt
    sheet_naplo.update_cell(row_idx + 2, 4, new_status) # 4. oszlop a Státusz
    st.cache_data.clear()
    st.rerun()

def delete_scheduling(allomas_nev):
    # Megkeressük a vezénylések között és töröljük a sort
    cells = sheet_vez.findall(allomas_nev)
    for cell in cells:
        sheet_vez.delete_rows(cell.row)
    st.cache_data.clear()
    st.rerun()

# -----------------------------
# UI - HIBALISTA
# -----------------------------
st.title("🛠️ Karbantartási vezénylő")
st.subheader("📝 Aktuális hibaállapotok")

# Szűrés a releváns oszlopra a KeyError elkerülésével
hibas_df = data['naplo'][data['naplo'][COL_STATUSZ].isin(['Nyitott', 'Visszamenni'])]

if not hibas_df.empty:
    cols = st.columns([1.5, 2, 2.5, 2, 2.5])
    cols[0].write("**Dátum**")
    cols[1].write("**Állomás**")
    cols[2].write("**Hiba leírása**")
    cols[3].write("**Ütemezés**")
    cols[4].write("**Műveletek**")
    st.divider()

    for idx, row in hibas_df.iterrows():
        c = st.columns([1.5, 2, 2.5, 2, 2.5])
        allomas = row[COL_ALLOMAS_NAPLO]
        
        c[0].write(row['Dátum'])
        c[1].write(allomas)
        
        desc = row['Hiba leírása']
        if row[COL_STATUSZ] == 'Visszamenni':
            c[2].warning(f"⚠️ {desc}")
        else:
            c[2].write(desc)
        
        # Ütemezés keresése
        v_info = data['vez'][data['vez']['Allomas_Neve'] == allomas]
        if not v_info.empty:
            v_row = v_info.iloc[-1]
            c[3].info(f"👤 {v_row['Technikus_Neve']}\n📅 {v_row['Datum']}")
        else:
            c[3].write("---")

        # GOMBOK MŰKÖDÉSE
        b1, b2, b3 = c[4].columns(3)
        if b1.button("✅ Kész", key=f"k{idx}"):
            update_status(idx, "Kész")
            delete_scheduling(allomas) # Ha kész, az ütemezés is törlődik
        if b2.button("🔄 Vissza", key=f"v{idx}"):
            update_status(idx, "Visszamenni")
        if b3.button("🗑️ Töröl", key=f"t{idx}"):
            delete_scheduling(allomas)

# -----------------------------
# TÉRKÉP (Színlogika javítva)
# -----------------------------
st.subheader("📍 Térkép")

def get_fill_color(row_allomas):
    h = data['naplo'][data['naplo'][COL_ALLOMAS_NAPLO] == row_allomas]
    v = data['vez'][data['vez']['Allomas_Neve'] == row_allomas]
    
    if h.empty: return [200, 200, 200, 50]
    
    is_vissza = "Visszamenni" in h[COL_STATUSZ].values
    is_nyitott = "Nyitott" in h[COL_STATUSZ].values
    is_utemezve = not v.empty

    if is_vissza and not is_nyitott: return [255, 255, 0] # Sárga
    if is_vissza and is_nyitott and not is_utemezve: return [139, 69, 19] # Barna
    if is_utemezve: return [0, 255, 0] # Zöld
    return [255, 0, 0] # Piros

map_df = data['allomasok'].copy()
map_df['hibak_szama'] = map_df['Nev'].apply(lambda x: len(data['naplo'][(data['naplo'][COL_ALLOMAS_NAPLO] == x) & (data['naplo'][COL_STATUSZ].isin(['Nyitott', 'Visszamenni']))]))
map_df = map_df[map_df['hibak_szama'] > 0]

if not map_df.empty:
    map_df['fill_color'] = map_df['Nev'].apply(get_fill_color)
    map_df['line_color'] = map_df['Tipus'].apply(lambda t: [0, 255, 0] if t=="MOL" else ([255, 0, 0] if t=="ORLEN" else [0, 191, 255]))

    st.pydeck_chart(pdk.Deck(
        map_style='mapbox://styles/mapbox/light-v10',
        initial_view_state=pdk.ViewState(latitude=47.1, longitude=19.5, zoom=7),
        layers=[
            pdk.Layer(
                "ScatterplotLayer", map_df, get_position="[Lon, Lat]",
                get_fill_color="fill_color", get_line_color="line_color",
                line_width_min_pixels=4, get_radius=6000, pickable=True
            ),
            pdk.Layer(
                "TextLayer", map_df, get_position="[Lon, Lat]",
                get_text="hibak_szama", get_size=22, get_color=[0, 0, 0],
                get_alignment_baseline="'center'"
            )
        ]
    ))

# -----------------------------
# VEZÉNYLÉS OLDALSÁV
# -----------------------------
st.sidebar.header("📋 Vezénylés")
free_send = st.sidebar.checkbox("Nem aktív hiba küldés")
lista = data['allomasok']['Nev'].tolist() if free_send else hibas_df[COL_ALLOMAS_NAPLO].unique().tolist()

with st.sidebar.form("v_form"):
    tech = st.selectbox("Technikus", data['tech']['Név'].tolist() if not data['tech'].empty else [])
    hova = st.selectbox("Állomás", lista)
    mikor = st.date_input("Dátum")
    if st.form_submit_button("Vezényel"):
        sheet_vez.append_row([tech, hova, str(mikor), "Aktív"])
        st.success("Vezénylés rögzítve!")
        st.cache_data.clear()
        st.rerun()
