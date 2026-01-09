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

def find_col(df, targets):
    if df.empty: return "Ismeretlen"
    for target in targets:
        for c in df.columns:
            if target.lower() in str(c).lower(): return c
    return df.columns[0]

COL_A = find_col(data['naplo'], ["Állomás", "Allomas"])
COL_S = find_col(data['naplo'], ["Státusz", "Status"])
COL_T = find_col(data['naplo'], ["Hibajegyszám", "Ticket"])
COL_DESC = find_col(data['naplo'], ["Hiba leírása", "Leírás"])

COL_V_ALL = find_col(data['vez'], ["Allomas", "Állomás"])
COL_V_FEL = find_col(data['vez'], ["Feladat", "Hiba"])
COL_V_TECH = find_col(data['vez'], ["Technikus", "Név"])

hibas_df = data['naplo'][data['naplo'][COL_S].isin(['Nyitott', 'Visszamenni'])].copy() if not data['naplo'].empty else pd.DataFrame()

def get_task_label(row):
    ticket = f"[{row[COL_T]}] " if COL_T in row and str(row[COL_T]).strip() else ""
    return f"{row[COL_A]} | {ticket}{row[COL_DESC]}"

# -----------------------------
# MENÜ ÉS LOGIKA
# -----------------------------
if 'edit_row_id' not in st.session_state: st.session_state.edit_row_id = None

menu = st.sidebar.radio("Menü", ["Műszerfal & Térkép", "Hiba rögzítése", "Vezénylés", "Új állomás felvitele"])
active_menu = "Vezénylés" if st.session_state.edit_row_id else menu

# -----------------------------
# 1. MŰSZERFAL & TÉRKÉP
# -----------------------------
if active_menu == "Műszerfal & Térkép":
    st.title("🛠️ Operatív Irányítópult")
    if not hibas_df.empty:
        hibas_df['dt_temp'] = pd.to_datetime(hibas_df['Dátum'], errors='coerce')
        hibas_df['only_date'] = hibas_df['dt_temp'].dt.date
        hibas_df = hibas_df.sort_values('dt_temp')
        unique_dates = hibas_df['only_date'].dropna().unique()
        
        if len(unique_dates) > 0:
            date_cols = st.columns(len(unique_dates))
            for idx, d_val in enumerate(unique_dates):
                with date_cols[idx]:
                    st.markdown(f"### 📅 {d_val}")
                    day_tasks = hibas_df[hibas_df['only_date'] == d_val]
                    for _, row in day_tasks.iterrows():
                        ticket_prefix = f"**{row[COL_T]}** - " if COL_T in row and row[COL_T] else ""
                        with st.container(border=True):
                            st.write(f"⏰ Bejelentve: {str(row['Dátum']).split(' ')[1] if ' ' in str(row['Dátum']) else ''}")
                            st.markdown(f"📍 **{row[COL_A]}**")
                            st.write(f"{ticket_prefix}{row[COL_DESC]}")
                            v_info = data['vez'][(data['vez'][COL_V_ALL] == row[COL_A]) & (data['vez'][COL_V_FEL] == row[COL_DESC])] if not data['vez'].empty else pd.DataFrame()
                            if not v_info.empty:
                                lv = v_info.iloc[-1]
                                st.success(f"👤 {lv[COL_V_TECH]}\n🕒 Ütemezve: {lv['Datum']}")
                                btn_label, btn_help = "📝", "Módosítás"
                            else:
                                st.warning("❌ Nincs ütemezve")
                                btn_label, btn_help = "📅", "Új ütemezés"
                            
                            b1, b2, b3 = st.columns(3)
                            if b1.button("✅", key=f"ok_{row['_sheet_row']}"):
                                sheet_naplo.update_cell(row['_sheet_row'], 4, "Kész"); st.rerun()
                            if b2.button(btn_label, key=f"ed_{row['_sheet_row']}", help=btn_help):
                                st.session_state.edit_row_id = row['_sheet_row']; st.rerun()
                            if b3.button("🔄", key=f"re_{row['_sheet_row']}"):
                                sheet_naplo.update_cell(row['_sheet_row'], 4, "Visszamenni"); st.rerun()
    st.divider()
    # TÉRKÉP (kihagyva a rövidítés miatt, de a helye megvan)

# -----------------------------
# 2. VEZÉNYLÉS
# -----------------------------
elif active_menu == "Vezénylés":
    row_id = st.session_state.edit_row_id
    st.title("📋 " + ("Ütemezés módosítása" if row_id else "Új vezénylés"))
    with st.form("v_form"):
        if row_id:
            row_data = data['naplo'][data['naplo']['_sheet_row'] == row_id].iloc[0]
            default_allomas, default_feladat = row_data[COL_A], row_data[COL_DESC]
            task_list = [get_task_label(row_data)]
        else:
            task_options = {get_task_label(r): r for _, r in hibas_df.iterrows()}
            task_list = list(task_options.keys())

        techs = data['tech']['Név'].tolist() if not data['tech'].empty else ["Nincs technikus"]
        t_tech = st.selectbox("Technikus kiválasztása", techs)
        selected_task_label = st.selectbox("Választható feladat", task_list)
        st.info("Az alábbi időpont a technikus ütemezett kiszállási ideje.")
        t_date = st.date_input("Kiszállás napja", date.today())
        t_time = st.time_input("Kiszállás órája", time(8, 0))
        
        c1, c2 = st.columns(2)
        if c1.form_submit_button("Mentés"):
            final_allomas, final_feladat = (default_allomas, default_feladat) if row_id else (task_options[selected_task_label][COL_A], task_options[selected_task_label][COL_DESC])
            try:
                cells = sheet_vez.findall(final_allomas)
                for cell in reversed(cells):
                    if sheet_vez.cell(cell.row, list(data['vez'].columns).index(COL_V_FEL)+1).value == final_feladat:
                        sheet_vez.delete_rows(cell.row)
            except: pass
            sheet_vez.append_row([t_tech, final_allomas, f"{t_date} {t_time.strftime('%H:%M')}", final_feladat])
            st.session_state.edit_row_id = None; st.success("Sikeres mentés!"); st.rerun()
        if row_id and c2.form_submit_button("Ütemezés törlése"):
            st.session_state.edit_row_id = None; st.rerun()
    if st.button("Mégse"): st.session_state.edit_row_id = None; st.rerun()

# -----------------------------
# 3. HIBA RÖGZÍTÉSE
# -----------------------------
elif active_menu == "Hiba rögzítése":
    st.title("🐞 Új hiba bejelentése")
    with st.form("h_form"):
        opts = {f"{r['Nev']} ({r['Tipus']})": r['Nev'] for _, r in data['allomasok'].iterrows()}
        val_all = st.selectbox("Állomás", list(opts.keys()))
        val_ticket = st.text_input("Hibajegyszám (opcionális)")
        desc = st.text_area("Hiba leírása")
        d, t = st.date_input("Dátum", date.today()), st.time_input("Idő", time(12, 0))
        if st.form_submit_button("Mentés"):
            sheet_naplo.append_row([f"{d} {t.strftime('%H:%M')}", opts[val_all], desc, "Nyitott", val_ticket])
            st.success("Hiba rögzítve!"); st.rerun()

# -----------------------------
# 4. ÚJ ÁLLOMÁS FELVITELE
# -----------------------------
elif active_menu == "Új állomás felvitele":
    st.title("➕ Új állomás rögzítése")
    with st.form("a_form"):
        n = st.text_input("Név"); t = st.selectbox("Típus", ["MOL", "ORLEN", "Egyéb"])
        la, lo = st.text_input("Lat"), st.text_input("Lon")
        if st.form_submit_button("Mentés"):
            sheet_allomasok.append_row([len(data['allomasok'])+1, n, t, la, lo])
            st.success("Hozzáadva!"); st.rerun()
