import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import date, datetime
import time

# ---------- KONFIGURÁCIÓ ----------
st.set_page_config(layout="wide", page_title="Karbantartási Vezénylő")

SCOPE = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# ---------- ADATBÁZIS KAPCSOLAT (OPTIMALIZÁLT) ----------
@st.cache_resource
def get_spreadsheet():
    """Egyszer nyitja meg a táblázatot és megőrzi a kapcsolatot."""
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPE)
    gc = gspread.authorize(creds)
    return gc.open("Terkep_Adatbazis")

# Adatok betöltése cache-el
@st.cache_data(ttl=60)
def load_data():
    sh = get_spreadsheet()
    return {
        "st": sh.worksheet("Allomasok").get_all_records(),
        "log": sh.worksheet("Naplo").get_all_records(),
        "tech": sh.worksheet("Technikusok").get_all_records(),
        "vez": sh.worksheet("Vezenylesek").get_all_records()
    }

# ---------- MŰVELETEK (HIBAKEZELÉSSEL) ----------
def run_operation(func, *args):
    """Biztonságos műveletvégzés: ha sok a kérés, vár és újrapróbálja."""
    try:
        func(*args)
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        if "429" in str(e):
            st.error("⚠️ Túl sok művelet egyszerre! Kérlek várj 10 másodpercet, majd frissítsd az oldalt.")
        else:
            st.error(f"Hiba történt: {e}")

# ---------- ADATOK ELŐKÉSZÍTÉSE ----------
try:
    sh = get_spreadsheet()
    data = load_data()
    st_data, log_data, tech_data, vez_data = data["st"], data["log"], data["tech"], data["vez"]
    tech_names = [t['Nev'] for t in tech_data if t.get('Nev')]
except Exception as e:
    st.error("A Google Sheets nem elérhető. Várj egy kicsit...")
    st.stop()

def safe_date(d_attr):
    if isinstance(d_attr, date): return d_attr
    try: return datetime.strptime(str(d_attr).strip(), "%Y-%m-%d").date()
    except: return date.today()

# ---------- OLDALSÁV (SIDEBAR) ----------
st.sidebar.title("🛠️ Kezelőpanel")
only_unplanned = st.sidebar.toggle("Csak a beütemezetlen munkák", value=False)

if st.sidebar.button("🔄 Kényszerített frissítés"):
    st.cache_data.clear()
    st.rerun()

# Új hiba felvitele
with st.sidebar.expander("📝 Új hiba rögzítése"):
    with st.form("new_fault", clear_on_submit=True):
        f_station = st.selectbox("Kút", [s['Nev'] for s in st_data])
        f_desc = st.text_input("Hiba leírása")
        f_date = st.date_input("Hiba napja", date.today())
        f_time = st.selectbox("Idő", [f"{h:02d}:{m:02d}" for h in range(6,22) for m in (0,30)])
        if st.form_submit_button("Mentés"):
            run_operation(sh.worksheet("Naplo").append_row, [f_station, str(f_date), f_desc, f_time])

# Beosztás készítése
with st.sidebar.expander("👷 Technikus vezénylése"):
    with st.form("assign_tech", clear_on_submit=True):
        v_tech = st.selectbox("Technikus", tech_names)
        hiba_list = [f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})" for l in log_data]
        v_hiba = st.selectbox("Melyik hiba?", hiba_list) if hiba_list else st.selectbox("Nincs hiba", ["-"])
        v_date = st.date_input("Munkavégzés napja", date.today())
        if st.form_submit_button("Beosztás"):
            run_operation(sh.worksheet("Vezenylesek").append_row, [v_tech, v_hiba.split(": ")[0], str(v_date), v_hiba])

# ---------- FŐOLDAL - ÖSSZES MUNKA ----------
st.title("📅 Összes munka")

display_data = []
for l in log_data:
    hiba_id = f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})"
    vez_info = next((v for v in vez_data if v.get('Hiba') == hiba_id), None)
    if only_unplanned and vez_info: continue
    display_data.append((l, vez_info))

if not display_data:
    st.info("Nincs megjeleníthető munka.")
else:
    unique_days = sorted(list(set(str(item[0]['Datum']) for item in display_data)))
    cols = st.columns(len(unique_days))

    for col, day_str in zip(cols, unique_days):
        col.markdown(f"### {day_str}")
        for i, (l, v) in enumerate(display_data):
            if str(l['Datum']) == day_str:
                hiba_id = f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})"
                with col.container(border=True):
                    st.markdown(f"**{l.get('Ido','--')} - {l['Allomas_Neve']}**")
                    st.caption(f"_{l['Leiras']}_")
                    
                    if v:
                        st.success(f"👷 {v['Technikus_Neve']} (Terv: {v['Datum']})")
                        # Módosítások
                        orig_v_idx = next((idx for idx, row in enumerate(vez_data) if row.get('Hiba') == hiba_id), None)
                        
                        new_t = st.selectbox("Technikus mód.", tech_names, 
                                             index=tech_names.index(v['Technikus_Neve']) if v['Technikus_Neve'] in tech_names else 0,
                                             key=f"t_mod_{day_str}_{i}")
                        if new_t != v['Technikus_Neve'] and orig_v_idx is not None:
                            run_operation(sh.worksheet("Vezenylesek").update_cell, orig_v_idx + 2, 1, new_t)

                        new_vd = st.date_input("Dátum mód.", safe_date(v['Datum']), key=f"vd_mod_{day_str}_{i}")
                        if str(new_vd) != str(v['Datum']) and orig_v_idx is not None:
                            run_operation(sh.worksheet("Vezenylesek").update_cell, orig_v_idx + 2, 3, str(new_vd))
                    else:
                        st.warning("Nincs beosztva")

                    with st.expander("⚙️"):
                        if st.button("🗑️ Törlés", key=f"del_{day_str}_{i}"):
                            orig_l_idx = next((idx for idx, row in enumerate(log_data) if f"{row['Allomas_Neve']}: {row['Leiras']} ({row['Datum']})" == hiba_id), None)
                            if orig_l_idx is not None:
                                run_operation(sh.worksheet("Naplo").delete_rows, orig_l_idx + 2)

# ---------- TÉRKÉP SZÁMOKKAL ----------
st.divider()
st.subheader("📍 Helyszíni áttekintés")
m = folium.Map(location=[47.1625, 19.5033], zoom_start=7)

station_summary = {}
for l in log_data:
    hiba_id = f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})"
    vez_info = any(v.get('Hiba') == hiba_id for v in vez_data)
    if only_unplanned and vez_info: continue
    
    s_name = l['Allomas_Neve']
    if s_name not in station_summary:
        stn_match = [s for s in st_data if s['Nev'] == s_name]
        if stn_match:
            station_summary[s_name] = {"coords": [stn_match[0]['Lat'], stn_match[0]['Lon']], "hibak": [], "kesz": True}
    
    if s_name in station_summary:
        station_summary[s_name]["hibak"].append(f"• {l['Leiras']}")
        if not vez_info: station_summary[s_name]["kesz"] = False

for s_name, info in station_summary.items():
    count = len(info['hibak'])
    color = "#27ae60" if info['kesz'] else "#e74c3c"
    icon_html = f'<div style="background-color: {color}; width: 30px; height: 30px; border-radius: 50%; border: 2px solid white; color: white; font-weight: bold; display: flex; justify-content: center; align-items: center; box-shadow: 0px 0px 5px rgba(0,0,0,0.5); font-size: 14px;">{count}</div>'
    
    folium.Marker(
        location=info['coords'],
        icon=folium.DivIcon(html=icon_html),
        popup=folium.Popup(f"<b>{s_name}</b><br>" + "<br>".join(info['hibak']), max_width=300),
        tooltip=f"{s_name}: {count} hiba"
    ).add_to(m)

st_folium(m, width=1200, height=500, returned_objects=[])