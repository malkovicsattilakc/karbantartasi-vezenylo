import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import date, datetime

# ---------- KONFIGURÁCIÓ ----------
st.set_page_config(layout="wide", page_title="Karbantartási Vezénylő")

SCOPE = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# ---------- ADATBÁZIS CSATLAKOZÁS ÉS CACHE ----------
@st.cache_resource
def get_gc():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPE)
    return gspread.authorize(creds)

# ADATOK BETÖLTÉSE CACHE-EL (TTL = 60 másodperc)
# Ez azt jelenti, hogy 1 percen belül nem hívja újra a Google-t, csak a memóriából dolgozik.
@st.cache_data(ttl=60)
def load_data():
    gc = get_gc()
    sh = gc.open("Terkep_Adatbazis")
    return {
        "st": sh.worksheet("Allomasok").get_all_records(),
        "log": sh.worksheet("Naplo").get_all_records(),
        "tech": sh.worksheet("Technikusok").get_all_records(),
        "vez": sh.worksheet("Vezenylesek").get_all_records()
    }

# Segédfüggvény az íráshoz (ezeknél töröljük a cache-t, hogy látszódjon a változás)
def get_sheets():
    gc = get_gc()
    sh = gc.open("Terkep_Adatbazis")
    return sh

# ---------- FŐ PROGRAMKÓD ----------
try:
    data = load_data()
    st_data = data["st"]
    log_data = data["log"]
    tech_data = data["tech"]
    vez_data = data["vez"]
    tech_names = [t['Nev'] for t in tech_data if t.get('Nev')]
except Exception as e:
    st.error("Hiba az adatok betöltésekor. Próbáld frissíteni az oldalt.")
    st.stop()

# ---------- SEGÉDFÜGGVÉNYEK ----------
def safe_date(d_attr):
    if isinstance(d_attr, date): return d_attr
    try: return datetime.strptime(str(d_attr).strip(), "%Y-%m-%d").date()
    except: return date.today()

# ---------- OLDALSÁV (SIDEBAR) ----------
st.sidebar.title("🛠️ Kezelőpanel")

# Kézi frissítés gomb (Törli a cache-t és újraolvas)
if st.sidebar.button("🔄 Adatok kényszerített frissítése"):
    st.cache_data.clear()
    st.rerun()

# 1. Új hiba felvitele
with st.sidebar.expander("📝 Új hiba rögzítése"):
    with st.form("new_fault", clear_on_submit=True):
        f_station = st.selectbox("Kút", [s['Nev'] for s in st_data])
        f_desc = st.text_input("Leírás")
        f_date = st.date_input("Dátum", date.today())
        f_time = st.selectbox("Idő", [f"{h:02d}:{m:02d}" for h in range(6,22) for m in (0,30)])
        if st.form_submit_button("Mentés"):
            get_sheets().worksheet("Naplo").append_row([f_station, str(f_date), f_desc, f_time])
            st.cache_data.clear() # Frissítjük a memóriát
            st.rerun()

# 2. Beosztás készítése
with st.sidebar.expander("👷 Technikus vezénylése"):
    with st.form("assign_tech", clear_on_submit=True):
        v_tech = st.selectbox("Technikus", tech_names)
        hiba_list = [f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})" for l in log_data]
        v_hiba = st.selectbox("Melyik hiba?", hiba_list) if hiba_list else st.selectbox("Nincs hiba", ["-"])
        v_date = st.date_input("Munkavégzés napja", date.today())
        if st.form_submit_button("Beosztás"):
            get_sheets().worksheet("Vezenylesek").append_row([v_tech, v_hiba.split(": ")[0], str(v_date), v_hiba])
            st.cache_data.clear()
            st.rerun()

# ---------- FŐOLDAL - MÁTRIX NÉZET ----------
st.title("📅 Napi Vezénylési Terv")

if not log_data:
    st.info("Nincs rögzített hiba.")
else:
    unique_days = sorted(list(set(str(l['Datum']) for l in log_data)))
    cols = st.columns(len(unique_days))

    for col, day_str in zip(cols, unique_days):
        col.markdown(f"### {day_str}")
        for i, l in enumerate(log_data):
            if str(l['Datum']) == day_str:
                hiba_id = f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})"
                with col.container(border=True):
                    st.markdown(f"**{l.get('Ido','--')} - {l['Allomas_Neve']}**")
                    st.caption(f"_{l['Leiras']}_")
                    
                    found_vez = False
                    for v_i, v in enumerate(vez_data):
                        if v.get('Hiba') == hiba_id:
                            found_vez = True
                            st.success(f"👷 {v['Technikus_Neve']}")
                            st.caption(f"📅 Tervezve: {v['Datum']}")
                    
                    if not found_vez:
                        st.warning("Nincs beosztva")

                    # Szerkesztési funkciók
                    with st.expander("⚙️"):
                        if st.button("🗑️ Törlés", key=f"del_{day_str}_{i}"):
                            get_sheets().worksheet("Naplo").delete_rows(i + 2)
                            st.cache_data.clear()
                            st.rerun()

# ---------- TÉRKÉP ----------
st.divider()
m = folium.Map(location=[47.1625, 19.5033], zoom_start=7)
for l in log_data:
    stn_match = [s for s in st_data if s['Nev'] == l['Allomas_Neve']]
    if stn_match:
        stn = stn_match[0]
        hiba_id = f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})"
        is_vez = any(v.get('Hiba') == hiba_id for v in vez_data)
        folium.Marker(
            [stn['Lat'], stn['Lon']],
            popup=f"{l['Allomas_Neve']}",
            icon=folium.Icon(color="green" if is_vez else "red", icon="wrench" if is_vez else "exclamation", prefix="fa")
        ).add_to(m)
st_folium(m, width=1200, height=500, returned_objects=[])