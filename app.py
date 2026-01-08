import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import datetime

# ================== KONFIG ==================
st.set_page_config(layout="wide", page_title="Karbantartási Vezénylő")

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ================== GOOGLE SHEETS ==================
@st.cache_resource
def get_spreadsheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPE
    )
    gc = gspread.authorize(creds)
    return gc.open("Terkep_Adatbazis")

@st.cache_data(ttl=60)
def load_data():
    sh = get_spreadsheet()
    return {
        "allomas": sh.worksheet("Allomasok").get_all_records(),
        "naplo": sh.worksheet("Naplo").get_all_records(),
        "technikus": sh.worksheet("Technikusok").get_all_records(),
        "vezeny": sh.worksheet("Vezenylesek").get_all_records()
    }

def run_and_refresh(func, *args):
    func(*args)
    st.cache_data.clear()
    st.rerun()

# ================== ADATBETÖLTÉS ==================
try:
    data = load_data()
    allomasok = data["allomas"]
    naplo = data["naplo"]
    technikusok = data["technikus"]
except Exception as e:
    st.error(f"❌ Adatbetöltési hiba: {e}")
    st.stop()

# ================== SIDEBAR ==================
st.sidebar.title("⚙️ Kezelőpanel")

with st.sidebar.expander("➕ Új állomás felvétele"):
    with st.form("uj_allomas"):
        nev = st.text_input("Állomás neve")
        tipus = st.selectbox("Típus", ["MOL", "ORLEN", "Egyéb"])
        lat = st.text_input("Szélesség (pl. 47.650587)")
        lon = st.text_input("Hosszúság (pl. 19.725236)")

        if st.form_submit_button("Mentés"):
            try:
                lat = float(lat.replace(",", "."))
                lon = float(lon.replace(",", "."))
                run_and_refresh(
                    get_spreadsheet().worksheet("Allomasok").append_row,
                    [nev, lat, lon, tipus]
                )
                st.success("✅ Állomás mentve")
            except Exception as e:
                st.error(f"Hibás koordináta: {e}")

# ================== TÉRKÉP ==================
st.header("🗺️ Állomások térképe")

m = folium.Map(location=[47.5, 19.0], zoom_start=7)

for a in allomasok:
    try:
        nev = a.get("Állomás neve") or a.get("Allomas neve") or "Ismeretlen"
        lat = float(str(a.get("Szélesség", "")).replace(",", "."))
        lon = float(str(a.get("Hosszúság", "")).replace(",", "."))

        folium.Marker(
            [lat, lon],
            popup=nev,
            icon=folium.Icon(color="blue", icon="info-sign")
        ).add_to(m)
    except:
        continue

st_folium(m, width=1200, height=600)

# ================== HIBÁK NAPLÓ ==================
st.header("📒 Hibák napló")

if naplo:
    st.dataframe(naplo, use_container_width=True)
else:
    st.info("Nincs hiba rögzítve")

