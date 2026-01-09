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

try:
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
except Exception as e:
    st.error("Csatlakozási hiba a Google Sheets-hez. Ellenőrizd a secrets-eket!")
    st.stop()

# Lapok betöltése
sheet_naplo = sh.worksheet("Naplo")
sheet_vez = sh.worksheet("Vezenylesek")
sheet_allomasok = sh.worksheet("Allomasok")
sheet_tech = sh.worksheet("Technikusok")

@st.cache_data(ttl=1)
def load_all_data():
    def get_safe_df(s):
        records = s.get_all_records()
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df.columns = [str(c).strip() for c in df.columns]
        df['_sheet_row'] = range(2, len(df) + 2)
        return df

    return {
        "allomasok": get_safe_df(sheet_allomasok),
        "naplo": get_safe_df(sheet_naplo),
        "tech": get_safe_df(sheet_tech),
        "vez": get_safe_df(sheet_vez)
    }

data = load_all_data()

# Biztonságos oszlopkeresés
def get_col(df, key, default):
    if df.empty: return default
    return next((c for c in df.columns if key in c), default)

COL_A = get_col(data['naplo'], 'Állomás', "Állomás neve:")
COL_S = get_col(data['naplo'], 'Státusz', "Státusz")

# Aktív hibák kigyűjtése a szűréshez
if not data['naplo'].empty and COL_S in data['naplo'].columns:
    hibas_df_all = data['naplo'][data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni'])].copy()
    # Azon állomások listája, ahol aktív hiba van
    aktiv_hibas_allomasok = hibas_df_all[COL_A].unique().tolist()
else:
    hibas_df_all = pd.DataFrame()
    aktiv_hibas_allomasok = []

# -----------------------------
# MENÜ KEZELÉS
# -----------------------------
if 'edit_target' not in st.session_state:
    st.session_state.edit_target = None

menu = st.sidebar.radio("Menü", ["Műszerfal & Térkép", "Hiba rögzítése", "Vezénylés", "Új állomás felvitele"])
active_menu = "Vezénylés" if st.session_state.edit_target else menu

# -----------------------------
# 1. MŰSZERFAL & TÉRKÉP
# -----------------------------
if active_menu == "Műszerfal & Térkép":
    st.title("🛠️ Feladatkezelő és Műszerfal")
    
    if not hibas_df_all.empty:
        # Időrendi rendezés
        hibas_df_all['dt_temp'] = pd.to_datetime(hibas_df_all['Dátum'], errors='coerce')
        hibas_df_sorted = hibas_df_all.sort_values('dt_temp', ascending=True)
    else:
        hibas_df_sorted = pd.DataFrame()

    st.subheader(f"📅 Aktuális munkák időrendben ({len(hibas_df_sorted)} db)")

    if not hibas_df_sorted.empty:
        h = st.columns([2, 2, 2.5, 2, 3])
        h[0].write("**Határidő**"); h[1].write("**Helyszín**"); h[2].write("**Feladat**"); h[3].write("**Technikus**"); h[4].write("**Műveletek**")
        st.divider()

        for _, row in hibas_df_sorted.iterrows():
            c = st.columns([2, 2, 2.5, 2, 3])
            all_name = row[COL_A]
            s_row = row['_sheet_row']
            
            c[0].write(f"⏰ {row['Dátum']}")
            c[1].write(all_name)
            c[2].write(row.get('Hiba leírása', '---'))
            
            v_info = data['vez'][data['vez']['Allomas_Neve'] == all_name] if not data['vez'].empty else pd.DataFrame()
            is_sched = not v_info.empty
            if is_sched:
                last_v = v_info.iloc[-1]
                c[3].info(f"👤 {last_v.get('Technikus_Neve', 'N/A')}")
            else:
                c[3].write("---")

            b = c[4].columns(4)
            if b[0].button("✅", key=f"k_{s_row}"):
                sheet_naplo.update_cell(s_row, 4, "Kész"); st.rerun()
            if b[1].button("🔄", key=f"v_{s_row}"):
                sheet_naplo.update_cell(s_row, 4, "Visszamenni"); st.rerun()
            if is_sched and b[2].button("📝", key=f"e_{s_row}"):
                st.session_state.edit_target = all_name; st.rerun()
            if b[3].button("🗑️", key=f"t_{s_row}"):
                sheet_naplo.delete_rows(s_row)
                st.rerun()
    else:
        st.info("Nincs rögzített aktív feladat.")

    # TÉRKÉP
    st.subheader("📍 Térkép")
    m_df = data['allomasok'].copy()
    if not m_df.empty and 'Lat' in m_df.columns:
        m_df['Lat'] = pd.to_numeric(m_df['Lat'], errors='coerce')
        m_df['Lon'] = pd.to_numeric(m_df['Lon'], errors='coerce')
        m_df = m_df.dropna(subset=['Lat', 'Lon'])
        m_df['hibak'] = m_df['Nev'].apply(lambda x: len(hibas_df_sorted[hibas_df_sorted[COL_A] == x]) if not hibas_df_sorted.empty else 0)
        p_df = m_df[m_df['hibak'] > 0]
        if not p_df.empty:
            st.pydeck_chart(pdk.Deck(
                map_style=None,
                initial_view_state=pdk.ViewState(latitude=p_df['Lat'].mean(), longitude=p_df['Lon'].mean(), zoom=7),
                layers=[
                    pdk.Layer("ScatterplotLayer", p_df, get_position="[Lon, Lat]", get_fill_color=[255, 0, 0, 150], get_radius=7000),
                    pdk.Layer("TextLayer", p_df, get_position="[Lon, Lat]", get_text="hibak", get_size=25, get_color=[0, 0, 0])
                ]
            ))

# -----------------------------
# 2. HIBA RÖGZÍTÉSE
# -----------------------------
elif active_menu == "Hiba rögzítése":
    st.title("🐞 Új hiba és határidő")
    with st.form("h_form"):
        a_names = data['allomasok']['Nev'].tolist() if not data['allomasok'].empty else []
        sel_all = st.selectbox("Állomás", a_names)
        desc = st.text_area("Hiba leírása")
        col1, col2 = st.columns(2)
        d = col1.date_input("Határidő napja", date.today())
        t = col2.time_input("Pontos idő", time(10, 0))
        if st.form_submit_button("Mentés"):
            if sel_all and desc:
                full_dt = f"{d} {t.strftime('%H:%M')}"
                sheet_naplo.append_row([full_dt, sel_all, desc, "Nyitott", ""])
                st.success(f"Hiba elmentve: {full_dt}"); st.cache_data.clear()
            else: st.error("Tölts ki minden mezőt!")

# -----------------------------
# 3. VEZÉNYLÉS (SZŰRT LISTÁVAL)
# -----------------------------
elif active_menu == "Vezénylés":
    target = st.session_state.edit_target
    st.title("📋 " + ("Ütemezés módosítása" if target else "Technikus kirendelése"))
    
    # Ha nincs aktív hiba, figyelmeztetünk
    if not aktiv_hibas_allomasok and not target:
        st.warning("Nincs olyan állomás, ahol aktív hiba lenne, ezért nem lehet vezényelni. Rögzíts előbb egy hibát!")
    else:
        with st.form("v_form"):
            techs = data['tech']['Név'].tolist() if not data['tech'].empty else []
            
            # CSAK AZ AKTÍV HIBÁS ÁLLOMÁSOK MEGJELENÍTÉSE
            # Ha módosítás van, akkor a módosítandót is hozzáadjuk, ha véletlenül nem lenne benne
            if target and target not in aktiv_hibas_allomasok:
                display_alls = [target] + aktiv_hibas_allomasok
            else:
                display_alls = aktiv_hibas_allomasok
            
            t_tech = st.selectbox("Technikus", techs)
            t_all = st.selectbox("Helyszín (Csak aktív hibák!)", display_alls, index=display_alls.index(target) if target in display_alls else 0)
            t_date = st.date_input("Dátum", date.today())
            t_time = st.time_input("Időpont", time(8, 0))
            
            if st.form_submit_button("Mentés"):
                if target: # Régi ütemezés törlése
                    try:
                        cells = sheet_vez.findall(target)
                        for cell in reversed(cells): sheet_vez.delete_rows(cell.row)
                    except: pass
                sheet_vez.append_row([t_tech, t_all, f"{t_date} {t_time.strftime('%H:%M')}", "Ütemezve"])
                st.session_state.edit_target = None
                st.success("Sikeres vezénylés!"); st.rerun()

    if target and st.button("Mégse"):
        st.session_state.edit_target = None; st.rerun()

# -----------------------------
# 4. ÚJ ÁLLOMÁS
# -----------------------------
elif active_menu == "Új állomás felvitele":
    st.title("➕ Új állomás rögzítése")
    with st.form("a_form"):
        n = st.text_input("Név"); t = st.selectbox("Típus", ["MOL", "ORLEN", "Egyéb"])
        la = st.text_input("Lat (pl. 47.12)"); lo = st.text_input("Lon (pl. 19.12)")
        if st.form_submit_button("Mentés"):
            if n and la and lo:
                sheet_allomasok.append_row([len(data['allomasok'])+1, n, t, la, lo])
                st.success("Állomás hozzáadva!"); st.cache_data.clear()
