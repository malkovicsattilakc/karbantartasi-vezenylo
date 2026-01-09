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

@st.cache_data(ttl=2)
def load_all_data():
    # Adatok beolvasása és oszlopnevek tisztítása
    naplo_df = pd.DataFrame(sheet_naplo.get_all_records())
    naplo_df.columns = [str(c).strip() for c in naplo_df.columns]
    
    # Biztonsági oszlopkeresés: megkeressük melyik oszlop tartalmazza az 'Állomás' szót
    allomas_col = next((c for c in naplo_df.columns if 'Állomás' in c), "Állomás neve:")
    statusz_col = next((c for c in naplo_df.columns if 'Státusz' in c), "Státusz")
    
    return {
        "allomasok": pd.DataFrame(sheet_allomasok.get_all_records()),
        "naplo": naplo_df,
        "tech": pd.DataFrame(sheet_tech.get_all_records()),
        "vez": pd.DataFrame(sheet_vez.get_all_records()),
        "cols": {"allomas": allomas_col, "statusz": statusz_col}
    }

data = load_all_data()
COL_A = data["cols"]["allomas"]
COL_S = data["cols"]["statusz"]

# -----------------------------
# MÓDOSÍTÓ FUNKCIÓK
# -----------------------------
def update_status(row_idx, new_status):
    # Megkeressük a Státusz oszlop számát (A=1, B=2, C=3, D=4...)
    # A te leírásod alapján a Naplo-ban: Dátum(1), Állomás(2), Hiba(3), Státusz(4)
    sheet_naplo.update_cell(row_idx + 2, 4, new_status)
    st.cache_data.clear()
    st.rerun()

def delete_scheduling(allomas_nev):
    try:
        cells = sheet_vez.findall(allomas_nev)
        for cell in reversed(cells): # Hátulról töröljük, hogy ne csússzanak el az indexek
            sheet_vez.delete_rows(cell.row)
        st.cache_data.clear()
        st.rerun()
    except:
        pass

# -----------------------------
# UI - HIBALISTA
# -----------------------------
st.title("🛠️ Karbantartási vezénylő")

# Szűrés: csak a nyitott vagy visszamenős hibák
hibas_df = data['naplo'][data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni'])]

st.subheader(f"📝 Aktuális hibaállapotok ({len(hibas_df)} db)")

if not hibas_df.empty:
    header = st.columns([1.5, 2, 2.5, 2, 2.5])
    header[0].write("**Dátum**")
    header[1].write("**Állomás**")
    header[2].write("**Hiba leírása**")
    header[3].write("**Ütemezés**")
    header[4].write("**Műveletek**")
    st.divider()

    for idx, row in hibas_df.iterrows():
        c = st.columns([1.5, 2, 2.5, 2, 2.5])
        allomas_nev = row[COL_A]
        
        c[0].write(row['Dátum'])
        c[1].write(allomas_nev)
        
        # Hiba leírása megjelenítés
        if row[COL_S] == 'Visszamenni':
            c[2].warning(f"🔄 {row['Hiba leírása']}")
        else:
            c[2].write(row['Hiba leírása'])
        
        # Ütemezési adatok keresése a Vezenylesek lapról
        v_info = data['vez'][data['vez']['Allomas_Neve'] == allomas_nev]
        if not v_info.empty:
            v_last = v_info.iloc[-1]
            c[3].info(f"👤 {v_last['Technikus_Neve']}\n📅 {v_last['Datum']}")
        else:
            c[3].write("---")

        # Gombok
        b1, b2, b3 = c[4].columns(3)
        if b1.button("✅ Kész", key=f"k_{idx}"):
            update_status(idx, "Kész")
            delete_scheduling(allomas_nev)
        if b2.button("⚠️ Vissza", key=f"v_{idx}"):
            update_status(idx, "Visszamenni")
        if b3.button("🗑️ Töröl", key=f"t_{idx}"):
            delete_scheduling(allomas_nev)

# -----------------------------
# TÉRKÉP MEGJELENÍTÉSE
# -----------------------------
st.subheader("📍 Térképes nézet")

def get_marker_color(name):
    h = data['naplo'][data['naplo'][COL_A] == name]
    v = data['vez'][data['vez']['Allomas_Neve'] == name]
    
    if h.empty: return [200, 200, 200, 100]
    
    st_list = h[COL_S].tolist()
    is_vissza = "Visszamenni" in st_list
    is_nyitott = "Nyitott" in st_list
    is_utemezve = not v.empty

    if is_vissza and not is_nyitott: return [255, 255, 0] # Sárga
    if is_vissza and is_nyitott and not is_utemezve: return [139, 69, 19] # Barna
    if is_utemezve: return [0, 255, 0] # Zöld
    return [255, 0, 0] # Piros

map_data = data['allomasok'].copy()
map_data['hibak_szama'] = map_data['Nev'].apply(lambda x: len(data['naplo'][(data['naplo'][COL_A] == x) & (data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni']))]))
map_data = map_data[map_data['hibak_szama'] > 0]

if not map_data.empty:
    map_data['fill'] = map_data['Nev'].apply(get_marker_color)
    map_data['line'] = map_data['Tipus'].apply(lambda t: [0, 255, 0] if t=="MOL" else ([255, 0, 0] if t=="ORLEN" else [0, 191, 255]))

    st.pydeck_chart(pdk.Deck(
        map_style='mapbox://styles/mapbox/light-v10',
        initial_view_state=pdk.ViewState(latitude=47.1, longitude=19.5, zoom=7),
        layers=[
            pdk.Layer(
                "ScatterplotLayer", map_data, get_position="[Lon, Lat]",
                get_fill_color="fill", get_line_color="line",
                line_width_min_pixels=3, get_radius=6000, pickable=True
            ),
            pdk.Layer(
                "TextLayer", map_data, get_position="[Lon, Lat]",
                get_text="hibak_szama", get_size=20, get_color=[0, 0, 0]
            )
        ]
    ))

# -----------------------------
# VEZÉNYLÉS OLDALSÁV
# -----------------------------
st.sidebar.header("📋 Vezénylés rögzítése")
free_send = st.sidebar.checkbox("Nem aktív hiba küldés")
target_list = data['allomasok']['Nev'].tolist() if free_send else hibas_df[COL_A].unique().tolist()

with st.sidebar.form("v_form"):
    t_name = st.selectbox("Technikus", data['tech']['Név'].tolist() if not data['tech'].empty else [])
    a_name = st.selectbox("Helyszín", target_list)
    d_sel = st.date_input("Kivonulás napja")
    if st.form_submit_button("Vezénylés mentése"):
        sheet_vez.append_row([t_name, a_name, str(d_sel), "Ütemezve"])
        st.success("Vezénylés elmentve!")
        st.cache_data.clear()
        st.rerun()
