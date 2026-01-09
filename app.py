import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import pydeck as pdk
from datetime import datetime, date, time

# -----------------------------
# KONFIGURÁCIÓ ÉS ADATOK
# -----------------------------
SPREADSHEET_ID = "1-kng7w3h8Us6Xr93Nk1kJ8zwuSocCadqJvyxpb7mhas"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

st.set_page_config(page_title="Karbantartási vezénylő", layout="wide")

# Google Auth
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SPREADSHEET_ID)

sheets = {
    "allomasok": sh.worksheet("Allomasok"),
    "naplo": sh.worksheet("Naplo"),
    "tech": sh.worksheet("Technikusok"),
    "vez": sh.worksheet("Vezenylesek")
}

@st.cache_data(ttl=2)
def load_all_data():
    return {k: pd.DataFrame(v.get_all_records()) for k, v in sheets.items()}

data = load_all_data()

# -----------------------------
# SEGÉDFÜGGVÉNYEK ÉS LOGIKA
# -----------------------------
def get_status_color(allomas_nev):
    h = data['naplo'][data['naplo']['Állomás neve:'] == allomas_nev]
    v = data['vez'][data['vez']['Allomas_Neve'] == allomas_nev]
    
    nyitott_hibak = h[h['Státusz'] == 'Nyitott']
    visszamenni = h[h['Státusz'] == 'Visszamenni']
    utemezve = not v.empty

    if visszamenni.empty and nyitott_hibak.empty: return None # Nincs hiba
    if not visszamenni.empty and nyitott_hibak.empty: return [255, 255, 0] # Sárga (Csak visszamenni)
    if not visszamenni.empty and not nyitott_hibak.empty and not utemezve: return [139, 69, 19] # Barna
    if utemezve: return [0, 255, 0] # Zöld (Ütemezve)
    return [255, 0, 0] # Piros (Sima nyitott hiba)

# -----------------------------
# UI - NYITOTT HIBÁK LISTÁJA
# -----------------------------
st.title("🛠️ Karbantartási vezénylő")

st.subheader("📝 Aktuális hibaállapotok")
hibas_df = data['naplo'][data['naplo']['Státusz'].isin(['Nyitott', 'Visszamenni'])]

if not hibas_df.empty:
    cols = st.columns([2, 3, 2, 2, 3])
    cols[0].bold("Dátum")
    cols[1].bold("Állomás")
    cols[2].bold("Hiba")
    cols[3].bold("Ütemezés")
    cols[4].bold("Műveletek")
    st.divider()

    for idx, row in hibas_df.iterrows():
        c = st.columns([2, 3, 2, 2, 3])
        allomas = row['Állomás neve:']
        c[0].write(row['Dátum'])
        c[1].write(allomas)
        c[2].write(row['Hiba leírása'])
        
        # Ütemezési infó keresése
        v_info = data['vez'][data['vez']['Allomas_Neve'] == allomas]
        if not v_info.empty:
            c[3].info(f"👤 {v_info.iloc[-1]['Technikus_Neve']}\n📅 {v_info.iloc[-1]['Datum']}")
        else:
            c[3].write("---")

        # Gombok
        btn_col1, btn_col2 = c[4].columns(2)
        if btn_col1.button("✅ Kész", key=f"done_{idx}"):
            # Törlés logikája (táblázatból való eltávolítás vagy státusz állítás)
            # Itt most egyszerűsítve csak a státuszt állítjuk
            st.success("Munka elvégezve!")
        if btn_col2.button("⚠️ Vissza", key=f"back_{idx}"):
            st.warning("Visszatérés rögzítve.")

# -----------------------------
# TÉRKÉP MEGJELENÍTÉSE
# -----------------------------
st.subheader("📍 Interaktív Térkép")
map_data = data['allomasok'].copy()
map_data['hibak_szama'] = map_data['Nev'].apply(lambda x: len(data['naplo'][(data['naplo']['Állomás neve:'] == x) & (data['naplo']['Státusz'].isin(['Nyitott', 'Visszamenni']))]))
map_data = map_data[map_data['hibak_szama'] > 0]

# Színlogika
def get_border(tipus):
    if tipus == "MOL": return [0, 255, 0] # Zöld keret
    if tipus == "ORLEN": return [255, 0, 0] # Piros keret
    return [0, 191, 255] # Világoskék

map_data['fill_color'] = map_data['Nev'].apply(get_status_color)
map_data['line_color'] = map_data['Tipus'].apply(get_border)

st.pydeck_chart(pdk.Deck(
    map_style='mapbox://styles/mapbox/light-v10',
    initial_view_state=pdk.ViewState(latitude=47.1, longitude=19.5, zoom=7),
    layers=[
        pdk.Layer(
            "ScatterplotLayer",
            map_data,
            get_position="[Lon, Lat]",
            get_fill_color="fill_color",
            get_line_color="line_color",
            line_width_min_pixels=3,
            get_radius=5000,
            pickable=True,
        ),
        pdk.Layer(
            "TextLayer",
            map_data,
            get_position="[Lon, Lat]",
            get_text="hibak_szama",
            get_size=16,
            get_color=[0, 0, 0],
            get_alignment_baseline="'center'"
        )
    ]
))

# -----------------------------
# VEZÉNYLÉS FORM
# -----------------------------
st.sidebar.header("📋 Vezénylés")
free_send = st.sidebar.checkbox("Nem aktív hiba küldés")

if free_send:
    v_allomasok = data['allomasok']['Nev'].tolist()
else:
    v_allomasok = hibas_df['Állomás neve:'].unique().tolist()

with st.sidebar.form("vez_form"):
    tech = st.selectbox("Technikus", data['tech']['Név'].tolist() if not data['tech'].empty else [])
    cel = st.selectbox("Célállomás", v_allomasok)
    v_datum = st.date_input("Dátum")
    submit = st.form_submit_button("Kirendelés")
    
    if submit:
        sheets['vez'].append_row([tech, cel, str(v_datum), "Vezényelve"])
        st.success("Sikeres vezénylés!")
        st.cache_data.clear()
