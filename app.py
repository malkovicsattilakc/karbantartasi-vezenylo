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

# Auth
try:
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
except Exception as e:
    st.error(f"Hiba a Google Sheets csatlakozásnál: {e}")
    st.stop()

# Munkalapok
sheet_naplo = sh.worksheet("Naplo")
sheet_vez = sh.worksheet("Vezenylesek")
sheet_allomasok = sh.worksheet("Allomasok")
sheet_tech = sh.worksheet("Technikusok")

@st.cache_data(ttl=2)
def load_all_data():
    def get_safe_df(sheet):
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        df.columns = [str(c).strip() for c in df.columns]
        return df

    return {
        "allomasok": get_safe_df(sheet_allomasok),
        "naplo": get_safe_df(sheet_naplo),
        "tech": get_safe_df(sheet_tech),
        "vez": get_safe_df(sheet_vez)
    }

data = load_all_data()

# Dinamikus oszlopkeresés (ha üres a tábla, alapértelmezett nevet adunk)
def get_col_name(df, target, default):
    return next((c for c in df.columns if target in c), default)

COL_A = get_col_name(data['naplo'], 'Állomás', "Állomás neve:")
COL_S = get_col_name(data['naplo'], 'Státusz', "Státusz")

# -----------------------------
# MENÜ
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
    
    # Hibaüzenet megelőzése: ellenőrizzük, hogy létezik-e az oszlop
    if COL_S in data['naplo'].columns:
        hibas_df = data['naplo'][data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni'])]
    else:
        hibas_df = pd.DataFrame()

    st.subheader(f"📝 Aktuális hibaállapotok ({len(hibas_df)} db)")

    if not hibas_df.empty:
        header = st.columns([1.5, 2, 2.5, 2, 3])
        header[0].write("**Dátum**"); header[1].write("**Állomás**"); header[2].write("**Hiba**"); header[3].write("**Ütemezés**"); header[4].write("**Műveletek**")
        st.divider()

        for idx, row in hibas_df.iterrows():
            c = st.columns([1.5, 2, 2.5, 2, 3])
            all_name = row[COL_A]
            c[0].write(row.get('Dátum', '---'))
            c[1].write(all_name)
            c[2].write(row.get('Hiba leírása', '---'))
            
            # ÜTEMEZÉS KERESÉSE (Biztonságos verzió)
            v_df = data['vez']
            is_scheduled = False
            if not v_df.empty and 'Allomas_Neve' in v_df.columns:
                v_info = v_df[v_df['Allomas_Neve'] == all_name]
                if not v_info.empty:
                    v_l = v_info.iloc[-1]
                    c[3].info(f"👤 {v_l.get('Technikus_Neve', 'N/A')}\n📅 {v_l.get('Datum', 'N/A')}")
                    is_scheduled = True
            
            if not is_scheduled:
                c[3].write("---")

            b_cols = c[4].columns(4)
            if b_cols[0].button("✅", key=f"k_{idx}"):
                sheet_naplo.update_cell(idx + 2, 4, "Kész"); st.rerun()
            if b_cols[1].button("🔄", key=f"v_{idx}"):
                sheet_naplo.update_cell(idx + 2, 4, "Visszamenni"); st.rerun()
            if is_scheduled and b_cols[2].button("📝", key=f"e_{idx}"):
                st.session_state.edit_allomas = all_name; st.rerun()
            if b_cols[3].button("🗑️", key=f"d_{idx}"):
                cells = sheet_vez.findall(all_name)
                for cell in reversed(cells): sheet_vez.delete_rows(cell.row)
                st.rerun()
    else:
        st.info("Nincs rögzített hiba a rendszerben.")

    # TÉRKÉP (Csak ha vannak állomások és koordináták)
    st.subheader("📍 Térkép")
    map_df = data['allomasok'].copy()
    if not map_df.empty and 'Lat' in map_df.columns:
        map_df['Lat'] = pd.to_numeric(map_df['Lat'], errors='coerce')
        map_df['Lon'] = pd.to_numeric(map_df['Lon'], errors='coerce')
        map_df = map_df.dropna(subset=['Lat', 'Lon'])
        
        # Hibaszámítás
        if not hibas_df.empty:
            map_df['hibak_szama'] = map_df['Nev'].apply(lambda x: len(hibas_df[hibas_df[COL_A] == x]))
        else:
            map_df['hibak_szama'] = 0
            
        plot_df = map_df[map_df['hibak_szama'] > 0].copy()

        if not plot_df.empty:
            st.pydeck_chart(pdk.Deck(
                map_style=None,
                initial_view_state=pdk.ViewState(latitude=plot_df['Lat'].mean(), longitude=plot_df['Lon'].mean(), zoom=7),
                layers=[
                    pdk.Layer("ScatterplotLayer", plot_df, get_position="[Lon, Lat]", get_fill_color=[255, 0, 0, 200], get_radius=6000),
                    pdk.Layer("TextLayer", plot_df, get_position="[Lon, Lat]", get_text="hibak_szama", get_size=25, get_color=[0, 0, 0])
                ]
            ))
        else:
            st.write("Nincs megjeleníthető hiba a térképen.")

# -----------------------------
# 2. VEZÉNYLÉS / HIBA / ÁLLOMÁS (Hasonlóan védett formák)
# -----------------------------
elif current_menu == "Vezénylés":
    editing = st.session_state.edit_allomas
    st.title("📋 " + ("Módosítás" if editing else "Vezénylés"))
    
    with st.form("vez_form"):
        tech_list = data['tech']['Név'].tolist() if not data['tech'].empty else ["Nincs technikus"]
        all_list = data['allomasok']['Nev'].tolist() if not data['allomasok'].empty else ["Nincs állomás"]
        
        tech = st.selectbox("Technikus", tech_list)
        hely = st.selectbox("Helyszín", all_list, index=all_list.index(editing) if editing in all_list else 0)
        datum = st.date_input("Dátum", date.today())
        if st.form_submit_button("Mentés"):
            if editing:
                cells = sheet_vez.findall(editing)
                for cell in reversed(cells): sheet_vez.delete_rows(cell.row)
            sheet_vez.append_row([tech, hely, str(datum), "Aktív"])
            st.session_state.edit_allomas = None
            st.success("Mentve!"); st.rerun()

elif menu == "Hiba rögzítése":
    st.title("🐞 Hiba bejelentése")
    with st.form("h_form"):
        allomasok = data['allomasok']['Nev'].tolist() if not data['allomasok'].empty else []
        val = st.selectbox("Állomás", allomasok)
        desc = st.text_area("Hiba leírása")
        if st.form_submit_button("Mentés"):
            sheet_naplo.append_row([str(date.today()), val, desc, "Nyitott"])
            st.success("Rögzítve!")

elif menu == "Új állomás felvitele":
    st.title("➕ Új állomás")
    with st.form("a_form"):
        n = st.text_input("Név"); t = st.selectbox("Típus", ["MOL", "ORLEN", "Egyéb"])
        la = st.text_input("Lat"); lo = st.text_input("Lon")
        if st.form_submit_button("Mentés"):
            sheet_allomasok.append_row([len(data['allomasok'])+1, n, t, la, lo])
            st.success("Hozzáadva!")
