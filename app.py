import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime, date
import uuid

# --- 1. Konfiguráció és Adatbetöltés ---
st.set_page_config(layout="wide", page_title="Munkatervező Dashboard")

# Minta adatbetöltés (A valóságban itt olvassuk be a CSV-t vagy Google Sheet-et)
@st.cache_data
def load_locations():
    # Itt próbáljuk meg betölteni a feltöltött fájlt, ha létezik, különben üres df
    try:
        # Feltételezzük, hogy a fájl neve 'allomasok.csv' a projekt mappában
        # A felhasználó által megadott struktúra: ID, Nev, Tipus, Lat, Lon
        df = pd.read_csv("allomasok.csv") 
        # Biztosítjuk, hogy a koordináták számok legyenek
        df['Lat'] = pd.to_numeric(df['Lat'], errors='coerce')
        df['Lon'] = pd.to_numeric(df['Lon'], errors='coerce')
        return df
    except FileNotFoundError:
        # Ha nincs fájl, létrehozunk egy demo adatsort a prompt alapján
        data = {
            'ID': ['Abony', 'Nagylak', 'PÉCS'],
            'Nev': ['Abony', 'Nagylak', 'PÉCS'],
            'Tipus': ['MOL', 'ORLEN', 'Egyéb'], # Demo típusok
            'Lat': [47.18874, 46.167993, 46.065023],
            'Lon': [20.00478, 20.706045, 18.180011]
        }
        return pd.DataFrame(data)

# Session State inicializálása (Adatbázis szimuláció)
if 'tasks' not in st.session_state:
    st.session_state.tasks = []
    # Demo adat
    st.session_state.tasks.append({
        'id': str(uuid.uuid4()),
        'location_id': 'Abony',
        'desc': 'Szivárgás a 2-es kútnál',
        'deadline_date': date.today(),
        'deadline_time': datetime.now().time(),
        'status': 'active', # active, assigned, revisit
        'tech_name': None,
        'work_date': None,
        'revisit_flag': False
    })

if 'locations' not in st.session_state:
    st.session_state.locations = load_locations()

# --- Segédfüggvények ---
def save_task(location_id, desc, d_date, d_time):
    st.session_state.tasks.append({
        'id': str(uuid.uuid4()),
        'location_id': location_id,
        'desc': desc,
        'deadline_date': d_date,
        'deadline_time': d_time,
        'status': 'active',
        'tech_name': None,
        'work_date': None,
        'revisit_flag': False
    })

def update_task_status(task_id, new_status, tech_name=None, work_date=None):
    for task in st.session_state.tasks:
        if task['id'] == task_id:
            task['status'] = new_status
            if tech_name: task['tech_name'] = tech_name
            if work_date: task['work_date'] = work_date
            if new_status == 'revisit':
                task['revisit_flag'] = True
                task['tech_name'] = None # Töröljük a régi technikust
                task['work_date'] = None
            break

def delete_task(task_id):
    st.session_state.tasks = [t for t in st.session_state.tasks if t['id'] != task_id]

def add_location(loc_id, loc_type, lat, lon):
    new_row = pd.DataFrame([{'ID': loc_id, 'Nev': loc_id, 'Tipus': loc_type, 'Lat': lat, 'Lon': lon}])
    st.session_state.locations = pd.concat([st.session_state.locations, new_row], ignore_index=True)

# --- UI Layout ---

st.title("🔧 Feladatirányítási Rendszer")

tabs = st.tabs(["📋 Irányítópult", "➕ Új Feladat", "🗺️ Térkép", "📍 Új Cím"])

# --- 1. TAB: IRÁNYÍTÓPULT ---
with tabs[0]:
    st.header("Aktív hibák irányítópultja")
    
    # Csak az aktív vagy kiosztott vagy visszatérős feladatokat listázzuk
    active_tasks = [t for t in st.session_state.tasks]
    
    if not active_tasks:
        st.info("Nincs aktív feladat.")
    else:
        # Dátumok kinyerése az oszlopokhoz
        unique_dates = sorted(list(set([t['deadline_date'] for t in active_tasks])))
        
        cols = st.columns(len(unique_dates))
        
        for idx, d_date in enumerate(unique_dates):
            with cols[idx]:
                st.subheader(d_date.strftime("%Y-%m-%d"))
                # Feladatok szűrése az adott napra és rendezés idő szerint
                day_tasks = [t for t in active_tasks if t['deadline_date'] == d_date]
                day_tasks.sort(key=lambda x: x['deadline_time'])
                
                for task in day_tasks:
                    # Kártya stílus
                    with st.container(border=True):
                        loc_info = st.session_state.locations[st.session_state.locations['ID'] == task['location_id']]
                        loc_type = loc_info['Tipus'].values[0] if not loc_info.empty else "Ismeretlen"
                        
                        # Fejléc: Időpont és Helyszín
                        st.markdown(f"**⏰ {task['deadline_time'].strftime('%H:%M')}** - {task['location_id']} ({loc_type})")
                        st.text(task['desc'])
                        
                        # Státusz jelzések
                        if task['revisit_flag']:
                            st.warning("⚠️ VISSZAMENNI!")
                        
                        if task['status'] == 'assigned':
                            st.success(f"👷 {task['tech_name']} | 📅 {task['work_date']}")
                        
                        # Gombok / Aciók
                        c1, c2 = st.columns(2)
                        
                        # Kiosztás / Ütemezés
                        with st.expander("Kiosztás / Módosítás"):
                            with st.form(key=f"assign_{task['id']}"):
                                tech_input = st.text_input("Technikus neve", value=task['tech_name'] if task['tech_name'] else "")
                                date_input = st.date_input("Munkavégzés dátuma", value=task['work_date'] if task['work_date'] else date.today())
                                submit_assign = st.form_submit_button("Mentés")
                                if submit_assign:
                                    update_task_status(task['id'], 'assigned', tech_input, date_input)
                                    st.rerun()

                        # Visszaküldés (csak ha már ki van osztva vagy volt ott valaki)
                        if task['status'] == 'assigned' or task['revisit_flag']:
                            if st.button("🔄 Visszamenni", key=f"rev_{task['id']}"):
                                update_task_status(task['id'], 'revisit')
                                st.rerun()
                        
                        # Törlés
                        if st.button("🗑️ Törlés", key=f"del_{task['id']}", type="primary"):
                            delete_task(task['id'])
                            st.rerun()

# --- 2. TAB: ÚJ FELADAT ---
with tabs[1]:
    st.header("Új feladat rögzítése")
    
    with st.form("new_task_form"):
        # Helyszín választó
        loc_options = st.session_state.locations['ID'].tolist()
        selected_loc = st.selectbox("Helyszín kiválasztása", loc_options)
        
        desc = st.text_area("Hiba leírása")
        
        col1, col2 = st.columns(2)
        d_date = col1.date_input("Határidő napja", date.today())
        d_time = col2.time_input("Határidő óra/perc", datetime.now().time())
        
        submitted = st.form_submit_button("Rögzítés")
        
        if submitted:
            save_task(selected_loc, desc, d_date, d_time)
            st.success("Feladat sikeresen rögzítve!")

# --- 3. TAB: TÉRKÉP ---
with tabs[2]:
    st.header("Hibák térképe")
    
    # Alap térkép (Magyarországra fókuszálva)
    m = folium.Map(location=[47.1625, 19.5033], zoom_start=7)
    
    # Csoportosítás helyszínek szerint
    locations_with_tasks = list(set([t['location_id'] for t in st.session_state.tasks]))
    
    for loc_id in locations_with_tasks:
        # Adatok lekérése
        loc_data = st.session_state.locations[st.session_state.locations['ID'] == loc_id]
        if loc_data.empty:
            continue
            
        lat = loc_data['Lat'].values[0]
        lon = loc_data['Lon'].values[0]
        l_type = loc_data['Tipus'].values[0].upper() if isinstance(loc_data['Tipus'].values[0], str) else "EGYÉB"
        
        # Feladatok az adott helyszínen
        loc_tasks = [t for t in st.session_state.tasks if t['location_id'] == loc_id]
        task_count = len(loc_tasks)
        
        if task_count == 0:
            continue

        # Szín logika meghatározása
        
        # 1. Keret színe (Márka alapján)
        stroke_color = 'blue' # Alapértelmezett (Egyéb)
        if 'MOL' in l_type:
            stroke_color = 'green'
        elif 'ORLEN' in l_type:
            stroke_color = 'red'
        elif 'EGYÉB' in l_type: # Vagy minden más
            stroke_color = '#3388ff' # Világoskék

        # 2. Belső szín (Státusz alapján)
        # Logika: 
        # - Csak új (nem voltunk): Piros
        # - Csak visszatérő: Sárga
        # - Vegyes: Barna
        
        has_new = any(not t['revisit_flag'] and t['status'] != 'assigned' for t in loc_tasks)
        # Feltételezzük, hogy ha 'assigned', akkor még nem 'voltunk', tehát az is az 'új' kategória a térkép szempontjából, 
        # kivéve ha a feladat specifikusan a "még nem voltunk" állapotot kéri.
        # A prompt szerint: "ahol még nem voltunk a középső kőr piros".
        
        has_revisit = any(t['revisit_flag'] for t in loc_tasks)
        
        fill_color = 'white'
        if has_new and has_revisit:
            fill_color = 'brown'
        elif has_revisit:
            fill_color = 'yellow'
        else:
            fill_color = 'red' # Minden más esetben (csak új hibák)

        # Popup tartalom összeállítása
        popup_html = f"<b>{loc_id}</b><br>Típus: {l_type}<br>Hibák száma: {task_count}<br>"
        for t in loc_tasks:
            status_icon = "⚠️" if t['revisit_flag'] else "🆕"
            popup_html += f"- {status_icon} {t['desc']}<br>"

        # Marker hozzáadása
        folium.CircleMarker(
            location=[lat, lon],
            radius=12 + (task_count * 2), # Méret a hibák számától függően kicsit nő
            color=stroke_color,      # Keret színe
            weight=4,                # Keret vastagsága
            fill=True,
            fill_color=fill_color,   # Belső színe
            fill_opacity=1,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{loc_id} ({task_count})"
        ).add_to(m)
        
        # Szám a kör közepébe (DivIcon segítségével)
        folium.map.Marker(
            [lat, lon],
            icon=folium.DivIcon(
                html=f"""<div style="font-family: sans-serif; color: white; text-shadow: 1px 1px 2px black; text-align: center; font-weight: bold;">{task_count}</div>"""
            )
        ).add_to(m)

    st_folium(m, width=1000, height=600)
    
    # Jelmagyarázat
    st.markdown("""
    **Jelmagyarázat:**
    * **Keret:** 🟢 MOL | 🔴 ORLEN | 🔵 Egyéb
    * **Belső:** 🔴 Csak új hiba | 🟡 Csak visszatérő hiba | 🟤 Vegyes
    """)

# --- 4. TAB: ÚJ CÍM ---
with tabs[3]:
    st.header("Új állomás felvétele")
    
    with st.form("new_location_form"):
        col1, col2 = st.columns(2)
        new_id = col1.text_input("Állomás neve/ID")
        new_type = col2.selectbox("Típus", ["MOL", "ORLEN", "Egyéb"])
        
        col3, col4 = st.columns(2)
        new_lat = col3.number_input("Szélesség (Lat)", format="%.6f")
        new_lon = col4.number_input("Hosszúság (Lon)", format="%.6f")
        
        if st.form_submit_button("Hozzáadás"):
            if new_id and new_lat and new_lon:
                add_location(new_id, new_type, new_lat, new_lon)
                st.success(f"{new_id} hozzáadva az adatbázishoz!")
            else:
                st.error("Minden mező kitöltése kötelező!")
