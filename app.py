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

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

st.set_page_config(page_title="Karbantartási vezénylő", layout="wide")
st.title("🛠️ Karbantartási vezénylő")

# -----------------------------
# GOOGLE AUTH
# -----------------------------
if "gcp_service_account" not in st.secrets:
    st.error("Hiányzik a 'gcp_service_account' a beállításokból!")
    st.stop()

creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
try:
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    sheet_allomasok = sh.worksheet("Allomasok")
    sheet_naplo = sh.worksheet("Naplo")
    sheet_tech = sh.worksheet("Technikusok")
    sheet_vez = sh.worksheet("Vezenylesek")
except Exception as e:
    st.error(f"Hiba a kapcsolódásnál: {e}")
    st.stop()

# -----------------------------
# ADATBETÖLTÉS
# -----------------------------
@st.cache_data(ttl=5)
def load_data():
    return (
        sheet_allomasok.get_all_records(),
        sheet_naplo.get_all_records(),
        sheet_tech.get_all_records(),
        sheet_vez.get_all_records()
    )

allomasok, naplo, technikusok, vezenylesek = load_data()

# -----------------------------
# MENÜ
# -----------------------------
menu = st.sidebar.radio("Menü", ["Térkép", "Állomás létrehozása", "Hiba rögzítése", "Vezénylés"])

# -----------------------------
# TÉRKÉP ÉS NYITOTT HIBÁK
# -----------------------------
if menu == "Térkép":
    st.subheader("📝 Nyitott hibák")
    if naplo:
        # A te táblázatodban: "Státusz"
        nyitott = [n for n in naplo if str(n.get("Státusz")).strip() == "Nyitott"]
        if nyitott:
            for n in nyitott:
                # Kijelezzük a fontosabb infókat
                st.warning(f"⚠️ **{n.get('Állomás neve:', 'Ismeretlen')}**: {n.get('Hiba leírása')} (Bejelentve: {n.get('Dátum')})")
        else:
            st.success("Nincs nyitott hiba!")
    else:
        st.info("A hibanapló üres.")

    st.subheader("📍 Állomások térképen")
    if allomasok:
        df = pd.DataFrame(allomasok)
        # Oszlopneveid: Lat, Lon
        df["Lat"] = pd.to_numeric(df["Lat"], errors="coerce")
        df["Lon"] = pd.to_numeric(df["Lon"], errors="coerce")
        df = df.dropna(subset=["Lat", "Lon"])
        
        if not df.empty:
            st.pydeck_chart(pdk.Deck(
                map_style='mapbox://styles/mapbox/dark-v10',
                initial_view_state=pdk.ViewState(latitude=df["Lat"].mean(), longitude=df["Lon"].mean(), zoom=7),
                layers=[pdk.Layer("ScatterplotLayer", data=df, get_position="[Lon, Lat]", get_radius=3000, get_fill_color=[255, 0, 0, 160], pickable=True)]
            ))
        else:
            st.info("Nincs koordináta az állomásokhoz.")

# -----------------------------
# HIBA RÖGZÍTÉSE
# -----------------------------
elif menu == "Hiba rögzítése":
    st.subheader("🐞 Új hiba bejelentése")
    # Oszlopneved: Nev
    allomas_nevek = [a.get("Nev", "Névtelen") for a in allomasok]
    
    with st.form("hiba_form"):
        allomas = st.selectbox("Állomás kiválasztása", allomas_nevek)
        hiba_leiras = st.text_area("Hiba leírása")
        
        st.write("⌛ **Határidő beállítása:**")
        col1, col2 = st.columns(2)
        h_datum = col1.date_input("Dátum", date.today())
        h_ido = col2.time_input("Időpont", time(12, 0))
        
        submit = st.form_submit_button("Hiba rögzítése")
        
        if submit:
            hatarido_szoveg = f"{h_datum} {h_ido.strftime('%H:%M')}"
            # Oszlopok a Naplo-ban: Dátum, Állomás neve:, Hiba leírása, Státusz, Technikus
            # Megjegyzés: A határidőt a "Hiba leírása" végéhez fűzöm, mert nincs külön oszlopod neki
            teljes_leiras = f"{hiba_leiras} | HATÁRIDŐ: {hatarido_szoveg}"
            
            sheet_naplo.append_row([
                str(date.today()), 
                allomas, 
                teljes_leiras, 
                "Nyitott", 
                "" # Technikus üresen marad rögzítéskor
            ])
            st.success("Hiba rögzítve!")
            st.cache_data.clear()

# -----------------------------
# VEZÉNYLÉS
# -----------------------------
elif menu == "Vezénylés":
    st.subheader("📋 Technikus vezénylése")
    # Oszlopneveid: Név (Technikusok), Nev (Allomasok)
    tech_nevek = [t.get("Név", "Névtelen") for t in technikusok]
    allomas_nevek = [a.get("Nev", "Névtelen") for a in allomasok]

    with st.form("vez_form"):
        tech = st.selectbox("Technikus", tech_nevek)
        allomas = st.selectbox("Állomás", allomas_nevek)
        kivonulas_nap = st.date_input("Kivonulás napja", date.today())
        feladat = st.text_area("Feladat leírása")
        
        submit = st.form_submit_button("Vezénylés mentése")
        
        if submit:
            # Oszlopok a Vezenylesek-ben: Technikus_Neve, Allomas_Neve, Datum, Hiba
            sheet_vez.append_row([
                tech, 
                allomas, 
                str(kivonulas_nap), 
                feladat
            ])
            st.success("Vezénylés rögzítve a táblázatba!")
            st.cache_data.clear()

# -----------------------------
# ÁLLOMÁS LÉTREHOZÁSA
# -----------------------------
elif menu == "Állomás létrehozása":
    st.subheader("➕ Új állomás rögzítése")
    with st.form("allomas_form"):
        nev = st.text_input("Állomás neve")
        tipus = st.text_input("Típus")
        lat = st.text_input("Szélesség (Lat)")
        lon = st.text_input("Hosszúság (Lon)")
        
        if st.form_submit_button("Mentés"):
            # Oszlopok: ID, Nev, Tipus, Lat, Lon
            uj_id = len(allomasok) + 1
            sheet_allomasok.append_row([uj_id, nev, tipus, lat, lon])
            st.success(f"'{nev}' állomás mentve!")
            st.cache_data.clear()
