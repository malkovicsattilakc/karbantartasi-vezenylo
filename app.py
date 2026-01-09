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
    naplo_df = pd.DataFrame(sheet_naplo.get_all_records())
    naplo_df.columns = [str(c).strip() for c in naplo_df.columns]
    
    allomas_df = pd.DataFrame(sheet_allomasok.get_all_records())
    allomas_df.columns = [str(c).strip() for c in allomas_df.columns]
    
    # Automatikus oszlopkeresés
    allomas_col = next((c for c in naplo_df.columns if 'Állomás' in c), "Állomás neve:")
    statusz_col = next((c for c in naplo_df.columns if 'Státusz' in c), "Státusz")
    
    return {
        "allomasok": allomas_df,
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
    # Keressük meg a Státusz oszlop indexét (4. oszlop a te leírásod alapján)
    sheet_naplo.update_cell(row_idx + 2, 4, new_status)
    st.cache_data.clear()
    st.rerun()

def delete_scheduling(allomas_nev):
    try:
        cells = sheet_vez.findall(allomas_nev)
        for cell in reversed(cells):
            sheet_vez.delete_rows(cell.row)
        st.cache_data.clear()
        st.rerun()
    except:
        pass

# -----------------------------
# UI - HIBALISTA
# -----------------------------
st.title("🛠️ Karbantartási vezénylő")

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
        
        status = row[COL_S]
        desc = row['Hiba leírása']
        if status == 'Visszamenni':
            c[2].warning(f"🔄 {desc}")
        else:
            c[2].write(desc)
        
        v_info = data['vez'][data['vez']['Allomas_Neve'] == allomas_nev]
        if not v_info.empty:
            v_last = v_info.iloc[-1]
            c[3].info(f"👤 {v_last['Technikus_Neve']}\n📅 {v_last['Datum']}")
        else:
            c[3].write("---")

        b1, b2, b3 = c[4].columns(3)
        if b1.button("✅ Kész", key=f"k_{idx}"):
            update_status(idx, "Kész")
            delete_scheduling(allomas_nev)
        if b2.button("🔄 Vissza", key=f"v_{idx}"):
            update_status(idx, "Visszamenni")
        if b3.button("🗑️ Töröl", key=f"t_{idx}"):
            delete_scheduling(allomas_nev)

# -----------------------------
# TÉRKÉP MEGJELENÍTÉSE
# -----------------------------
st.subheader("📍 Térképes nézet")

def get_fill_color(name):
    h = data['naplo'][data['naplo'][COL_A] == name]
    v = data['vez'][data['vez']['Allomas_Neve'] == name]
    if h.empty: return [200, 200, 200, 100]
    st_list = h[COL_S].tolist()
    if "Visszamenni" in st_list and "Nyitott" not in st_list: return [255, 255, 0]
    if "Visszamenni" in st_list and "Nyitott" in st_list and v.empty: return [139, 69, 19]
    if not v.empty: return [0, 255, 0]
    return [255, 0, 0]

map_data = data['allomasok'].copy()
# Számszerűsítjük a koordinátákat
map_data['Lat'] = pd.to_numeric(map_data['Lat'], errors='coerce')
map_data['Lon'] = pd.to_numeric(map_data['Lon'], errors='coerce')
map_data = map_data.dropna(subset=['Lat', 'Lon'])

map_data['hibak_szama'] = map_data['Nev'].apply(lambda x: len(data['naplo'][(data['naplo'][COL_A] == x) & (data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni']))]))
map_plot = map_data[map_data['hibak_szama'] > 0].copy()

if not map_plot.empty:
    map_plot['fill'] = map_plot['Nev'].apply(get_fill_color)
    map_plot['line'] = map_plot['Tipus'].apply(lambda t: [0, 255, 0] if t=="MOL" else ([255, 0, 0] if t=="ORLEN" else [0, 191, 255]))

    # Térkép középpontjának kiszámítása az adatok alapján
    mid_lat = map_plot['Lat'].mean()
    mid_lon = map_plot['Lon'].mean()

    st.pydeck_chart(pdk.Deck(
        map_style='mapbox://styles/mapbox/light-v10',
        initial_view_state=pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=7),
        layers=[
            pdk.Layer(
                "ScatterplotLayer", map_plot, get_position="[Lon, Lat]",
                get_fill_color="fill", get_line_color="line",
                line_width_min_pixels=3, get_radius=5000, pickable=True
            ),
            pdk.Layer(
                "TextLayer", map_plot, get_position="[Lon, Lat]",
                get_text="hibak_szama", get_size=20, get_color=[0, 0, 0],
                get_alignment_baseline="'center'"
            )
        ]
    ))
else:
    st.info("Jelenleg nincs megjeleníthető hiba a térképen.")

# -----------------------------
# VEZÉNYLÉS OLDALSÁV
# -----------------------------
st.sidebar.header("📋 Vezénylés rögzítése")
free_send = st.sidebar.checkbox("Nem aktív hiba küldés")
target_list = data['allomasok']['Nev'].tolist() if free_send else hibas_df[COL_A].unique().tolist()

with st.sidebar.form("v_form"):
    t_name = st.selectbox("Technikus", data['tech']['Név'].tolist() if not data['tech'].empty else [])
    a_name = st.selectbox("Helyszín", target_list)
    d_sel = st.date_input("Kivonulás napja", date.today())
    if st.form_submit_button("Vezénylés mentése"):
        sheet_vez.append_row([t_name, a_name, str(d_sel), "Ütemezve"])
        st.success("Vezénylés elmentve!")
        st.cache_data.clear()
        st.rerun()
