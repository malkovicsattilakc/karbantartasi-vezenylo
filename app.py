import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import datetime

# ---------------- KONFIG ----------------
st.set_page_config(layout="wide", page_title="Karbantartási Vezénylő")

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ---------------- GOOGLE SHEETS ----------------
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
        "vezenyles": sh.worksheet("Vezenylesek").get_all_records()
    }

def run_and_refresh(func, *args):
    func(*args)
    st.cache_data.clear()
    st.rerun()

# ---------------- ADATBETÖLTÉS ----------------
try:
    sh = get_spreadsheet()
    data = load_data()
    allomasok = data["allomas"]
    naplo = data["naplo"]
    technikusok = data["technikus"]
except Exception as e:
    st.error(f"Adatbázis hiba: {e}")
    st.stop()

# ---------------- SIDEBAR ----------------
st.sidebar.title("🛠 Kezelőpanel")

# ---- ÚJ ÁLLOMÁS ----
with st.sidebar.expander("➕ Új állomás felvétele"):
    with st.form("uj_allomas"):
        nev = st.text_input("Állomás neve")

        lat = st.number_input(
            "Szélesség (Latitude)",
            format="%.6f",
            value=47.650587
        )

        lon = st.number_input(
            "Hosszúság (Longitude)",
            format="%.6f",
            value=19.725236
        )

        tipus = st.selectbox("Típus", ["MOL", "ORLEN", "Egyéb"])

        if st.form_submit_button("Mentés"):
            if nev:
                run_and_refresh(
                    sh.worksheet("Allomasok").append_row,
                    [nev, float(lat), float(lon), tipus]
                )
            else:
                st.warning("Állomás neve kötelező")

# ---------------- TÉRKÉP ----------------
st.title("📍 Állomások térképen")

m = folium.Map(location=[47.2, 19.5], zoom_start=7)

for a in allomasok:
    try:
        lat = float(a["Szélesség"])
        lon = float(a["Hosszúság"])
        folium.Marker(
            [lat, lon],
            popup=f"{a['Állomás_Neve']} ({a.get('Típus','')})"
        ).add_to(m)
    except:
        continue

st_folium(m, width=1200, height=600)

# ---------------- NAPLÓ ----------------
st.divider()
st.header("📒 Hibák napló")

with st.form("uj_hiba"):
    allomas_nev = st.selectbox(
        "Állomás",
        [a["Állomás_Neve"] for a in allomasok]
    )
    leiras = st.text_area("Hiba leírása")

    if st.form_submit_button("Hiba rögzítése"):
        if leiras:
            run_and_refresh(
                sh.worksheet("Naplo").append_row,
                [datetime.now().isoformat(), allomas_nev, leiras]
            )
        else:
            st.warning("Leírás kötelező")

st.dataframe(naplo)
