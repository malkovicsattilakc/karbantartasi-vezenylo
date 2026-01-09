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
# OLDALSÁV MENÜ
# -----------------------------
menu = st.sidebar.radio("Funkció választása", ["Műszerfal & Térkép", "Hiba rögzítése", "Vezénylés", "Új állomás felvitele"])

# -----------------------------
# 1. MŰSZERFAL & TÉRKÉP
# -----------------------------
if menu == "Műszerfal & Térkép":
    st.title("🛠️ Karbantartási vezénylő")
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
            c[2].write(f"⚠️ {row['Hiba leírása']}" if row[COL_S] == 'Visszamenni' else row['Hiba leírása'])
            
            v_info = data['vez'][data['vez']['Allomas_Neve'] == all_name]
            if not v_info.empty:
                v_l = v_info.iloc[-1]
                c[3].info(f"👤 {v_l['Technikus_Neve']}\n📅 {v_l['Datum']}")
            else: c[3].write("---")

            b1, b2, b3 = c[4].columns(3)
            if b1.button("✅", key=f"k_{idx}"): 
                sheet_naplo.update_cell(idx + 2, 4, "Kész")
                st.rerun()
            if b2.button("🔄", key=f"v_{idx}"):
                sheet_naplo.update_cell(idx + 2, 4, "Visszamenni")
                st.rerun()

    st.subheader("📍 Térkép")
    map_df = data['allomasok'].copy()
    map_df['Lat'] = pd.to_numeric(map_df['Lat'], errors='coerce')
    map_df['Lon'] = pd.to_numeric(map_df['Lon'], errors='coerce')
    map_df = map_df.dropna(subset=['Lat', 'Lon'])
    
    # Csak ott rajzolunk kört, ahol van hiba
    map_df['hibak_szama'] = map_df['Nev'].apply(lambda x: len(data['naplo'][(data['naplo'][COL_A] == x) & (data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni']))]))
    plot_df = map_df[map_df['hibak_szama'] > 0].copy()

    if not plot_df.empty:
        # Színlogika
        def get_colors(name, tipus):
            h = data['naplo'][data['naplo'][COL_A] == name]
            v = data['vez'][data['vez']['Allomas_Neve'] == name]
            fill = [255, 0, 0] # Alap piros
            if not v.empty: fill = [0, 255, 0] # Zöld ha ütemezve
            elif "Visszamenni" in h[COL_S].values: fill = [255, 255, 0] # Sárga
            
            line = [0, 255, 0] if tipus == "MOL" else ([255, 0, 0] if tipus == "ORLEN" else [0, 191, 255])
            return pd.Series([fill, line])

        plot_df[['f_col', 'l_col']] = plot_df.apply(lambda r: get_colors(r['Nev'], r['Tipus']), axis=1)

        st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/dark-v10', # Sötét téma a jobb láthatóságért
            initial_view_state=pdk.ViewState(latitude=plot_df['Lat'].mean(), longitude=plot_df['Lon'].mean(), zoom=7),
            layers=[
                pdk.Layer("ScatterplotLayer", plot_df, get_position="[Lon, Lat]", get_fill_color="f_col", get_line_color="l_col", line_width_min_pixels=3, get_radius=5000, pickable=True),
                pdk.Layer("TextLayer", plot_df, get_position="[Lon, Lat]", get_text="hibak_szama", get_size=20, get_color=[255, 255, 255])
            ]
        ))

# -----------------------------
# 2. HIBA RÖGZÍTÉSE
# -----------------------------
elif menu == "Hiba rögzítése":
    st.title("🐞 Új hiba bejelentése")
    with st.form("hiba_form"):
        allomas = st.selectbox("Állomás kiválasztása", data['allomasok']['Nev'].tolist())
        leiras = st.text_area("Hiba pontos leírása")
        col1, col2 = st.columns(2)
        d = col1.date_input("Határidő nap", date.today())
        t = col2.time_input("Határidő idő", time(12, 0))
        if st.form_submit_button("Hiba mentése"):
            sheet_naplo.append_row([str(date.today()), allomas, f"{leiras} | HATÁRIDŐ: {d} {t}", "Nyitott", ""])
            st.success("Hiba rögzítve!")
            st.cache_data.clear()

# -----------------------------
# 3. VEZÉNYLÉS
# -----------------------------
elif menu == "Vezénylés":
    st.title("📋 Technikus kirendelése")
    with st.form("vez_form"):
        t_name = st.selectbox("Technikus", data['tech']['Név'].tolist())
        a_name = st.selectbox("Helyszín", data['allomasok']['Nev'].tolist())
        v_date = st.date_input("Kivonulás dátuma")
        if st.form_submit_button("Vezénylés mentése"):
            sheet_vez.append_row([t_name, a_name, str(v_date), "Aktív"])
            st.success("Sikeres vezénylés!")
            st.cache_data.clear()

# -----------------------------
# 4. ÚJ ÁLLOMÁS FELVITELE
# -----------------------------
elif menu == "Új állomás felvitele":
    st.title("➕ Új állomás rögzítése")
    with st.form("uj_allomas"):
        n = st.text_input("Állomás neve")
        t = st.selectbox("Típus", ["MOL", "ORLEN", "Egyéb"])
        la = st.text_input("Lat (pl. 47.123)")
        lo = st.text_input("Lon (pl. 19.123)")
        if st.form_submit_button("Állomás mentése"):
            sheet_allomasok.append_row([len(data['allomasok'])+1, n, t, la, lo])
            st.success("Új állomás hozzáadva!")
            st.cache_data.clear()
