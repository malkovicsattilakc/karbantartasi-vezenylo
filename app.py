import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import pydeck as pdk
from datetime import datetime, date, time

# -----------------------------
# KONFIGURÁCIÓ ÉS CSATLAKOZÁS
# -----------------------------
SPREADSHEET_ID = "1-kng7w3h8Us6Xr93Nk1kJ8zwuSocCadqJvyxpb7mhas"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

st.set_page_config(page_title="Karbantartási vezénylő", layout="wide")

# Google Auth
if "gcp_service_account" not in st.secrets:
    st.error("Hiányzik a 'gcp_service_account' konfiguráció!")
    st.stop()

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
    naplo_df = pd.DataFrame(sheet_naplo.get_all_records())
    naplo_df.columns = [str(c).strip() for c in naplo_df.columns]
    allomas_df = pd.DataFrame(sheet_allomasok.get_all_records())
    allomas_df.columns = [str(c).strip() for c in allomas_df.columns]
    
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
# MENÜ (Visszahozva minden funkció)
# -----------------------------
menu = st.sidebar.radio("Menü", ["Műszerfal & Térkép", "Hiba rögzítése", "Vezénylés", "Új állomás felvitele"])

# -----------------------------
# 1. MŰSZERFAL & TÉRKÉP (A régi jó térképpel)
# -----------------------------
if menu == "Műszerfal & Térkép":
    st.title("🛠️ Karbantartási vezénylő")
    
    # Hibalista megjelenítése felül
    hibas_df = data['naplo'][data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni'])]
    st.subheader(f"📝 Aktuális hibaállapotok ({len(hibas_df)} db)")

    if not hibas_df.empty:
        header = st.columns([1.5, 2, 2.5, 2, 2.5])
        header[0].write("**Dátum**"); header[1].write("**Állomás**"); header[2].write("**Hiba**"); header[3].write("**Ütemezés**"); header[4].write("**Műveletek**")
        st.divider()

        for idx, row in hibas_df.iterrows():
            c = st.columns([1.5, 2, 2.5, 2, 2.5])
            all_name = row[COL_A]
            c[0].write(row['Dátum'])
            c[1].write(all_name)
            c[2].write(row['Hiba leírása'])
            
            # Ütemezési infó (Vezénylések lapról)
            v_info = data['vez'][data['vez']['Allomas_Neve'] == all_name]
            if not v_info.empty:
                v_l = v_info.iloc[-1]
                c[3].info(f"👤 {v_l['Technikus_Neve']}\n📅 {v_l['Datum']}")
            else:
                c[3].write("---")

            b_cols = c[4].columns(3)
            if b_cols[0].button("✅", key=f"k_{idx}"):
                sheet_naplo.update_cell(idx + 2, 4, "Kész")
                st.cache_data.clear()
                st.rerun()
            if b_cols[1].button("🔄", key=f"v_{idx}"):
                sheet_naplo.update_cell(idx + 2, 4, "Visszamenni")
                st.cache_data.clear()
                st.rerun()

    # TÉRKÉP (Visszaállítva a kezdeti jó verzióra)
    st.subheader("📍 Állomások térképen")
    map_df = data['allomasok'].copy()
    map_df['Lat'] = pd.to_numeric(map_df['Lat'], errors='coerce')
    map_df['Lon'] = pd.to_numeric(map_df['Lon'], errors='coerce')
    map_df = map_df.dropna(subset=['Lat', 'Lon'])

    if not map_df.empty:
        # Meghatározzuk a színeket és hibaszámokat
        map_df['hibak_szama'] = map_df['Nev'].apply(lambda x: len(data['naplo'][(data['naplo'][COL_A] == x) & (data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni']))]))
        
        def get_map_colors(r):
            h = data['naplo'][data['naplo'][COL_A] == r['Nev']]
            v = data['vez'][data['vez']['Allomas_Neve'] == r['Nev']]
            
            # Belső szín (Státusz alapú)
            if not v.empty: fill = [0, 255, 0, 160] # Zöld (Ütemezve)
            elif "Visszamenni" in h[COL_S].values: fill = [255, 255, 0, 160] # Sárga
            elif not h.empty: fill = [255, 0, 0, 160] # Piros (Nyitott hiba)
            else: fill = [200, 200, 200, 50] # Szürke (Nincs hiba)
            
            # Keretszín (Márka alapú)
            if r['Tipus'] == "MOL": line = [0, 255, 0]
            elif r['Tipus'] == "ORLEN": line = [255, 0, 0]
            else: line = [0, 191, 255]
            
            return pd.Series([fill, line])

        map_df[['f_color', 'l_color']] = map_df.apply(get_map_colors, axis=1)

        st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/dark-v10',
            initial_view_state=pdk.ViewState(latitude=map_df['Lat'].mean(), longitude=map_df['Lon'].mean(), zoom=7),
            layers=[
                pdk.Layer(
                    "ScatterplotLayer", map_df, get_position="[Lon, Lat]",
                    get_fill_color="f_color", get_line_color="l_color",
                    line_width_min_pixels=3, get_radius=5000, pickable=True
                ),
                pdk.Layer(
                    "TextLayer", map_df[map_df['hibak_szama'] > 0], get_position="[Lon, Lat]",
                    get_text="hibak_szama", get_size=20, get_color=[255, 255, 255]
                )
            ]
        ))

# -----------------------------
# 2. HIBA RÖGZÍTÉSE
# -----------------------------
elif menu == "Hiba rögzítése":
    st.title("🐞 Új hiba bejelentése")
    with st.form("hiba_form"):
        # Cím kiválasztása márka megjelenítésével
        options = {f"{r['Nev']} ({r['Tipus']})": r['Nev'] for _, r in data['allomasok'].iterrows()}
        valasztott_cim = st.selectbox("Állomás kiválasztása", list(options.keys()))
        hiba_leiras = st.text_area("Hiba leírása")
        
        col1, col2 = st.columns(2)
        h_datum = col1.date_input("Határidő nap", date.today())
        h_ido = col2.time_input("Pontos idő", time(12, 0))
        
        if st.form_submit_button("Hiba mentése"):
            sheet_naplo.append_row([
                str(date.today()), 
                options[valasztott_cim], 
                f"{hiba_leiras} | HATÁRIDŐ: {h_datum} {h_ido.strftime('%H:%M')}", 
                "Nyitott", ""
            ])
            st.success("Hiba rögzítve a naplóba!")
            st.cache_data.clear()

# -----------------------------
# 3. VEZÉNYLÉS (Szűrt lista megoldva)
# -----------------------------
elif menu == "Vezénylés":
    st.title("📋 Technikus kirendelése")
    
    # Csak hibahelyszínekre küldés szűrő az oldalsávon vagy itt
    free_send = st.checkbox("Nem aktív hiba küldés (Összes állomás mutatása)")
    
    hibas_helyszinek = data['naplo'][data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni'])][COL_A].unique().tolist()
    osszes_helyszin = data['allomasok']['Nev'].tolist()
    
    valaszthato_cimek = osszes_helyszin if free_send else hibas_helyszinek

    if not valaszthato_cimek and not free_send:
        st.warning("Jelenleg nincs nyitott hiba. Pipáld be a fenti gombot az összes állomás listázásához.")
    else:
        with st.form("vez_form"):
            tech = st.selectbox("Technikus", data['tech']['Név'].tolist())
            hely = st.selectbox("Célállomás", valaszthato_cimek)
            mikor = st.date_input("Kivonulás napja", date.today())
            feladat = st.text_area("Munka leírása")
            
            if st.form_submit_button("Vezénylés rögzítése"):
                sheet_vez.append_row([tech, hely, str(mikor), feladat])
                st.success(f"{tech} kirendelve: {hely}")
                st.cache_data.clear()

# -----------------------------
# 4. ÚJ ÁLLOMÁS FELVITELE
# -----------------------------
elif menu == "Új állomás felvitele":
    st.title("➕ Új állomás rögzítése")
    with st.form("uj_all_form"):
        nev = st.text_input("Állomás neve")
        tipus = st.selectbox("Típus", ["MOL", "ORLEN", "Egyéb"])
        lat = st.text_input("Szélesség (Lat) - pl: 47.123")
        lon = st.text_input("Hosszúság (Lon) - pl: 19.123")
        
        if st.form_submit_button("Állomás mentése"):
            if nev and lat and lon:
                sheet_allomasok.append_row([len(data['allomasok'])+1, nev, tipus, lat, lon])
                st.success(f"'{nev}' sikeresen hozzáadva!")
                st.cache_data.clear()
            else:
                st.error("Kérlek tölts ki minden mezőt!")
