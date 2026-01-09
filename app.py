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

st.set_page_config(page_title="Karbantartási vezénylő PRO", layout="wide")

try:
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
except:
    st.error("Google Sheets hiba! Ellenőrizd a hozzáférést.")
    st.stop()

sheet_naplo = sh.worksheet("Naplo")
sheet_vez = sh.worksheet("Vezenylesek")
sheet_allomasok = sh.worksheet("Allomasok")
sheet_tech = sh.worksheet("Technikusok")

@st.cache_data(ttl=1)
def load_all_data():
    def get_df(s):
        records = s.get_all_records()
        if not records: return pd.DataFrame()
        df = pd.DataFrame(records)
        df.columns = [str(c).strip() for c in df.columns]
        df['_sheet_row'] = range(2, len(df) + 2)
        return df
    return {"allomasok": get_df(sheet_allomasok), "naplo": get_df(sheet_naplo), 
            "tech": get_df(sheet_tech), "vez": get_df(sheet_vez)}

data = load_all_data()

# DINAMIKUS OSZLOPKERESÉS (Hogy ne legyen KeyError)
def find_col(df, target):
    if df.empty: return "Ismeretlen"
    for c in df.columns:
        if target.lower() in c.lower(): return c
    return df.columns[1] if len(df.columns) > 1 else target

COL_A = find_col(data['naplo'], "Állomás")
COL_S = find_col(data['naplo'], "Státusz")

# -----------------------------
# MENÜ ÉS LOGIKA
# -----------------------------
hibas_df = data['naplo'][data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni'])].copy() if not data['naplo'].empty else pd.DataFrame()

if 'edit_target' not in st.session_state: st.session_state.edit_target = None

menu = st.sidebar.radio("Menü", ["Műszerfal & Térkép", "Hiba rögzítése", "Vezénylés", "Új állomás"])
active_menu = "Vezénylés" if st.session_state.edit_target else menu

# -----------------------------
# 1. MŰSZERFAL & TÉRKÉP
# -----------------------------
if active_menu == "Műszerfal & Térkép":
    st.title("🛠️ Karbantartási Vezénylő")
    
    # 1.1 FELADATOK OSZLOPOS LISTÁZÁSA
    if not hibas_df.empty:
        # Dátum szerinti rendezés
        hibas_df['dt_temp'] = pd.to_datetime(hibas_df['Dátum'], errors='coerce')
        hibas_df = hibas_df.sort_values('dt_temp')
        
        for d_str, day_group in hibas_df.groupby('Dátum', sort=False):
            st.subheader(f"📅 {d_str}")
            # Feladatok megjelenítése oszlopokban (max 3 egy sorban)
            cols = st.columns(3)
            for i, (_, row) in enumerate(day_group.iterrows()):
                with cols[i % 3]:
                    st.info(f"📍 **{row[COL_A]}**")
                    st.write(f"**Hiba:** {row['Hiba leírása']}")
                    
                    # Ütemezési infó
                    v_info = data['vez'][data['vez']['Allomas_Neve'] == row[COL_A]] if not data['vez'].empty else pd.DataFrame()
                    if not v_info.empty:
                        lv = v_info.iloc[-1]
                        st.success(f"👤 {lv['Technikus_Neve']} | 📅 {lv['Datum']}")
                    else:
                        st.warning("❌ Nincs ütemezve")
                    
                    # Műveletek
                    b1, b2, b3 = st.columns(3)
                    if b1.button("✅", key=f"ok_{row['_sheet_row']}", help="Kész (Törlés)"):
                        sheet_naplo.update_cell(row['_sheet_row'], 4, "Kész")
                        cells = sheet_vez.findall(row[COL_A])
                        for cell in reversed(cells): sheet_vez.delete_rows(cell.row)
                        st.rerun()
                    if b2.button("📝", key=f"ed_{row['_sheet_row']}", help="Ütemezés"):
                        st.session_state.edit_target = row[COL_A]; st.rerun()
                    if b3.button("🔄", key=f"re_{row['_sheet_row']}", help="Visszamenni"):
                        sheet_naplo.update_cell(row['_sheet_row'], 4, "Visszamenni"); st.rerun()
            st.divider()
    else:
        st.info("Nincs aktív hiba.")

    # 1.2 TÉRKÉP PRO LOGIKA
    st.subheader("📍 Térképes nézet")
    m_df = data['allomasok'].copy()
    if not m_df.empty and 'Lat' in m_df.columns:
        m_df['Lat'] = pd.to_numeric(m_df['Lat'], errors='coerce')
        m_df['Lon'] = pd.to_numeric(m_df['Lon'], errors='coerce')
        m_df = m_df.dropna(subset=['Lat', 'Lon'])
        
        def get_map_logic(r):
            h_list = hibas_df[hibas_df[COL_A] == r['Nev']]
            h_count = len(h_list)
            if h_count == 0: return pd.Series([[200, 200, 200, 30], [100, 100, 100], 0])
            
            # Keret színe (Brand)
            brand = str(r.get('Tipus', '')).upper()
            l_color = [0, 255, 0] if "MOL" in brand else ([255, 0, 0] if "ORLEN" in brand else [0, 191, 255])
            
            # Kitöltés színe (Státusz)
            v_info = data['vez'][data['vez']['Allomas_Neve'] == r['Nev']] if not data['vez'].empty else pd.DataFrame()
            
            has_return = any(h_list[COL_S] == "Visszamenni")
            is_scheduled = not v_info.empty
            
            if has_return and not is_scheduled: f_color = [139, 69, 19, 230] # Barna
            elif is_scheduled: f_color = [0, 255, 0, 200]                   # Zöld
            elif has_return: f_color = [255, 255, 0, 200]                   # Sárga
            else: f_color = [255, 0, 0, 200]                                # Piros
                
            return pd.Series([f_color, l_color, h_count])

        m_df[['f_c', 'l_c', 'cnt']] = m_df.apply(get_map_logic, axis=1)
        plot_df = m_df[m_df['cnt'] > 0]

        st.pydeck_chart(pdk.Deck(
            initial_view_state=pdk.ViewState(latitude=47.1, longitude=19.5, zoom=6.5),
            layers=[
                pdk.Layer("ScatterplotLayer", plot_df, get_position="[Lon, Lat]", get_fill_color="f_c", 
                          get_line_color="l_c", line_width_min_pixels=3, get_radius=7500, stroked=True),
                pdk.Layer("TextLayer", plot_df, get_position="[Lon, Lat]", get_text="cnt", get_size=24, get_color=[0, 0, 0])
            ]
        ))

# -----------------------------
# 2. VEZÉNYLÉS
# -----------------------------
elif active_menu == "Vezénylés":
    target = st.session_state.edit_target
    st.title("📋 " + ("Ütemezés módosítása" if target else "Vezénylés"))
    
    any_station = st.sidebar.checkbox("Nem aktív hiba küldés")
    
    with st.form("v_form"):
        if any_station:
            all_list = data['allomasok']['Nev'].tolist()
        else:
            all_list = hibas_df[COL_A].unique().tolist()
            if target and target not in all_list: all_list.append(target)

        techs = data['tech']['Név'].tolist() if not data['tech'].empty else ["Nincs technikus"]
        
        t_tech = st.selectbox("Technikus", techs)
        t_all = st.selectbox("Helyszín", all_list, index=all_list.index(target) if target in all_list else 0)
        t_date = st.date_input("Dátum", date.today())
        t_time = st.time_input("Időpont", time(8, 0))
        
        c1, c2 = st.columns(2)
        if c1.form_submit_button("Mentés / Módosítás"):
            cells = sheet_vez.findall(t_all)
            for cell in reversed(cells): sheet_vez.delete_rows(cell.row)
            sheet_vez.append_row([t_tech, t_all, f"{t_date} {t_time.strftime('%H:%M')}", "Ütemezve"])
            st.session_state.edit_target = None; st.success("Mentve!"); st.rerun()
            
        if target and c2.form_submit_button("Ütemezés törlése (Hiba marad)"):
            cells = sheet_vez.findall(target)
            for cell in reversed(cells): sheet_vez.delete_rows(cell.row)
            st.session_state.edit_target = None; st.rerun()

    if st.button("Mégse"): st.session_state.edit_target = None; st.rerun()

# -----------------------------
# 3. HIBA RÖGZÍTÉSE
# -----------------------------
elif active_menu == "Hiba rögzítése":
    st.title("🐞 Új hiba bejelentése")
    with st.form("h_form"):
        opts = {f"{r['Nev']} ({r['Tipus']})": r['Nev'] for _, r in data['allomasok'].iterrows()}
        val_all = st.selectbox("Állomás", list(opts.keys()))
        desc = st.text_area("Hiba leírása")
        d = st.date_input("Dátum", date.today())
        t = st.time_input("Idő", time(12, 0))
        if st.form_submit_button("Mentés"):
            sheet_naplo.append_row([f"{d} {t.strftime('%H:%M')}", opts[val_all], desc, "Nyitott", ""])
            st.success("Rögzítve!"); st.rerun()

# -----------------------------
# 4. ÚJ ÁLLOMÁS
# -----------------------------
elif active_menu == "Új állomás":
    st.title("➕ Új állomás rögzítése")
    with st.form("a_form"):
        n = st.text_input("Név"); t = st.selectbox("Típus", ["MOL", "ORLEN", "Egyéb"])
        la = st.text_input("Lat"); lo = st.text_input("Lon")
        if st.form_submit_button("Mentés"):
            sheet_allomasok.append_row([len(data['allomasok'])+1, n, t, la, lo])
            st.success("Hozzáadva!"); st.rerun()
