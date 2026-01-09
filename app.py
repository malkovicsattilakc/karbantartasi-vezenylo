import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import pydeck as pdk
from datetime import date

# -----------------------------
# KONFIG
# -----------------------------
SPREADSHEET_ID = "1-kng7w3h8Us6Xr93Nk1kJ8zwuSocCadqJvyxpb7mhas"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# -----------------------------
# GOOGLE AUTH
# -----------------------------
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPES
)

gc = gspread.authorize(creds)
sh = gc.open_by_key(SPREADSHEET_ID)

# -----------------------------
# WORKSHEETS
# -----------------------------
sheet_allomasok = sh.worksheet("Allomasok")
sheet_naplo = sh.worksheet("Naplo")
sheet_tech = sh.worksheet("Technikusok")
sheet_vez = sh.worksheet("Vezenylesek")

# -----------------------------
# ADATBETÖLTÉS
# -----------------------------
def load_data():
    return (
        sheet_allomasok.get_all_records(),
        sheet_naplo.get_all_records(),
        sheet_tech.get_all_records(),
        sheet_vez.get_all_records()
    )

allomasok, naplo, technikusok, vezenylesek = load_data()

# -----------------------------
# STREAMLIT UI
# -----------------------------
st.set_page_config(page_title="Karbantartási vezénylő", layout="wide")
st.title("🛠️ Karbantartási vezénylő")

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

        df["Lat"] = pd.to_numeric(df["Lat"], errors="coerce")
        df["Lon"] = pd.to_numeric(df["Lon"], errors="coerce")
        df = df.dropna(subset=["Lat", "Lon"])

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
                    get_radius=200,
                    pickable=True
                )
            ]
        ))

    st.subheader("📝 Nyitott hibák")
    for n in naplo:
        st.write(
            f"📅 {n['Dátum']} – {n['Állomás neve:']} – {n['Hiba leírása']} ({n['Státusz']})"
        )

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
            sheet_allomasok.append_row([
                len(allomasok) + 1,
                nev,
                tipus,
                lat,
                lon
            ])
            st.success("Állomás mentve")
            st.experimental_rerun()

# -----------------------------
# HIBA RÖGZÍTÉSE
# -----------------------------
elif menu == "Hiba rögzítése":
    st.subheader("🐞 Új hiba")

    allomas_nevek = [a["Nev"] for a in allomasok]

    with st.form("hiba_form"):
        allomas = st.selectbox("Állomás", allomas_nevek)
        hiba = st.text_area("Hiba leírása")
        submit = st.form_submit_button("Rögzítés")

        if submit:
            sheet_naplo.append_row([
                str(date.today()),
                allomas,
                hiba,
                "Nyitott",
                ""
            ])
            st.success("Hiba rögzítve")
            st.experimental_rerun()

# -----------------------------
# VEZÉNYLÉS
# -----------------------------
elif menu == "Vezénylés":
    st.subheader("📋 Technikus vezénylése")

    tech_nevek = [t["Név"] for t in technikusok]
    allomas_nevek = [a["Nev"] for a in allomasok]

    with st.form("vez_form"):
        tech = st.selectbox("Technikus", tech_nevek)
        allomas = st.selectbox("Állomás", allomas_nevek)
        hiba = st.text_area("Hiba")
        submit = st.form_submit_button("Vezénylés")

        if submit:
            sheet_vez.append_row([
                tech,
                allomas,
                str(date.today()),
                hiba
            ])
            st.success("Vezénylés mentve")
            st.experimental_rerun()
