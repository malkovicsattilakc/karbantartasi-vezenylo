import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import date, datetime
from geopy.geocoders import Nominatim # Koordináta kereséshez

# ---------- KONFIGURÁCIÓ ----------
st.set_page_config(layout="wide", page_title="Karbantartási Vezénylő")

SCOPE = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# ---------- ADATBÁZIS KAPCSOLAT ----------
@st.cache_resource
def get_spreadsheet():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPE)
    gc = gspread.authorize(creds)
    return gc.open("Terkep_Adatbazis")

@st.cache_data(ttl=60)
def load_data():
    sh = get_spreadsheet()
    return {
        "st": sh.worksheet("Allomasok").get_all_records(),
        "log": sh.worksheet("Naplo").get_all_records(),
        "tech": sh.worksheet("Technikusok").get_all_records(),
        "vez": sh.worksheet("Vezenylesek").get_all_records()
    }

def run_operation(func, *args):
    try:
        func(*args)
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Hiba a művelet során: {e}")

# ---------- ADATOK ELŐKÉSZÍTÉSE ----------
try:
    sh = get_spreadsheet()
    data = load_data()
    st_data, log_data, tech_data, vez_data = data["st"], data["log"], data["tech"], data["vez"]
    tech_names = [t['Nev'] for t in tech_data if t.get('Nev')]
except Exception as e:
    st.error("Adatbázis hiba.")
    st.stop()

def safe_date(d_attr):
    if isinstance(d_attr, date): return d_attr
    try: return datetime.strptime(str(d_attr).strip(), "%Y-%m-%d").date()
    except: return date.today()

def get_hiba_id(row):
    return f"{row.get('Allomas_Neve')}: {row.get('Kod', '')} - {row.get('Leiras', '')} ({row.get('Datum', '')})"

# ---------- OLDALSÁV (SIDEBAR) ----------
st.sidebar.title("🛠️ Kezelőpanel")

# 1. ÚJ ÁLLOMÁS HOZZÁADÁSA (Geokódolással)
with st.sidebar.expander("➕ Új állomás felvétele"):
    with st.form("new_station"):
        n_name = st.text_input("Állomás neve (pl. Szentlőrinc 1)")
        n_type = st.selectbox("Típus", ["MOL", "ORLEN"])
        n_address = st.text_input("Cím vagy Város (a koordinátákhoz)", placeholder="pl. Szentlőrinc")
        
        if st.form_submit_button("Állomás mentése"):
            geolocator = Nominatim(user_agent="karbantarto_app")
            try:
                # Keresés Magyarországon belül
                location = geolocator.geocode(f"{n_address}, Hungary")
                if location:
                    # Allomasok fül oszlopai: Nev, Lat, Lon, Tipus
                    run_operation(sh.worksheet("Allomasok").append_row, [n_name, location.latitude, location.longitude, n_type])
                    st.success(f"Siker! Koordináták: {location.latitude}, {location.longitude}")
                else:
                    st.error("Nem találtam meg a helyszínt. Kérlek add meg pontosabban!")
            except:
                st.error("Hiba a keresés közben.")

st.sidebar.divider()

# 2. ÚJ HIBA RÖGZÍTÉSE
with st.sidebar.expander("📝 Új hiba rögzítése"):
    with st.form("new_fault", clear_on_submit=True):
        # Kút választás: Név + Típus megjelenítése
        station_options = [f"{s['Nev']} ({s.get('Tipus', '?')})" for s in st_data]
        f_station_raw = st.selectbox("Kút", station_options)
        f_kod = st.text_input("Kód")
        f_desc = st.text_input("Hiba leírása")
        f_date = st.date_input("Hiba napja", date.today())
        f_time = st.selectbox("Idő", [f"{h:02d}:{m:02d}" for h in range(6,22) for m in (0,30)])
        
        if st.form_submit_button("Mentés"):
            # Csak a nevet mentjük el (levágjuk a típust a végéről)
            f_station_name = f_station_raw.split(" (")[0]
            run_operation(sh.worksheet("Naplo").append_row, [f_station_name, str(f_date), f_desc, f_time, f_kod])

# 3. BEOSZTÁS
with st.sidebar.expander("👷 Technikus vezénylése"):
    with st.form("assign_tech", clear_on_submit=True):
        v_tech = st.selectbox("Technikus", tech_names)
        hiba_list = [get_hiba_id(l) for l in log_data]
        v_hiba = st.selectbox("Melyik hiba?", hiba_list) if hiba_list else st.selectbox("Nincs hiba", ["-"])
        v_date = st.date_input("Munkavégzés napja", date.today())
        if st.form_submit_button("Beosztás"):
            run_operation(sh.worksheet("Vezenylesek").append_row, [v_tech, v_hiba.split(": ")[0], str(v_date), v_hiba])

# ---------- FŐOLDAL ----------
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
                    st.markdown(f"**{l.get('Ido','--')} - {l['Allomas_Neve']}**")
                    st.markdown(f"*{l.get('Kod', 'Nincs kód')}* - {l.get('Leiras')}")
                    if v:
                        st.success(f"👷 {v['Technikus_Neve']}")
                    else:
                        st.warning("Nincs beosztva")
                    
                    if st.button("🗑️ Törlés", key=f"del_{i}_{day_str}"):
                        orig_l_idx = next((idx for idx, row in enumerate(log_data) if get_hiba_id(row) == h_id), None)
                        if orig_l_idx is not None:
                            sh.worksheet("Naplo").delete_rows(orig_l_idx + 2)
                        orig_v_idx = next((idx for idx, row in enumerate(vez_data) if row.get('Hiba') == h_id), None)
                        if orig_v_idx is not None:
                            sh.worksheet("Vezenylesek").delete_rows(orig_v_idx + 2)
                        st.cache_data.clear()
                        st.rerun()

# ---------- TÉRKÉP (MOL=ZÖLD, ORLEN=PIROS) ----------
st.divider()
st.subheader("📍 Helyszíni áttekintés")
m = folium.Map(location=[47.1625, 19.5033], zoom_start=7)

station_summary = {}
for l in log_data:
    h_id = get_hiba_id(l)
    vez_info = any(v.get('Hiba') == h_id for v in vez_data)
    if only_unplanned and vez_info: continue
    
    s_name = l['Allomas_Neve']
    if s_name not in station_summary:
        match = [s for s in st_data if s['Nev'] == s_name]
        if match:
            # Itt vesszük ki a típust az Allomasok táblából
            s_type = match[0].get('Tipus', 'MOL').upper()
            station_summary[s_name] = {
                "coords": [match[0]['Lat'], match[0]['Lon']], 
                "hibak": [], 
                "type": s_type
            }
    
    if s_name in station_summary:
        station_summary[s_name]["hibak"].append(f"• {l.get('Kod','?')}: {l.get('Leiras')}")

for s_name, info in station_summary.items():
    count = len(info['hibak'])
    # Szín meghatározása típus alapján
    marker_color = "#27ae60" if info['type'] == "MOL" else "#e74c3c" # MOL: Zöld, Orlen: Piros
    
    icon_html = f'''
        <div style="
            background-color: {marker_color};
            width: 32px;
            height: 32px;
            border-radius: 50%;
            border: 3px solid white;
            color: white;
            font-weight: bold;
            display: flex;
            justify-content: center;
            align-items: center;
            box-shadow: 0px 2px 6px rgba(0,0,0,0.4);
            font-size: 14px;
        ">
            {count}
        </div>
    '''
    
    folium.Marker(
        location=info['coords'],
        icon=folium.DivIcon(html=icon_html),
        popup=folium.Popup(f"<b>{s_name} ({info['type']})</b><br>" + "<br>".join(info['hibak']), max_width=300),
        tooltip=f"{s_name} ({info['type']})"
    ).add_to(m)

st_folium(m, width=1200, height=500, returned_objects=[])