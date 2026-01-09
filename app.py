import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date
import folium
from streamlit_folium import st_folium

# ======================
# GOOGLE AUTH
# ======================
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPE
)

gc = gspread.authorize(creds)

# ======================
# SHEETEK
# ======================
SPREADSHEET_NAME = "Terkep_Adatbazis"

sh = gc.open(SPREADSHEET_NAME)
sheet_allomasok = sh.worksheet("Allomasok")
sheet_naplo = sh.worksheet("Naplo")
sheet_tech = sh.worksheet("Technikusok")
sheet_vez = sh.worksheet("Vezenylesek")

# ======================
# ADATBETÖLTÉS
# ======================
def load_data():
    return (
        sheet_allomasok.get_all_records(),
        sheet_naplo.get_all_records(),
        sheet_tech.get_all_records(),
        sheet_vez.get_all_records()
    )

allomasok, naplo, technikusok, vezenylesek = load_data()

# ======================
# UI – CÍM
# ======================
st.set_page_config(layout="wide")
st.title("🗺️ Karbantartási vezénylő – Streamlit")

# ======================
# ÚJ ÁLLOMÁS
# ======================
with st.expander("➕ Új állomás rögzítése"):
    nev = st.text_input("Állomás neve")
    tipus = st.selectbox("Típus", ["MOL", "Egyéb"])
    lat = st.text_input("Szélesség (pl. 47.650587)")
    lon = st.text_input("Hosszúság (pl. 19.725236)")

    if st.button("Állomás mentése"):
        try:
            sheet_allomasok.append_row([
                "",
                nev,
                tipus,
                float(lat.replace(",", ".")),
                float(lon.replace(",", "."))
            ])
            st.success("Állomás mentve")
            st.rerun()
        except Exception as e:
            st.error(f"Hiba: {e}")

# ======================
# ÚJ HIBA
# ======================
with st.expander("📝 Új hiba rögzítése"):
    allomas_nevek = [a["Nev"] for a in allomasok]

    h_allomas = st.selectbox("Állomás", allomas_nevek)
    h_datum = st.date_input("Dátum", date.today())
    h_leiras = st.text_input("Hiba leírása")

    if st.button("Hiba mentése"):
        sheet_naplo.append_row([
            str(h_datum),
            h_allomas,
            h_leiras,
            "NYITOTT",
            ""
        ])
        st.success("Hiba rögzítve")
        st.rerun()

# ======================
# VEZÉNYLÉS
# ======================
with st.expander("👷 Technikus vezénylés"):
    tech_nevek = [t["Név"] for t in technikusok]

    nyitott_hibak = [
        f"{n['Állomás neve:']} – {n['Hiba leírása']} ({n['Dátum']})"
        for n in naplo if n["Státusz"] == "NYITOTT"
    ]

    v_tech = st.selectbox("Technikus", tech_nevek)
    v_hiba = st.selectbox("Hiba", nyitott_hibak)
    v_datum = st.date_input("Ütemezett dátum", date.today())

    if st.button("Vezénylés mentése"):
        allomas_nev = v_hiba.split(" – ")[0]

        sheet_vez.append_row([
            v_tech,
            allomas_nev,
            str(v_datum),
            v_hiba
        ])

        # Napló frissítés
        for i, row in enumerate(naplo):
            hiba_id = f"{row['Állomás neve:']} – {row['Hiba leírása']} ({row['Dátum']})"
            if hiba_id == v_hiba:
                sheet_naplo.update_cell(i + 2, 4, "BEOSZTVA")
                sheet_naplo.update_cell(i + 2, 5, v_tech)

        st.success("Vezénylés rögzítve")
        st.rerun()

# ======================
# TÉRKÉP
# ======================
st.subheader("🗺️ Aktív hibák térképen")

m = folium.Map(location=[47.2, 19.4], zoom_start=7)

for n in naplo:
    allomas = next(
        (a for a in allomasok if a["Nev"] == n["Állomás neve:"]),
        None
    )

    if not allomas:
        continue

    try:
        lat = float(allomas["Lat"])
        lon = float(allomas["Lon"])
    except:
        continue

    szin = "green" if n["Státusz"] == "BEOSZTVA" else "red"

    folium.Marker(
        [lat, lon],
        popup=f"""
        <b>{n['Állomás neve:']}</b><br>
        {n['Hiba leírása']}<br>
        Státusz: {n['Státusz']}<br>
        Technikus: {n['Technikus']}
        """,
        icon=folium.Icon(color=szin, icon="wrench", prefix="fa")
    ).add_to(m)

st_folium(m, height=500)
