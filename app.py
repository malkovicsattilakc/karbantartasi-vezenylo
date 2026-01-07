import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import date, datetime

# ---------- CONFIG & AUTH ----------
st.set_page_config(layout="wide", page_title="Karbantartási Vezénylő")

SCOPE = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# Biztonságos betöltés
@st.cache_resource
def get_gc():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPE)
    return gspread.authorize(creds)

try:
    gc = get_gc()
    sh = gc.open("Terkep_Adatbazis")
    sheet_allomasok = sh.worksheet("Allomasok")
    sheet_naplo = sh.worksheet("Naplo")
    sheet_tech = sh.worksheet("Technikusok")
    sheet_vezenyles = sh.worksheet("Vezenylesek")
except Exception as e:
    st.error(f"Kapcsolati hiba: {e}")
    st.stop()

# ---------- SEGÉDFÜGGVÉNYEK ----------
def safe_date(d_attr):
    """Kezeli ha a dátum a Sheet-ben nem YYYY-MM-DD formátumú"""
    if isinstance(d_attr, date):
        return d_attr
    try:
        return datetime.strptime(str(d_attr).strip(), "%Y-%m-%d").date()
    except:
        return date.today()

# ---------- DATA LOADING ----------
# A gyorsabb működés érdekében nem használunk cache-t a változó adatokra
st_data = sheet_allomasok.get_all_records()
log_data = sheet_naplo.get_all_records()
tech_data = sheet_tech.get_all_records()
vez_data = sheet_vezenyles.get_all_records()

tech_names = [t['Nev'] for t in tech_data if t.get('Nev')]

# ---------- SIDEBAR - ÚJ ADATBEVITEL ----------
st.sidebar.header("📝 Új hiba rögzítése")
with st.sidebar.form("hiba_form"):
    st_station = st.selectbox("Kút kiválasztása", [s['Nev'] for s in st_data])
    st_desc = st.text_input("Hiba leírása")
    st_date = st.date_input("Hiba észlelése", date.today())
    st_time = st.selectbox("Időpont", [f"{h:02d}:{m:02d}" for h in range(6,22) for m in (0,30)])
    if st.form_submit_button("Hiba Mentése"):
        sheet_naplo.append_row([st_station, str(st_date), st_desc, st_time])
        st.success("Mentve!")
        st.rerun()

st.sidebar.header("👷 Beosztás készítése")
with st.sidebar.form("vez_form"):
    sel_tech = st.selectbox("Technikus", tech_names)
    # Csak azokat a hibákat mutatjuk, amik a log_data-ban vannak
    hiba_options = [f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})" for l in log_data]
    sel_hiba = st.selectbox("Melyik hibára?", hiba_options) if hiba_options else st.selectbox("Nincs hiba", ["-"])
    sel_date = st.date_input("Munkavégzés napja", date.today())
    if st.form_submit_button("Beosztás Mentése"):
        sheet_vezenyles.append_row([sel_tech, sel_hiba.split(": ")[0], str(sel_date), sel_hiba])
        st.success("Vezényelve!")
        st.rerun()

# ---------- MAIN - NAPI LISTÁK ----------
st.title("🗺️ Karbantartási Vezénylő - Áttekintés")

if not log_data:
    st.info("Nincs rögzített hiba a rendszerben.")
else:
    # Aktív napok kigyűjtése
    unique_days = sorted(list(set(str(l['Datum']) for l in log_data)))
    cols = st.columns(len(unique_days))

    for col, day_str in zip(cols, unique_days):
        col.subheader(f"📅 {day_str}")
        
        # Hibák szűrése az adott napra
        for i, l in enumerate(log_data):
            if str(l['Datum']) == day_str:
                hiba_id = f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})"
                
                with col.expander(f"🔍 {l.get('Ido','--')} - {l['Allomas_Neve']}", expanded=True):
                    st.write(f"**Hiba:** {l['Leiras']}")
                    
                    # 1. Van-e beosztva valaki?
                    found_vez = False
                    for v_i, v in enumerate(vez_data):
                        if v.get('Hiba') == hiba_id:
                            found_vez = True
                            st.success(f"👷 {v['Technikus_Neve']}")
                            
                            # Technikus módosítása (index + 2 a fejléc miatt)
                            new_tech = st.selectbox("Csere", tech_names, 
                                                    index=tech_names.index(v['Technikus_Neve']) if v['Technikus_Neve'] in tech_names else 0,
                                                    key=f"tech_{day_str}_{i}_{v_i}")
                            if new_tech != v['Technikus_Neve']:
                                sheet_vezenyles.update_cell(v_i + 2, 1, new_tech)
                                st.rerun()
                            
                            # Tervezett dátum módosítása
                            new_v_date = st.date_input("Új ütemezés", safe_date(v['Datum']), key=f"vdate_{day_str}_{i}_{v_i}")
                            if str(new_v_date) != str(v['Datum']):
                                sheet_vezenyles.update_cell(v_i + 2, 3, str(new_v_date))
                                st.rerun()

                    if not found_vez:
                        st.warning("Nincs beosztva")

                    st.divider()
                    
                    # 2. Alap hiba módosítása (Naplo)
                    new_l_date = st.date_input("Hiba napja áthelyezése", safe_date(l['Datum']), key=f"ldate_{day_str}_{idx}")
                    if str(new_l_date) != str(l['Datum']):
                        sheet_naplo.update_cell(i + 2, 2, str(new_l_date))
                        st.rerun()

                    if st.button("Hiba Törlése", key=f"del_{day_str}_{i}", use_container_width=True):
                        sheet_naplo.delete_rows(i + 2)
                        st.rerun()

# ---------- TÉRKÉP MEGJELENÍTÉSE ----------
st.markdown("### 📍 Térképes nézet")
m = folium.Map(location=[47.1625, 19.5033], zoom_start=7)

for l in log_data:
    # Állomás keresése a koordinátákhoz
    stn_list = [s for s in st_data if s['Nev'] == l['Allomas_Neve']]
    if stn_list:
        stn = stn_list[0]
        hiba_id = f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})"
        is_vez = any(v.get('Hiba') == hiba_id for v in vez_data)

        folium.Marker(
            [stn['Lat'], stn['Lon']],
            popup=f"<b>{l['Allomas_Neve']}</b><br>{l['Leiras']}",
            tooltip=f"{l['Allomas_Neve']}",
            icon=folium.Icon(
                color="green" if is_vez else "red",
                icon="wrench" if is_vez else "exclamation",
                prefix="fa"
            )
        ).add_to(m)

st_folium(m, width=1200, height=500, returned_objects=[])