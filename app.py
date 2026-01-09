import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import pydeck as pdk
from datetime import date

# -----------------------------
# KONFIGURÁCIÓ
# -----------------------------
SPREADSHEET_ID = "1-kng7w3h8Us6Xr93Nk1kJ8zwuSocCadqJvyxpb7mhas"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# -----------------------------
# STREAMLIT UI SETUP (Ezt előre kell tenni)
# -----------------------------
st.set_page_config(page_title="Karbantartási vezénylő", layout="wide")
st.title("🛠️ Karbantartási vezénylő")

# -----------------------------
# GOOGLE AUTH ÉS KAPCSOLÓDÁS
# -----------------------------
# A secrets kezelése biztonságosan
if "gcp_service_account" not in st.secrets:
    st.error("Hiányzik a 'gcp_service_account' a secrets.toml fájlból vagy a Streamlit Cloud beállításaiból!")
    st.stop()

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPES
)

try:
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
except Exception as e:
    st.error(f"Hiba a Google Sheets csatlakozásnál: {e}")
    st.info("TIPP: Ellenőrizd, hogy megosztottad-e a táblázatot a Service Account e-mail címével (Szerkesztő joggal)!")
    st.stop()

# -----------------------------
# MUNKALAPOK DEFINIÁLÁSA
# -----------------------------
try:
    sheet_allomasok = sh.worksheet("Allomasok")
    sheet_naplo = sh.worksheet("Naplo")
    sheet_tech = sh.worksheet("Technikusok")
    sheet_vez = sh.worksheet("Vezenylesek")
except gspread.exceptions.WorksheetNotFound:
    st.error("Nem találom valamelyik munkalapot. Ellenőrizd a fülek neveit: Allomasok, Naplo, Technikusok, Vezenylesek")
    st.stop()

# -----------------------------
# ADATBETÖLTÉS (Cache-elve a sebességért)
# -----------------------------
@st.cache_data(ttl=10)  # 10 másodpercig megjegyzi az adatokat, nem kéri le újra feleslegesen
def load_data():
    return (
        sheet_allomasok.get_all_records(),
        sheet_naplo.get_all_records(),
        sheet_tech.get_all_records(),
        sheet_vez.get_all_records()
    )

# Adatok betöltése
allomasok, naplo, technikusok, vezenylesek = load_data()

# -----------------------------
# MENÜ
# -----------------------------
menu = st.sidebar.radio(
    "Menü",
    ["Térkép", "Állomás létrehozása", "Hiba rögzítése", "Vezénylés"]
)

# -----------------------------
# TÉRKÉP
# -----------------------------
if menu == "Térkép":
    st.subheader("📍 Állomások térképen")

    if not allomasok:
        st.info("Nincs még állomás rögzítve.")
    else:
        df = pd.DataFrame(allomasok)

        # Ellenőrizzük, hogy léteznek-e az oszlopok
        if "Lat" in df.columns and "Lon" in df.columns:
            df["Lat"] = pd.to_numeric(df["Lat"], errors="coerce")
            df["Lon"] = pd.to_numeric(df["Lon"], errors="coerce")
            df = df.dropna(subset=["Lat", "Lon"])

            if not df.empty:
                st.pydeck_chart(pdk.Deck(
                    initial_view_state=pdk.ViewState(
                        latitude=df["Lat"].mean(),
                        longitude=df["Lon"].mean(),
                        zoom=7
                    ),
                    layers=[
                        pdk.Layer(
                            "ScatterplotLayer",
                            data=df,
                            get_position="[Lon, Lat]",
                            get_radius=2000,  # Kicsit nagyobbra vettem, hogy jobban látsszon
                            get_fill_color=[255, 0, 0, 140], # Piros pöttyök
                            pickable=True
                        )
                    ]
                ))
            else:
                st.warning("Van adat, de a koordináták (Lat/Lon) hibásak vagy üresek.")
        else:
            st.warning("Hiányoznak a 'Lat' vagy 'Lon' oszlopok a táblázatból.")

    st.subheader("📝 Nyitott hibák")
    if naplo:
        for n in naplo:
            # Biztonsági ellenőrzés, hogy léteznek-e a kulcsok
            datum = n.get('Dátum', 'n.a.')
            nev = n.get('Állomás neve:', 'Ismeretlen') # A te kódodban kettőspont volt a fejlécben?
            leiras = n.get('Hiba leírása', '')
            statusz = n.get('Státusz', '')
            
            st.write(f"📅 {datum} – {nev} – {leiras} ({statusz})")
    else:
        st.info("Nincs rögzített hiba.")

# -----------------------------
# ÁLLOMÁS LÉTREHOZÁSA
# -----------------------------
elif menu == "Állomás létrehozása":
    st.subheader("➕ Új állomás")

    with st.form("allomas_form"):
        nev = st.text_input("Állomás neve")
        tipus = st.text_input("Típus")
        lat = st.text_input("Szélesség (pl. 47.650587)")
        lon = st.text_input("Hosszúság (pl. 19.725236)")
        submit = st.form_submit_button("Mentés")

        if submit:
            try:
                sheet_allomasok.append_row([
                    len(allomasok) + 1,
                    nev,
                    tipus,
                    lat,
                    lon
                ])
                st.success("Állomás mentve")
                st.cache_data.clear() # Töröljük a cache-t, hogy azonnal látsszon az új adat
                st.rerun() # Javítva experimental_rerun-ról
            except Exception as e:
                st.error(f"Hiba mentéskor: {e}")

# -----------------------------
# HIBA RÖGZÍTÉSE
# -----------------------------
elif menu == "Hiba rögzítése":
    st.subheader("🐞 Új hiba")

    # Biztonságos név kinyerés
    allomas_nevek = [a.get("Nev", "Névtelen") for a in allomasok] if allomasok else []

    with st.form("hiba_form"):
        allomas = st.selectbox("Állomás", allomas_nevek)
        hiba = st.text_area("Hiba leírása")
        submit = st.form_submit_button("Rögzítés")

        if submit:
            try:
                sheet_naplo.append_row([
                    str(date.today()),
                    allomas,
                    hiba,
                    "Nyitott",
                    ""
                ])
                st.success("Hiba rögzítve")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Hiba mentéskor: {e}")

# -----------------------------
# VEZÉNYLÉS
# -----------------------------
elif menu == "Vezénylés":
    st.subheader("📋 Technikus vezénylése")

    tech_nevek = [t.get("Név", "Névtelen") for t in technikusok] if technikusok else []
    allomas_nevek = [a.get("Nev", "Névtelen") for a in allomasok] if allomasok else []

    with st.form("vez_form"):
        tech = st.selectbox("Technikus", tech_nevek)
        allomas = st.selectbox("Állomás", allomas_nevek)
        hiba_text = st.text_area("Hiba")
        submit = st.form_submit_button("Vezénylés")

        if submit:
            try:
                sheet_vez.append_row([
                    tech,
                    allomas,
                    str(date.today()),
                    hiba_text
                ])
                st.success("Vezénylés mentve")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Hiba mentéskor: {e}")
