# ... (a kód eleje változatlan)

# -----------------------------
# 2. VEZÉNYLÉS (JAVÍTOTT FELIRATOKKAL)
# -----------------------------
elif active_menu == "Vezénylés":
    row_id = st.session_state.edit_row_id
    st.title("📋 " + ("Ütemezés módosítása" if row_id else "Új vezénylés leadása"))
    
    with st.form("v_form"):
        if row_id:
            # Itt olvassuk be a Naplóból a kiválasztott hiba adatait
            row_data = data['naplo'][data['naplo']['_sheet_row'] == row_id].iloc[0]
            default_allomas = row_data[COL_A]
            default_feladat = row_data[COL_DESC]
            task_list = [get_task_label(row_data)]
        else:
            # Csak a Nyitott vagy Visszamenni státuszú hibák jelennek meg
            task_options = {get_task_label(r): r for _, r in hibas_df.iterrows()}
            task_list = list(task_options.keys())

        techs = data['tech']['Név'].tolist() if not data['tech'].empty else ["Nincs technikus"]
        t_tech = st.selectbox("Technikus kiválasztása", techs)
        selected_task_label = st.selectbox("Választható feladat", task_list)
        
        # JAVÍTOTT FELIRAT: Ez mentődik a Vezenylesek lapra
        st.info("Az alábbi időpont a technikus ütemezett kiszállási ideje, az eredeti hiba dátumát nem módosítja.")
        t_date = st.date_input("Munkavégzés tervezett napja", date.today())
        t_time = st.time_input("Munkavégzés tervezett órája", time(8, 0))
        
        c1, c2 = st.columns(2)
        if c1.form_submit_button("Ütemezés mentése"):
            if row_id:
                final_allomas, final_feladat = default_allomas, default_feladat
            else:
                sel_row = task_options[selected_task_label]
                final_allomas, final_feladat = sel_row[COL_A], sel_row[COL_DESC]

            # Meglévő ütemezés frissítése a Vezenylesek munkalapon
            try:
                cells = sheet_vez.findall(final_allomas)
                for cell in reversed(cells):
                    if sheet_vez.cell(cell.row, list(data['vez'].columns).index(COL_V_FEL)+1).value == final_feladat:
                        sheet_vez.delete_rows(cell.row)
            except: pass
            
            # Az új adat beírása a Vezenylesek munkalapra
            sheet_vez.append_row([t_tech, final_allomas, f"{t_date} {t_time.strftime('%H:%M')}", final_feladat])
            st.session_state.edit_row_id = None
            st.success("Ütemezés sikeresen rögzítve!"); st.rerun()
            
        if row_id and c2.form_submit_button("Ütemezés törlése (Hiba marad)"):
            st.session_state.edit_row_id = None; st.rerun()

    if st.button("⬅️ Vissza a műszerfalra"): st.session_state.edit_row_id = None; st.rerun()

# ... (a kód többi része változatlan)
