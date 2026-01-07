import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import folium
from streamlit_folium import st_folium
from datetime import date, datetime

# ---------- KONFIGURÁCIÓ ----------
st.set_page_config(layout="wide", page_title="Karbantartási Vezénylő")

SCOPE = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# ---------- ADATBÁZIS CSATLAKOZÁS ----------
@st.cache_resource
def get_gc():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPE)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Hitelesítési hiba: {e}")
        return None

gc = get_gc()
if gc:
    try:
        sh = gc.open("Terkep_Adatbazis")
        sheet_allomasok = sh.worksheet("Allomasok")
        sheet_naplo = sh.worksheet("Naplo")
        sheet_tech = sh.worksheet("Technikusok")
        sheet_vezenyles = sh.worksheet("Vezenylesek")
    except Exception as e:
        st.error(f"Sheet elérés hiba: {e}")
        st.stop()
else:
    st.stop()

# ---------- SEGÉDFÜGGVÉNYEK ----------
def safe_date(d_attr):
    """Kezeli a különböző dátumformátumokat és megvédi az appot az összeomlástól."""
    if isinstance(d_attr, date):
        return d_attr
    if not d_attr:
        return date.today()
    try:
        # Próbáljuk meg kinyerni a szövegből a dátumot
        return datetime.strptime(str(d_attr).strip(), "%Y-%m-%d").date()
    except:
        return date.today()

# Adatok betöltése
st_data = sheet_allomasok.get_all_records()
log_data = sheet_naplo.get_all_records()
tech_data = sheet_tech.get_all_records()
vez_data = sheet_vezenyles.get_all_records()
tech_names = [t['Nev'] for t in tech_data if t.get('Nev')]

# ---------- OLDALSÁV (SIDEBAR) ----------
st.sidebar.title("🛠️ Kezelőpanel")

# 1. Új hiba felvitele
with st.sidebar.expander("📝 Új hiba rögzítése", expanded=False):
    with st.form("new_fault"):
        f_station = st.selectbox("Kút", [s['Nev'] for s in st_data])
        f_desc = st.text_input("Leírás")
        f_date = st.date_input("Dátum", date.today())
        f_time = st.selectbox("Idő", [f"{h:02d}:{m:02d}" for h in range(6,22) for m in (0,30)])
        if st.form_submit_button("Mentés"):
            sheet_naplo.append_row([f_station, str(f_date), f_desc, f_time])
            st.rerun()

# 2. Beosztás készítése
with st.sidebar.expander("👷 Technikus vezénylése", expanded=False):
    with st.form("assign_tech"):
        v_tech = st.selectbox("Technikus", tech_names)
        hiba_list = [f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})" for l in log_data]
        v_hiba = st.selectbox("Melyik hiba?", hiba_list) if hiba_list else st.selectbox("Nincs hiba", ["-"])
        v_date = st.date_input("Munkavégzés napja", date.today())
        if st.form_submit_button("Beosztás"):
            sheet_vezenyles.append_row([v_tech, v_hiba.split(": ")[0], str(v_date), v_hiba])
            st.rerun()

# ---------- FŐOLDAL - MÁTRIX NÉZET ----------
st.title("📅 Napi Vezénylési Terv")

if not log_data:
    st.info("Nincs rögzített hiba.")
else:
    # Oszlopok létrehozása a rögzített hiba-napok alapján
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
                    
                    # Beosztás keresése (bármilyen dátumra is szól)
                    found_vez = False
                    for v_i, v in enumerate(vez_data):
                        if v.get('Hiba') == hiba_id:
                            found_vez = True
                            st.success(f"👷 {v['Technikus_Neve']}")
                            st.caption(f"📅 Ütemezve: {v['Datum']}")
                            
                            # Technikus csere
                            new_t = st.selectbox("Csere", tech_names, 
                                                 index=tech_names.index(v['Technikus_Neve']) if v['Technikus_Neve'] in tech_names else 0,
                                                 key=f"t_{day_str}_{i}_{v_i}")
                            if new_t != v['Technikus_Neve']:
                                sheet_vezenyles.update_cell(v_i + 2, 1, new_t)
                                st.rerun()
                                
                            # Ütemezett nap módosítása
                            new_vd = st.date_input("Új ütemezés", safe_date(v['Datum']), key=f"vd_{day_str}_{i}_{v_i}")
                            if str(new_vd) != str(v['Datum']):
                                sheet_vezenyles.update_cell(v_i + 2, 3, str(new_vd))
                                st.rerun()

                    if not found_vez:
                        st.warning("Nincs beosztva")

                    # Műveletek a hibával (Naplo)
                    with st.expander("⚙️ Szerkesztés"):
                        # Hiba napjának áthelyezése
                        new_ld = st.date_input("Hiba napja", safe_date(l['Datum']), key=f"ld_{day_str}_{i}")
                        if str(new_ld) != str(l['Datum']):
                            sheet_naplo.update_cell(i + 2, 2, str(new_ld))
                            st.rerun()

                        if st.button("🗑️ Törlés", key=f"del_{day_str}_{i}"):
                            sheet_naplo.delete_rows(i + 2)
                            st.rerun()

# ---------- TÉRKÉP ----------
st.divider()
st.subheader("📍 Helyszíni áttekintés")
m = folium.Map(location=[47.1625, 19.5033], zoom_start=7)

for l in log_data:
    # Koordináták kikeresése
    stn_match = [s for s in st_data if s['Nev'] == l['Allomas_Neve']]
    if stn_match:
        stn = stn_match[0]
        hiba_id = f"{l['Allomas_Neve']}: {l['Leiras']} ({l['Datum']})"
        is_vez = any(v.get('Hiba') == hiba_id for v in vez_data)
        
        folium.Marker(
            [stn['Lat'], stn['Lon']],
            popup=f"<b>{l['Allomas_Neve']}</b><br>{l['Leiras']}",
            icon=folium.Icon(color="green" if is_vez else "red", icon="wrench" if is_vez else "exclamation", prefix="fa")
        ).add_to(m)

st_folium(m, width=1200, height=500, returned_objects=[])