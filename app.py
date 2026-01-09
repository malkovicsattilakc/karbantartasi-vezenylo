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
# SHEETS
# ======================
SPREADSHEET_NAME = "Terkep_Adatbazis"

SPREADSHEET_ID = "1-kng7w3h8Us6Xr93Nk1kJ8zwuSocCadqJvyxpb7mhas"
sh = gc.open_by_key(SPREADSHEET_ID)
sheet_naplo = sh.worksheet("Naplo")
sheet_tech = sh.worksheet("Technikusok")
sheet_vez = sh.worksheet("Vezenylesek")

# ======================
# LOAD DATA
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
# UI
# ======================
st.set_page_config(layout="wide")
st.title("🗺️ Karbantartási vezénylő")

# ======================
# ÚJ ÁLLOMÁS
# ======================
with st.expander("➕ Új állomás"):
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
with st.expander("📝 Új hiba"):
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

    nyitott_hibak = []
    for n in naplo:
        if n.get("Státusz") != "NYITOTT":
            continue

        allomas_nev = n.get("Állomás neve:") or n.get("Állomás neve")
        hiba_leiras = n.get("Hiba leírása")
        datum = n.get("Dátum")

        if not allomas_nev or not hiba_leiras or not datum:
            continue

        nyitott_hibak.append(
            f"{allomas_nev} – {hiba_leiras} ({datum})"
        )

    if nyitott_hibak:
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

            for i, n in enumerate(naplo):
                aid = f"{(n.get('Állomás neve:') or n.get('Állomás neve'))} – {n.get('Hiba leírása')} ({n.get('Dátum')})"
                if aid == v_hiba:
                    sheet_naplo.update_cell(i + 2, 4, "BEOSZTVA")
                    sheet_naplo.update_cell(i + 2, 5, v_tech)

            st.success("Vezénylés mentve")
            st.rerun()
    else:
        st.info("Nincs nyitott hiba")

# ======================
# TÉRKÉP
# ======================
st.subheader("🗺️ Aktív hibák térképen")

m = folium.Map(location=[47.2, 19.4], zoom_start=7)

for n in naplo:
    allomas_nev = n.get("Állomás neve:") or n.get("Állomás neve")
    if not allomas_nev:
        continue

    allomas = next(
        (a for a in allomasok if a["Nev"] == allomas_nev),
        None
    )
    if not allomas:
        continue

    try:
        lat = float(allomas["Lat"])
        lon = float(allomas["Lon"])
    except:
        continue

    szin = "green" if n.get("Státusz") == "BEOSZTVA" else "red"

    folium.Marker(
        [lat, lon],
        popup=f"""
        <b>{allomas_nev}</b><br>
        {n.get('Hiba leírása')}<br>
        Státusz: {n.get('Státusz')}<br>
        Technikus: {n.get('Technikus')}
        """,
        icon=folium.Icon(color=szin, icon="wrench", prefix="fa")
    ).add_to(m)

st_folium(m, height=500)

