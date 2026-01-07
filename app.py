import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import date, datetime

# ---------- KONFIGURÁCIÓ ----------
st.set_page_config(layout="wide", page_title="Karbantartási Vezénylő")

SCOPE = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_spreadsheet():
    """Kapcsolódás a Google Sheets-hez (egyszeri példány)."""
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPE)
    gc = gspread.authorize(creds)
    return gc.open("Terkep_Adatbazis")

@st.cache_data(ttl=60)
def load_data():
    """Adatok betöltése a táblázatból."""
    sh = get_spreadsheet()
    return {
        "st": sh.worksheet("Allomasok").get_all_records(),
        "log": sh.worksheet("Naplo").get_all_records(),
        "tech": sh.worksheet("Technikusok").get_all_records(),
        "vez": sh.worksheet("Vezenylesek").get_all_records()
    }

def run_operation(func, *args):
    """Művelet végrehajtása és cache ürítése."""
    try:
        func(*args)
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Hiba a művelet során: {e}")

# ---------- SEGÉDFÜGGVÉNYEK ----------
def get_hiba_id(row):
    """Egyedi azonosító generálása a hibákhoz a státusz figyelembevételével."""
    vissza = " [!] VISSZA KELL MENNI" if str(row.get('Statusz', '')) == 'VISSZA' else ""
    return f"{row.get('Allomas_Neve')}: {row.get('Kod', '')} - {row.get('Leiras', '')}{vissza} ({row.get('Datum', '')})"

# ---------- ADATOK BETÖLTÉSE ----------
try:
    sh = get_spreadsheet()
    data = load_data()
    st_data, log_data, tech_data, vez_data = data["st"], data["log"], data["tech"], data["vez"]
    tech_names = [t['Nev'] for t in tech_data if t.get('Nev')]
except Exception as e:
    st.error(f"Adatbázis hiba: {e}")
    st.info("Ellenőrizd az oszlopokat: Naplo (6 oszlop), Allomasok (4 oszlop)!")
    st.stop()

# ---------- OLDALSÁV (SIDEBAR) ----------
st.sidebar.title("🛠️ Kezelőpanel")

# 1. ÚJ ÁLLOMÁS (Kézi koordináták)
with st.sidebar.expander("➕ Új állomás felvétele"):
    with st.form("new_station"):
        n_name = st.text_input("Állomás neve")
        n_type = st.selectbox("Típus", ["MOL", "ORLEN"])
        st.write("📍 Koordináták (tizedes ponttal):")
        n_lat = st.number_input("Szélesség (Lat)", format="%.4f", value=47.1625)
        n_lon = st.number_input("Hosszúság (Lon)", format="%.4f", value=19.5033)
        if st.form_submit_button("Mentés"):
            run_operation(sh.worksheet("Allomasok").append_row, [n_name, n_lat, n_lon, n_type])

# 2. ÚJ HIBA
with st.sidebar.expander("📝 Új hiba rögzítése"):
    with st.form("new_fault", clear_on_submit=True):
        station_options = [f"{s['Nev']} ({s.get('Tipus', '?')})" for s in st_data]
        f_station_raw = st.selectbox("Kút", station_options)
        f_kod = st.text_input("Kód")
        f_desc = st.text_input("Hiba leírása")
        f_date = st.date_input("Hiba napja", date.today())
        f_time = st.selectbox("Idő", [f"{h:02d}:{m:02d}" for h in range(6,22) for m in (0,30)])
        if st.form_submit_button("Hiba rögzítése"):
            run_operation(sh.worksheet("Naplo").append_row, [f_station_raw.split(" (")[0], str(f_date), f_desc, f_time, f_kod, "ÚJ"])

# 3. BEOSZTÁS
with st.sidebar.expander("👷 Technikus vezénylése"):
    with st.form("assign_tech", clear_on_submit=True):
        v_tech = st.selectbox("Technikus", tech_names)
        hiba_list = [get_hiba_id(l) for l in log_data]
        v_hiba = st.selectbox("Melyik hiba?", hiba_list) if hiba_list else st.selectbox("Nincs hiba", ["-"])
        v_date = st.date_input("Tervezett nap", date.today())
        if st.form_submit_button("Beosztás"):
            run_operation(sh.worksheet("Vezenylesek").append_row, [v_tech, v_hiba.split(": ")[0], str(v_date), v_hiba])

# ---------- FŐOLDAL - MÁTRIX ----------
st.title("📅 Összes munka")
only_unplanned = st.sidebar.toggle("Csak a beütemezetlen munkák", value=False)

display_data = []
for l in log_data:
    h_id = get_hiba_id(l)
    vez_info = next((v for v in vez_data if v.get('Hiba') == h_id), None)
    if only_unplanned and vez_info: continue
    display_data.append((l, vez_info))

if not display_data:
    st.info("Nincs rögzített munka.")
else:
    unique_days = sorted(list(set(str(item[0]['Datum']) for item in display_data)))
    cols = st.columns(len(unique_days))

    for col, day_str in zip(cols, unique_days):
        col.markdown(f"### {day_str}")
        for i, (l, v) in enumerate(display_data):
            if str(l['Datum']) == day_str:
                h_id = get_hiba_id(l)
                with col.container(border=True):
                    if str(l.get('Statusz')) == 'VISSZA':
                        st.error("🔄 VISSZA KELL MENNI")
                    
                    st.markdown(f"**{l.get('Ido','--')} - {l['Allomas_Neve']}**")
                    st.markdown(f"*{l.get('Kod', '')}* - {l.get('Leiras')}")
                    
                    if v:
                        st.success(f"👷 {v['Technikus_Neve']}")
                        c1, c2 = st.columns(2)
                        if c1.button("✅ Kész", key=f"done_{i}_{day_str}"):
                            l_idx = next((idx for idx, row in enumerate(log_data) if get_hiba_id(row) == h_id), None)
                            if l_idx is not None: sh.worksheet("Naplo").delete_rows(l_idx + 2)
                            v_idx = next((idx for idx, row in enumerate(vez_data) if row.get('Hiba') == h_id), None)
                            if v_idx is not None: sh.worksheet("Vezenylesek").delete_rows(v_idx + 2)
                            st.cache_data.clear(); st.rerun()
                        
                        if c2.button("🔄 Vissza", key=f"back_{i}_{day_str}"):
                            l_idx = next((idx for idx, row in enumerate(log_data) if get_hiba_id(row) == h_id), None)
                            if l_idx is not None: sh.worksheet("Naplo").update_cell(l_idx + 2, 6, "VISSZA")
                            v_idx = next((idx for idx, row in enumerate(vez_data) if row.get('Hiba') == h_id), None)
                            if v_idx is not None: sh.worksheet("Vezenylesek").delete_rows(v_idx + 2)
                            st.cache_data.clear(); st.rerun()
                    else:
                        st.warning("Beosztásra vár")

                    if st.button("🗑️ Törlés", key=f"del_{i}_{day_str}", use_container_width=True):
                        l_idx = next((idx for idx, row in enumerate(log_data) if get_hiba_id(row) == h_id), None)
                        if l_idx is not None: sh.worksheet("Naplo").delete_rows(l_idx + 2)
                        v_idx = next((idx for idx, row in enumerate(vez_data) if row.get('Hiba') == h_id), None)
                        if v_idx is not None: sh.worksheet("Vezenylesek").delete_rows(v_idx + 2)
                        st.cache_data.clear(); st.rerun()

# ---------- TÉRKÉP ----------
st.divider()
st.subheader("📍 Helyszíni állapot")
m = folium.Map(location=[47.1625, 19.5033], zoom_start=7)

station_summary = {}
for l in log_data:
    h_id = get_hiba_id(l)
    vez_info = any(v.get('Hiba') == h_id for v in vez_data)
    is_back = (str(l.get('Statusz')) == 'VISSZA')
    if only_unplanned and vez_info: continue
    
    s_name = l['Allomas_Neve']
    if s_name not in station_summary:
        match = [s for s in st_data if s['Nev'] == s_name]
        if match:
            station_summary[s_name] = {
                "coords": [match[0]['Lat'], match[0]['Lon']], 
                "hibak": [], 
                "type": match[0].get('Tipus', 'MOL'),
                "p": False, "u": False, "b": False
            }
    
    if s_name in station_summary:
        station_summary[s_name]["hibak"].append(f"• {l.get('Kod','?')}: {l.get('Leiras')}")
        if is_back: station_summary[s_name]["b"] = True
        if vez_info: station_summary[s_name]["p"] = True
        else: station_summary[s_name]["u"] = True

for s_name, info in station_summary.items():
    if info['b']: border = "yellow"
    elif info['p'] and info['u']: border = "brown"
    elif info['p']: border = "#27ae60"
    else: border = "white"

    bg = "#27ae60" if info['type'] == "MOL" else "#e74c3c"
    
    icon_html = f'''
        <div style="background-color: {bg}; width: 34px; height: 34px; border-radius: 50%; border: 4px solid {border};
            color: white; font-weight: bold; display: flex; justify-content: center; align-items: center;
            box-shadow: 0px 2px 6px rgba(0,0,0,0.5); font-size: 14px;">{len(info['hibak'])}</div>
    '''
    folium.Marker(location=info['coords'], icon=folium.DivIcon(html=icon_html),
                  popup=folium.Popup(f"<b>{s_name}</b><br>"+ "<br>".join(info['hibak']), max_width=300)).add_to(m)

st_folium(m, width=1200, height=500, returned_objects=[])