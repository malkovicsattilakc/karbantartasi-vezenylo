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

creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SPREADSHEET_ID)

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
# SZERKESZTÉS ÁLLAPOT KEZELÉSE
# -----------------------------
if 'edit_allomas' not in st.session_state:
    st.session_state.edit_allomas = None

# -----------------------------
# MENÜ
# -----------------------------
menu = st.sidebar.radio("Menü", ["Műszerfal & Térkép", "Hiba rögzítése", "Vezénylés", "Új állomás felvitele"])

# Ha szerkesztés módban vagyunk, kényszerítsük a Vezénylés menüt
current_menu = "Vezénylés" if st.session_state.edit_allomas else menu

# -----------------------------
# 1. MŰSZERFAL & TÉRKÉP
# -----------------------------
if current_menu == "Műszerfal & Térkép":
    st.title("🛠️ Karbantartási vezénylő")
    
    hibas_df = data['naplo'][data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni'])]
    st.subheader(f"📝 Aktuális hibaállapotok ({len(hibas_df)} db)")

    if not hibas_df.empty:
        header = st.columns([1.5, 2, 2.5, 2, 3])
        header[0].write("**Dátum**"); header[1].write("**Állomás**"); header[2].write("**Hiba**"); header[3].write("**Ütemezés**"); header[4].write("**Műveletek**")
        st.divider()

        for idx, row in hibas_df.iterrows():
            c = st.columns([1.5, 2, 2.5, 2, 3])
            all_name = row[COL_A]
            c[0].write(row['Dátum'])
            c[1].write(all_name)
            c[2].write(row['Hiba leírása'])
            
            v_info = data['vez'][data['vez']['Allomas_Neve'] == all_name]
            is_scheduled = not v_info.empty
            
            if is_scheduled:
                v_l = v_info.iloc[-1]
                c[3].info(f"👤 {v_l['Technikus_Neve']}\n📅 {v_l['Datum']}")
            else:
                c[3].write("---")

            b_cols = c[4].columns(4)
            if b_cols[0].button("✅", key=f"k_{idx}", help="Kész"):
                sheet_naplo.update_cell(idx + 2, 4, "Kész")
                st.rerun()
            if b_cols[1].button("🔄", key=f"v_{idx}", help="Visszamenni"):
                sheet_naplo.update_cell(idx + 2, 4, "Visszamenni")
                st.rerun()
            
            # SZERKESZTÉS GOMB (Módosítás)
            if is_scheduled:
                if b_cols[2].button("📝", key=f"edit_{idx}", help="Ütemezés módosítása"):
                    st.session_state.edit_allomas = all_name
                    st.rerun()
            
            if b_cols[3].button("🗑️", key=f"del_{idx}", help="Ütemezés törlése"):
                cells = sheet_vez.findall(all_name)
                for cell in reversed(cells): sheet_vez.delete_rows(cell.row)
                st.rerun()

    # TÉRKÉP JAVÍTÁSA (STABIL STÍLUS)
    st.subheader("📍 Térkép (Csak aktív hibák)")
    map_df = data['allomasok'].copy()
    map_df['Lat'] = pd.to_numeric(map_df['Lat'], errors='coerce')
    map_df['Lon'] = pd.to_numeric(map_df['Lon'], errors='coerce')
    map_df = map_df.dropna(subset=['Lat', 'Lon'])

    map_df['hibak_szama'] = map_df['Nev'].apply(lambda x: len(data['naplo'][(data['naplo'][COL_A] == x) & (data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni']))]))
    plot_df = map_df[map_df['hibak_szama'] > 0].copy()

    if not plot_df.empty:
        def get_colors(r):
            h = data['naplo'][data['naplo'][COL_A] == r['Nev']]
            v = data['vez'][data['vez']['Allomas_Neve'] == r['Nev']]
            if not v.empty: f = [0, 255, 0, 200]
            elif "Visszamenni" in h[COL_S].values: f = [255, 255, 0, 200]
            else: f = [255, 0, 0, 200]
            l = [0, 255, 0] if r['Tipus'] == "MOL" else ([255, 0, 0] if r['Tipus'] == "ORLEN" else [0, 191, 255])
            return pd.Series([f, l])

        plot_df[['f_c', 'l_c']] = plot_df.apply(get_colors, axis=1)

        st.pydeck_chart(pdk.Deck(
            map_style=None, # Ez a gyári Mapbox-ot kikapcsolja és egy alap, de látható térképet ad
            initial_view_state=pdk.ViewState(latitude=plot_df['Lat'].mean(), longitude=plot_df['Lon'].mean(), zoom=7),
            layers=[
                pdk.Layer("ScatterplotLayer", plot_df, get_position="[Lon, Lat]", get_fill_color="f_c", get_line_color="l_c", line_width_min_pixels=3, get_radius=6000, pickable=True),
                pdk.Layer("TextLayer", plot_df, get_position="[Lon, Lat]", get_text="hibak_szama", get_size=25, get_color=[0, 0, 0], get_alignment_baseline="'center'")
            ]
        ))

# -----------------------------
# 2. VEZÉNYLÉS / MÓDOSÍTÁS
# -----------------------------
elif current_menu == "Vezénylés":
    editing = st.session_state.edit_allomas
    st.title("📋 " + ("Ütemezés módosítása" if editing else "Technikus kirendelése"))
    
    if editing:
        st.warning(f"Szerkesztés alatt: {editing}")

    with st.form("vez_form"):
        all_list = data['allomasok']['Nev'].tolist()
        # Ha szerkesztünk, alapból az adott állomás legyen kiválasztva
        def_idx = all_list.index(editing) if editing in all_list else 0
        
        tech = st.selectbox("Technikus", data['tech']['Név'].tolist())
        hely = st.selectbox("Helyszín", all_list, index=def_idx)
        datum = st.date_input("Kivonulás napja", date.today())
        leiras = st.text_area("Feladat leírása", "Módosított ütemezés" if editing else "")
        
        if st.form_submit_button("Mentés"):
            if editing: # Ha módosítunk, a régit töröljük először
                cells = sheet_vez.findall(editing)
                for cell in reversed(cells): sheet_vez.delete_rows(cell.row)
            
            sheet_vez.append_row([tech, hely, str(datum), leiras])
            st.session_state.edit_allomas = None # Szerkesztés vége
            st.success("Sikeres mentés!")
            st.rerun()
            
    if editing:
        if st.button("Mégse"):
            st.session_state.edit_allomas = None
            st.rerun()

# -----------------------------
# 3. HIBA RÖGZÍTÉSE
# -----------------------------
elif current_menu == "Hiba rögzítése":
    st.title("🐞 Új hiba bejelentése")
    with st.form("h_form"):
        opts = {f"{r['Nev']} ({r['Tipus']})": r['Nev'] for _, r in data['allomasok'].iterrows()}
        val = st.selectbox("Állomás", list(opts.keys()))
        desc = st.text_area("Hiba leírása")
        if st.form_submit_button("Hiba mentése"):
            sheet_naplo.append_row([str(date.today()), opts[val], desc, "Nyitott", ""])
            st.success("Rögzítve!")

# -----------------------------
# 4. ÚJ ÁLLOMÁS
# -----------------------------
elif current_menu == "Új állomás felvitele":
    st.title("➕ Új állomás rögzítése")
    with st.form("a_form"):
        n = st.text_input("Név"); t = st.selectbox("Típus", ["MOL", "ORLEN", "Egyéb"])
        la = st.text_input("Lat (pl. 47.12)"); lo = st.text_input("Lon (pl. 19.12)")
        if st.form_submit_button("Mentés"):
            sheet_allomasok.append_row([len(data['allomasok'])+1, n, t, la, lo])
            st.success("Állomás hozzáadva!")
