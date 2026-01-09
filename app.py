# Műveleti gombok logikusabb megjelenítése
b1, b2, b3 = st.columns(3)

# 1. KÉSZ GOMB (Zöld pipa)
if b1.button("✅", key=f"ok_{row['_sheet_row']}", help="Feladat elvégezve"):
    sheet_naplo.update_cell(row['_sheet_row'], 4, "Kész")
    # Töröljük az ütemezést is, ha volt
    cells = sheet_vez.findall(row[COL_A])
    for cell in reversed(cells):
        if sheet_vez.cell(cell.row, 4).value == row['Hiba leírása']:
            sheet_vez.delete_rows(cell.row)
    st.rerun()

# 2. ÜTEMEZÉS / MÓDOSÍTÁS GOMB
# Ha nincs ütemezve, más ikont és szöveget mutatunk
if not v_info.empty:
    btn_label = "📝"
    btn_help = "Ütemezés módosítása"
else:
    btn_label = "📅"
    btn_help = "Új ütemezés leadása"

if b2.button(btn_label, key=f"ed_{row['_sheet_row']}", help=btn_help):
    st.session_state.edit_row_id = row['_sheet_row']
    st.rerun()

# 3. VISSZAMENNI GOMB (Kék frissítés ikon)
if b3.button("🔄", key=f"re_{row['_sheet_row']}", help="Visszamenni szükséges"):
    sheet_naplo.update_cell(row['_sheet_row'], 4, "Visszamenni")
    st.rerun()
