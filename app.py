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

# Google Auth biztonságos kezelése
try:
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
except Exception as e:
    st.error(f"Csatlakozási hiba: {e}")
    st.stop()

# Munkalapok elérése
sheet_naplo = sh.worksheet("Naplo")
sheet_vez = sh.worksheet("Vezenylesek")
sheet_allomasok = sh.worksheet("Allomasok")
sheet_tech = sh.worksheet("Technikusok")

@st.cache_data(ttl=2)
def load_all_data():
    def get_df(s):
        df = pd.DataFrame(s.get_all_records())
        df.columns = [str(c).strip() for c in df.columns]
        return df
    return {
        "allomasok": get_df(sheet_allomasok),
        "naplo": get_df(sheet_naplo),
        "tech": get_df(sheet_tech),
        "vez": get_df(sheet_vez)
    }

data = load_all_data()

# Oszlopnevek dinamikus keresése a hibák elkerülésére
def find_col(df, key, default):
    return next((c for c in df.columns if key in c), default)

COL_A = find_col(data['naplo'], 'Állomás', "Állomás neve:")
COL_S = find_col(data['naplo'], 'Státusz', "Státusz")

# -----------------------------
# MENÜ ÉS ÁLLAPOTKEZELÉS
# -----------------------------
if 'edit_allomas' not in st.session_state:
    st.session_state.edit_allomas = None

menu = st.sidebar.radio("Menü", ["Műszerfal & Térkép", "Hiba rögzítése", "Vezénylés", "Új állomás felvitele"])
current_menu = "Vezénylés" if st.session_state.edit_allomas else menu

# -----------------------------
# 1. MŰSZERFAL & TÉRKÉP
# -----------------------------
if current_menu == "Műszerfal & Térkép":
    st.title("🛠️ Karbantartási vezénylő")
    
    # Csak a nyitott és visszamenős hibák
    hibas_df = data['naplo'][data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni'])] if COL_S in data['naplo'].columns else pd.DataFrame()
    st.subheader(f"📝 Aktuális hibaállapotok ({len(hibas_df)} db)")

    if not hibas_df.empty:
        header = st.columns([1.5, 2, 2.5, 2, 3.5])
        header[0].write("**Dátum**"); header[1].write("**Állomás**"); header[2].write("**Hiba**"); header[3].write("**Ütemezés**"); header[4].write("**Műveletek**")
        st.divider()

        for idx, row in hibas_df.iterrows():
            c = st.columns([1.5, 2, 2.5, 2, 3.5])
            all_name = row[COL_A]
            c[0].write(row.get('Dátum', '---'))
            c[1].write(all_name)
            c[2].write(row.get('Hiba leírása', '---'))
            
            # Ütemezési adatok kinyerése
            v_info = data['vez'][data['vez']['Allomas_Neve'] == all_name] if not data['vez'].empty else pd.DataFrame()
            is_scheduled = not v_info.empty
            
            if is_scheduled:
                last_v = v_info.iloc[-1]
                c[3].info(f"👤 {last_v.get('Technikus_Neve', 'N/A')}\n📅 {last_v.get('Datum', 'N/A')}")
            else:
                c[3].write("---")

            # MŰVELETEK GOMBOK
            b = c[4].columns(4)
            if b[0].button("✅", key=f"k_{idx}", help="Készre jelentés"):
                sheet_naplo.update_cell(idx + 2, 4, "Kész"); st.rerun()
            if b[1].button("🔄", key=f"v_{idx}", help="Visszamenni szükséges"):
                sheet_naplo.update_cell(idx + 2, 4, "Visszamenni"); st.rerun()
            if is_scheduled and b[2].button("📝", key=f"e_{idx}", help="Ütemezés módosítása"):
                st.session_state.edit_allomas = all_name; st.rerun()
            
            # TÖRLÉS GOMB (Eltávolítás a Naplóból és a Vezénylésből is)
            if b[3].button("🗑️", key=f"del_{idx}", help="Hiba végleges törlése"):
                # 1. Törlés a Napló lapról
                sheet_naplo.delete_rows(idx + 2)
                # 2. Törlés a Vezénylés lapról (ha van)
                cells = sheet_vez.findall(all_name)
                for cell in reversed(cells): sheet_vez.delete_rows(cell.row)
                st.success(f"{all_name} törölve.")
                st.rerun()
    else:
        st.info("Nincs aktív hiba a listában.")

    # TÉRKÉP MEGJELENÍTÉSE
    st.subheader("📍 Térképes nézet")
    map_df = data['allomasok'].copy()
    if not map_df.empty and 'Lat' in map_df.columns:
        map_df['Lat'] = pd.to_numeric(map_df['Lat'], errors='coerce')
        map_df['Lon'] = pd.to_numeric(map_df['Lon'], errors='coerce')
        map_df = map_df.dropna(subset=['Lat', 'Lon'])
        
        # Aktív hibák száma állomásonként
        map_df['hibak_szama'] = map_df['Nev'].apply(lambda x: len(hibas_df[hibas_df[COL_A] == x]) if not hibas_df.empty else 0)
        plot_df = map_df[map_df['hibak_szama'] > 0].copy()

        if not plot_df.empty:
            st.pydeck_chart(pdk.Deck(
                map_style='mapbox://styles/mapbox/light-v9', # Világos stílus a jobb láthatóságért
                initial_view_state=pdk.ViewState(latitude=plot_df['Lat'].mean(), longitude=plot_df['Lon'].mean(), zoom=7),
                layers=[
                    pdk.Layer("ScatterplotLayer", plot_df, get_position="[Lon, Lat]", get_fill_color=[255, 0, 0, 180], get_radius=6000, pickable=True),
                    pdk.Layer("TextLayer", plot_df, get_position="[Lon, Lat]", get_text="hibak_szama", get_size=24, get_color=[0, 0, 0], get_alignment_baseline="'center'")
                ]
            ))
        else:
            st.write("Nincs megjeleníthető hiba a térképen.")

# -----------------------------
# 2. HIBA RÖGZÍTÉSE (DÁTUMVÁLASZTÓVAL)
# -----------------------------
elif current_menu == "Hiba rögzítése":
    st.title("🐞 Új hiba bejelentése")
    with st.form("h_form"):
        all_names = data['allomasok']['Nev'].tolist() if not data['allomasok'].empty else []
        val_allomas = st.selectbox("Állomás kiválasztása", all_names)
        val_leiras = st.text_area("Hiba leírása")
        
        # DÁTUMVÁLASZTÓ JAVÍTÁSA
        val_datum = st.date_input("Hiba észlelésének dátuma", date.today())
        
        if st.form_submit_button("Hiba mentése"):
            if val_allomas and val_leiras:
                sheet_naplo.append_row([str(val_datum), val_allomas, val_leiras, "Nyitott", ""])
                st.success(f"Hiba rögzítve ({val_datum})!")
                st.cache_data.clear()
            else:
                st.error("Minden mezőt tölts ki!")

# -----------------------------
# 3. VEZÉNYLÉS / MÓDOSÍTÁS
# -----------------------------
elif current_menu == "Vezénylés":
    editing = st.session_state.edit_allomas
    st.title("📋 " + ("Ütemezés módosítása" if editing else "Technikus kirendelése"))
    
    with st.form("v_form"):
        t_list = data['tech']['Név'].tolist() if not data['tech'].empty else ["Nincs technikus"]
        a_list = data['allomasok']['Nev'].tolist() if not data['allomasok'].empty else ["Nincs állomás"]
        
        tech = st.selectbox("Technikus", t_list)
        hely = st.selectbox("Helyszín", a_list, index=a_list.index(editing) if editing in a_list else 0)
        mikor = st.date_input("Kivonulás dátuma", date.today())
        leiras = st.text_area("Feladat részletei", "Módosított ütemezés" if editing else "")
        
        if st.form_submit_button("Vezénylés mentése"):
            if editing: # Régi törlése
                cells = sheet_vez.findall(editing)
                for cell in reversed(cells): sheet_vez.delete_rows(cell.row)
            
            sheet_vez.append_row([tech, hely, str(mikor), leiras])
            st.session_state.edit_allomas = None
            st.success("Sikeres mentés!")
            st.rerun()
            
    if editing and st.button("Mégse"):
        st.session_state.edit_allomas = None
        st.rerun()

# -----------------------------
# 4. ÚJ ÁLLOMÁS
# -----------------------------
elif current_menu == "Új állomás felvitele":
    st.title("➕ Új állomás rögzítése")
    with st.form("a_form"):
        n = st.text_input("Állomás neve")
        t = st.selectbox("Márka/Típus", ["MOL", "ORLEN", "Egyéb"])
        la = st.text_input("Lat (Szélesség)")
        lo = st.text_input("Lon (Hosszúság)")
        if st.form_submit_button("Állomás mentése"):
            sheet_allomasok.append_row([len(data['allomasok'])+1, n, t, la, lo])
            st.success(f"{n} hozzáadva a rendszerhez.")
            st.cache_data.clear()
