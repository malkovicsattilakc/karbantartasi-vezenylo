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

try:
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
except Exception as e:
    st.error(f"Csatlakozási hiba: {e}")
    st.stop()

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

COL_A = next((c for c in data['naplo'].columns if 'Állomás' in c), "Állomás neve:")
COL_S = next((c for c in data['naplo'].columns if 'Státusz' in c), "Státusz")

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
    
    # Adatok előkészítése és rendezése határidő szerint
    hibas_df = data['naplo'][data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni'])].copy()
    
    if not hibas_df.empty:
        # Próbáljuk dátum formátumra alakítani a rendezéshez (YYYY-MM-DD HH:MM)
        hibas_df['sort_dt'] = pd.to_datetime(hibas_df['Dátum'], errors='coerce')
        hibas_df = hibas_df.sort_values(by='sort_dt', ascending=True)

    st.subheader(f"📝 Aktuális feladatok határidő szerint ({len(hibas_df)} db)")

    if not hibas_df.empty:
        header = st.columns([2, 2, 2.5, 2, 3.5])
        header[0].write("**Határidő**"); header[1].write("**Állomás**"); header[2].write("**Hiba**"); header[3].write("**Ütemezés**"); header[4].write("**Műveletek**")
        st.divider()

        for idx, row in hibas_df.iterrows():
            # Megkeressük a valódi sorindexet a Google Táblázatban (Pandas index + 2)
            # Mivel a táblázat fejlécéből olvassuk az adatokat, az index eltolódhat, 
            # ezért a get_all_records() utáni indexelést használjuk.
            real_idx = idx + 2 
            
            c = st.columns([2, 2, 2.5, 2, 3.5])
            all_name = row[COL_A]
            
            # Időpont kiírása (Ha van benne szóköz, akkor feltételezzük, hogy van idő is)
            c[0].write(f"📅 {row['Dátum']}")
            c[1].write(all_name)
            c[2].write(row.get('Hiba leírása', '---'))
            
            v_info = data['vez'][data['vez']['Allomas_Neve'] == all_name] if not data['vez'].empty else pd.DataFrame()
            is_scheduled = not v_info.empty
            
            if is_scheduled:
                last_v = v_info.iloc[-1]
                c[3].info(f"👤 {last_v.get('Technikus_Neve', 'N/A')}\n📅 {last_v.get('Datum', 'N/A')}")
            else:
                c[3].write("---")

            b = c[4].columns(4)
            if b[0].button("✅", key=f"k_{idx}"):
                sheet_naplo.update_cell(real_idx, 4, "Kész"); st.rerun()
            if b[1].button("🔄", key=f"v_{idx}"):
                sheet_naplo.update_cell(real_idx, 4, "Visszamenni"); st.rerun()
            if is_scheduled and b[2].button("📝", key=f"e_{idx}"):
                st.session_state.edit_allomas = all_name; st.rerun()
            
            if b[3].button("🗑️", key=f"del_{idx}"):
                sheet_naplo.delete_rows(real_idx)
                st.rerun()
    else:
        st.info("Nincs aktív feladat.")

    # TÉRKÉP
    st.subheader("📍 Térkép")
    map_df = data['allomasok'].copy()
    if not map_df.empty and 'Lat' in map_df.columns:
        map_df['Lat'] = pd.to_numeric(map_df['Lat'], errors='coerce')
        map_df['Lon'] = pd.to_numeric(map_df['Lon'], errors='coerce')
        map_df = map_df.dropna(subset=['Lat', 'Lon'])
        map_df['hibak_szama'] = map_df['Nev'].apply(lambda x: len(hibas_df[hibas_df[COL_A] == x]) if not hibas_df.empty else 0)
        plot_df = map_df[map_df['hibak_szama'] > 0].copy()

        if not plot_df.empty:
            st.pydeck_chart(pdk.Deck(
                map_style='mapbox://styles/mapbox/light-v9',
                initial_view_state=pdk.ViewState(latitude=plot_df['Lat'].mean(), longitude=plot_df['Lon'].mean(), zoom=7),
                layers=[
                    pdk.Layer("ScatterplotLayer", plot_df, get_position="[Lon, Lat]", get_fill_color=[255, 0, 0, 180], get_radius=6500),
                    pdk.Layer("TextLayer", plot_df, get_position="[Lon, Lat]", get_text="hibak_szama", get_size=22, get_color=[0, 0, 0])
                ]
            ))

# -----------------------------
# 2. HIBA RÖGZÍTÉSE (HATÁRIDŐ + PONTOS IDŐ)
# -----------------------------
elif current_menu == "Hiba rögzítése":
    st.title("🐞 Új hiba és határidő megadása")
    with st.form("h_form"):
        all_names = data['allomasok']['Nev'].tolist() if not data['allomasok'].empty else []
        val_allomas = st.selectbox("Állomás kiválasztása", all_names)
        val_leiras = st.text_area("Hiba leírása")
        
        st.write("---")
        col1, col2 = st.columns(2)
        val_datum = col1.date_input("Határidő napja", date.today())
        val_ido = col2.time_input("Pontos idő (óra:perc)", time(12, 0))
        
        if st.form_submit_button("Mentés a feladatok közé"):
            if val_allomas and val_leiras:
                # Kombinált dátum és idő formátum: YYYY-MM-DD HH:MM
                teljes_hatarido = f"{val_datum} {val_ido.strftime('%H:%M')}"
                sheet_naplo.append_row([teljes_hatarido, val_allomas, val_leiras, "Nyitott", ""])
                st.success(f"Feladat rögzítve: {teljes_hatarido}")
                st.cache_data.clear()
            else:
                st.error("Kérlek adj meg minden adatot!")

# -----------------------------
# 3. VEZÉNYLÉS / MÓDOSÍTÁS
# -----------------------------
elif current_menu == "Vezénylés":
    editing = st.session_state.edit_allomas
    st.title("📋 " + ("Ütemezés módosítása" if editing else "Technikus kirendelése"))
    
    with st.form("v_form"):
        t_list = data['tech']['Név'].tolist() if not data['tech'].empty else []
        a_list = data['allomasok']['Nev'].tolist() if not data['allomasok'].empty else []
        
        tech = st.selectbox("Technikus", t_list)
        hely = st.selectbox("Helyszín", a_list, index=a_list.index(editing) if editing in a_list else 0)
        nap = st.date_input("Kivonulás napja", date.today())
        ora = st.time_input("Tervezett időpont", time(8, 0))
        feladat = st.text_area("Részletek", "Módosítás" if editing else "")
        
        if st.form_submit_button("Vezénylés mentése"):
            if editing:
                cells = sheet_vez.findall(editing)
                for cell in reversed(cells): sheet_vez.delete_rows(cell.row)
            
            sheet_vez.append_row([tech, hely, f"{nap} {ora.strftime('%H:%M')}", feladat])
            st.session_state.edit_allomas = None
            st.success("Vezénylés elmentve!")
            st.rerun()

# -----------------------------
# 4. ÚJ ÁLLOMÁS
# -----------------------------
elif current_menu == "Új állomás felvitele":
    st.title("➕ Új állomás")
    with st.form("a_form"):
        n = st.text_input("Állomás neve")
        t = st.selectbox("Típus", ["MOL", "ORLEN", "Egyéb"])
        la = st.text_input("Lat"); lo = st.text_input("Lon")
        if st.form_submit_button("Mentés"):
            sheet_allomasok.append_row([len(data['allomasok'])+1, n, t, la, lo])
            st.success("Hozzáadva!")
            st.cache_data.clear()
