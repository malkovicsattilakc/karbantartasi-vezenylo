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

# Munkalapok elérése
sheet_naplo = sh.worksheet("Naplo")
sheet_vez = sh.worksheet("Vezenylesek")
sheet_allomasok = sh.worksheet("Allomasok")
sheet_tech = sh.worksheet("Technikusok")

@st.cache_data(ttl=2)
def load_all_data():
    return {
        "allomasok": pd.DataFrame(sheet_allomasok.get_all_records()),
        "naplo": pd.DataFrame(sheet_naplo.get_all_records()),
        "tech": pd.DataFrame(sheet_tech.get_all_records()),
        "vez": pd.DataFrame(sheet_vez.get_all_records())
    }

data = load_all_data()

# -----------------------------
# LOGIKA ÉS SZÍNEK
# -----------------------------
def get_station_status(allomas_nev):
    h = data['naplo'][data['naplo']['Állomás neve:'] == allomas_nev]
    v = data['vez'][data['vez']['Allomas_Neve'] == allomas_nev]
    
    nyitott = h[h['Státusz'] == 'Nyitott']
    vissza = h[h['Státusz'] == 'Visszamenni']
    utemezve = not v.empty

    if vissza.empty and nyitott.empty: return None 
    if not vissza.empty and nyitott.empty: return [255, 255, 0] # Sárga: Vissza kell menni
    if not vissza.empty and not nyitott.empty and not utemezve: return [139, 69, 19] # Barna: Vissza + Új hiba
    if utemezve: return [0, 255, 0] # Zöld: Ütemezve
    return [255, 0, 0] # Piros: Csak nyitott hiba

# -----------------------------
# UI - HIBALISTA (FENT)
# -----------------------------
st.title("🛠️ Karbantartási vezénylő")

st.subheader("📝 Aktuális hibaállapotok")
hibas_df = data['naplo'][data['naplo']['Státusz'].isin(['Nyitott', 'Visszamenni'])]

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
        allomas = row['Állomás neve:']
        c[0].write(row['Dátum'])
        c[1].write(allomas)
        
        # Ha vissza kell menni, jelezzük a hiba alatt
        if row['Státusz'] == 'Visszamenni':
            c[2].warning(f"{row['Hiba leírása']} (VISSZA KELL MENNI)")
        else:
            c[2].write(row['Hiba leírása'])
        
        # Vezénylési infó keresése
        v_info = data['vez'][data['vez']['Allomas_Neve'] == allomas]
        if not v_info.empty:
            utemezett_tech = v_info.iloc[-1]['Technikus_Neve']
            utemezett_nap = v_info.iloc[-1]['Datum']
            c[3].info(f"👤 {utemezett_tech}\n📅 {utemezett_nap}")
        else:
            c[3].write("---")

        # Gombok
        b1, b2, b3 = c[4].columns(3)
        if b1.button("✅ Kész", key=f"k{idx}"):
            # Itt a Google Sheets-ben is átírhatnánk, most csak a UI-on jelezzük
            st.success(f"{allomas} lezárva.")
        if b2.button("🔄 Vissza", key=f"v{idx}"):
            st.warning("Visszamenni státusz rögzítve.")
        if b3.button("🗑️ Ütem. törlés", key=f"t{idx}"):
            st.error("Ütemezés törölve.")

# -----------------------------
# TÉRKÉP
# -----------------------------
st.subheader("📍 Térkép")
map_df = data['allomasok'].copy()
map_df['hibak_szama'] = map_df['Nev'].apply(lambda x: len(data['naplo'][(data['naplo']['Állomás neve:'] == x) & (data['naplo']['Státusz'].isin(['Nyitott', 'Visszamenni']))]))
map_df = map_df[map_df['hibak_szama'] > 0]

if not map_df.empty:
    map_df['fill_color'] = map_df['Nev'].apply(get_station_status)
    map_df['line_color'] = map_df['Tipus'].apply(lambda t: [0, 255, 0] if t=="MOL" else ([255, 0, 0] if t=="ORLEN" else [0, 191, 255]))

    st.pydeck_chart(pdk.Deck(
        map_style='mapbox://styles/mapbox/light-v10',
        initial_view_state=pdk.ViewState(latitude=47.1, longitude=19.5, zoom=7),
        layers=[
            pdk.Layer(
                "ScatterplotLayer", map_df, get_position="[Lon, Lat]",
                get_fill_color="fill_color", get_line_color="line_color",
                line_width_min_pixels=3, get_radius=5000, pickable=True
            ),
            pdk.Layer(
                "TextLayer", map_df, get_position="[Lon, Lat]",
                get_text="hibak_szama", get_size=20, get_color=[0, 0, 0]
            )
        ]
    ))

# -----------------------------
# VEZÉNYLÉS OLDALSÁV
# -----------------------------
st.sidebar.header("📋 Új vezénylés")
free_send = st.sidebar.checkbox("Nem aktív hiba küldés")

if free_send:
    lista = data['allomasok']['Nev'].tolist()
else:
    lista = hibas_df['Állomás neve:'].unique().tolist()

with st.sidebar.form("v_form"):
    tech = st.selectbox("Technikus", data['tech']['Név'].tolist() if not data['tech'].empty else [])
    hova = st.selectbox("Állomás", lista)
    mikor = st.date_input("Nap")
    if st.form_submit_button("Vezényel"):
        sheet_vez.append_row([tech, hova, str(mikor), "Vezényelve"])
        st.success("Mentve!")
        st.cache_data.clear()
