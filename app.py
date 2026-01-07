import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import date

# --- Ellenőrző rész ---
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

try:
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPE
    )
    gc = gspread.authorize(creds)

    # Próbáljuk meg megnyitni a Sheet-et
    sh = gc.open("Terkep_Adatbazis")
    st.success("🎉 A Google Sheet elérhető! A kapcsolat működik.")
except Exception as e:
    st.error(f"⚠️ Hiba a Sheet elérésében: {e}")

# ---------- GOOGLE AUTH ----------
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPE
)
gc = gspread.authorize(creds)

# ---------- SHEETS ----------
sh = gc.open("Terkep_Adatbazis")
sheet_allomasok = sh.worksheet("Allomasok")
sheet_naplo = sh.worksheet("Naplo")
sheet_tech = sh.worksheet("Technikusok")
sheet_vezenyles = sh.worksheet("Vezenylesek")

# ---------- DATA ----------
def load_all():
    return (
        sheet_allomasok.get_all_records(),
        sheet_naplo.get_all_records(),
        sheet_tech.get_all_records(),
        sheet_vezenyles.get_all_records()
    )

# ---------- OPERATIONS ----------
def save_work(station, d, desc, t):
    sheet_naplo.append_row([station, str(d), desc, t])

def save_assign(tech, station, d, hiba):
    sheet_vezenyles.append_row([tech, station, str(d), hiba])

def update_assign(idx, tech):
    sheet_vezenyles.update_cell(idx + 2, 1, tech)

def update_assign_date(idx, d):
    sheet_vezenyles.update_cell(idx + 2, 3, str(d))

def delete_task(idx):
    sheet_naplo.delete_rows(idx + 2)

def move_task_date(idx, d):
    sheet_naplo.update_cell(idx + 2, 2, str(d))

# ---------- UI ----------
st.set_page_config(layout="wide", page_title="Karbantartási Vezénylő")

st.title("🗺️ Karbantartási Vezénylő")

st_data, log_data, tech_data, vez_data = load_all()
tech_names = [t['Nev'] for t in tech_data]

# --- SIDEBAR ---
st.sidebar.header("📝 Új hiba")
st_station = st.sidebar.selectbox("Kút", [s['Nev'] for s in st_data])
st_desc = st.sidebar.text_input("Hiba")
st_date = st.sidebar.date_input("Hiba napja", date.today())
st_time = st.sidebar.selectbox(
    "Idő",
    [f"{h:02d}:{m:02d}" for h in range(6,22) for m in (0,30)]
)

if st.sidebar.button("Mentés"):
    save_work(st_station, st_date, st_desc, st_time)
    st.experimental_rerun()

st.sidebar.header("👷 Beosztás")
sel_tech = st.sidebar.selectbox("Technikus", tech_names)
sel_hiba = st.sidebar.selectbox(
    "Hiba",
    [f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})" for l in log_data]
)
sel_date = st.sidebar.date_input("Mikorra", date.today())

if st.sidebar.button("Beosztás"):
    save_assign(sel_tech, sel_hiba.split(": ")[0], sel_date, sel_hiba)
    st.experimental_rerun()

# --- MAIN ---
cols = st.columns(len(set(l['Datum'] for l in log_data)) or 1)

for col, day in zip(cols, sorted(set(l['Datum'] for l in log_data))):
    col.markdown(f"### 📅 {day}")

    for i, l in enumerate(log_data):
        if l['Datum'] != day:
            continue

        hiba_id = f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})"

        with col.container():
            st.markdown(f"**{l.get('Ido','08:00')} – {l['Allomas_Neve']}**")
            st.caption(l['Leiras'])

            for v_i, v in enumerate(vez_data):
                if v['Hiba'] == hiba_id:
                    new_tech = st.selectbox(
                        "Technikus",
                        tech_names,
                        index=tech_names.index(v['Technikus_Neve']),
                        key=f"t{v_i}"
                    )
                    if st.button("Csere", key=f"c{v_i}"):
                        update_assign(v_i, new_tech)
                        st.experimental_rerun()

                    new_d = st.date_input(
                        "Ütemezett dátum",
                        date.fromisoformat(v['Datum']),
                        key=f"d{v_i}"
                    )
                    if st.button("Idő mód.", key=f"m{v_i}"):
                        update_assign_date(v_i, new_d)
                        st.experimental_rerun()

            new_d = st.date_input("Hiba napjának módosítása",
                                  date.fromisoformat(day),
                                  key=f"mv{i}")
            if st.button("Áthelyez", key=f"mvb{i}"):
                move_task_date(i, new_d)
                st.experimental_rerun()

            if st.button("Törlés", key=f"del{i}"):
                delete_task(i)
                st.experimental_rerun()

# --- MAP ---
m = folium.Map(location=[47.1625, 19.5033], zoom_start=7)

for l in log_data:
    stn = next(s for s in st_data if s['Nev'] == l['Allomas_Neve'])
    hiba_id = f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})"
    is_vez = any(v['Hiba'] == hiba_id for v in vez_data)

    folium.Marker(
        [stn['Lat'], stn['Lon']],
        popup=f"{l['Allomas_Neve']} – {l['Leiras']}",
        icon=folium.Icon(
            color="green" if is_vez else "red",
            icon="wrench" if is_vez else "exclamation",
            prefix="fa"
        )
    ).add_to(m)

st_folium(m, width=1200)
