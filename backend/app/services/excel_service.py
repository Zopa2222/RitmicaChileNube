import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from io import BytesIO
from app.services.scoring_service import calculate_e_score, calculate_a_score

# Top-8 highlight color (gold-ish)
TOP8_FILL = PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid")
HEADER_FILL = PatternFill(start_color="2D3561", end_color="2D3561", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def parse_excel_file(file_stream):
    """
    Parse Excel file and extract categories with gymnasts.

    Handles multiple sections within the same sheet (individuales, duos, trios,
    conjuntos) separated by blank rows or sub-headers.  Column positions are
    detected dynamically from each header row containing NOMBRE + CATEGORIA.

    Args:
        file_stream: file object or BytesIO

    Returns:
        dict: { category_name: [gymnasts] }
    """
    try:
        workbook = openpyxl.load_workbook(file_stream, data_only=True)
        categories = {}
        categorias_banca = {}  # { category_name: 'A' | 'B' }

        print(f"DEBUG: Sheets found: {workbook.sheetnames}")

        for sheet_name in workbook.sheetnames:
            worksheet = workbook[sheet_name]
            print(f"DEBUG: Processing sheet {sheet_name}")

            processed_count = 0
            rows_read = 0
            skipped_footer = 0

            # We'll detect column groups dynamically.
            # A "group" is a set of (nombre_idx, club_idx, cat_idx) found
            # in a header row.  There may be two groups (Banca A + Banca B)
            # or just one.
            column_groups = []  # list of (nombre_idx, club_idx, cat_idx)

            max_row = worksheet.max_row
            if max_row is None:
                continue

            for row_idx, row in enumerate(worksheet.iter_rows(min_row=1, max_row=max_row, values_only=True), 1):
                rows_read += 1

                if not row:
                    continue

                row_list = list(row)
                row_upper = [str(cell).upper().strip() if cell is not None else '' for cell in row_list]

                # --- Check if this row is a header row ---
                nombre_positions = [i for i, v in enumerate(row_upper) if v == 'NOMBRE']
                cat_positions = [i for i, v in enumerate(row_upper) if v in ('CATEGORIA', 'CATEGORÍA', 'CATEGORY')]

                if nombre_positions and cat_positions:
                    # Detected a header row – rebuild column_groups
                    column_groups = []
                    club_positions = [i for i, v in enumerate(row_upper) if v == 'CLUB']

                    for nombre_idx in nombre_positions:
                        # Find the nearest CATEGORIA column to the right of NOMBRE
                        cat_candidates = [c for c in cat_positions if c > nombre_idx]
                        if not cat_candidates:
                            continue
                        cat_idx = min(cat_candidates)

                        # Find the nearest CLUB column between NOMBRE and CATEGORIA
                        club_candidates = [c for c in club_positions if nombre_idx < c < cat_idx]
                        club_idx = min(club_candidates) if club_candidates else None

                        column_groups.append((nombre_idx, club_idx, cat_idx))

                    print(f"DEBUG: Header detected at row {row_idx} with {len(column_groups)} group(s): {column_groups}")
                    continue  # Don't parse the header row as data

                # --- Skip if we haven't found any header yet ---
                if not column_groups:
                    continue

                # --- Skip fully blank rows ---
                if all(cell is None or str(cell).strip() == '' for cell in row_list):
                    continue

                # --- Parse data from each column group ---
                padded_row = row_list + [None] * max(0, max(g[2] for g in column_groups) + 1 - len(row_list))

                is_footer_row = False

                for group_idx, (nombre_idx, club_idx, cat_idx) in enumerate(column_groups):
                    banca = 'A' if group_idx == 0 else 'B'
                    name_val = padded_row[nombre_idx]
                    club_val = padded_row[club_idx] if club_idx is not None else None
                    cat_val  = padded_row[cat_idx]

                    if not name_val or not cat_val:
                        continue

                    name_str = str(name_val).strip()
                    cat_str  = str(cat_val).strip()

                    if not name_str or not cat_str:
                        continue

                    # Skip header-like values
                    if name_str.upper() in ('NOMBRE', 'NAME', 'N'):
                        continue
                    if cat_str.upper() in ('CATEGORIA', 'CATEGORÍA', 'CATEGORY'):
                        continue

                    # Skip footer rows
                    if any(kw in name_str.upper() for kw in ['PREMIACION', 'HORARIO', 'INICIO', 'FIN', 'ENTREGA']):
                        is_footer_row = True
                        skipped_footer += 1
                        continue

                    if is_footer_row:
                        continue

                    add_gymnast_to_category(categories, {
                        'nombre':    name_str,
                        'club':      str(club_val).strip() if club_val else '',
                        'categoria': cat_str
                    })
                    # Track banca assignment per category
                    if cat_str not in categorias_banca:
                        categorias_banca[cat_str] = banca
                    processed_count += 1

            print(f"DEBUG: Sheet {sheet_name}: Read {rows_read} rows, processed {processed_count} gymnasts, skipped {skipped_footer} footer rows")

        print(f"\n=== EXCEL PARSING SUMMARY ===")
        print(f"Total categories found: {len(categories)}")
        for cat_name, gymnasts in categories.items():
            banca_label = categorias_banca.get(cat_name, '?')
            print(f"  - {cat_name} (Banca {banca_label}): {len(gymnasts)} gimnastas")
        print(f"=============================\n")

        return categories, categorias_banca

    except Exception as e:
        print(f"ERROR parsing Excel: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}, {}


def add_gymnast_to_category(categories, data):
    """Helper to add gymnast to category dict"""
    category_name = data['categoria']

    if category_name not in categories:
        categories[category_name] = []
        print(f"DEBUG: New category created: '{category_name}'")

    categories[category_name].append({
        'nombre':       data['nombre'],
        'club':         data['club'],
        'DA':           0.0,
        'DB':           0.0,
        'E':            [],
        'A':            [],
        'Desc':         0.0,
        'puntajeTotal': 0.0,
        'order':        len(categories[category_name])
    })


def _get_score_columns(gymnast):
    """
    Build ordered score column list: DB, DA, A..., E..., Desc
    """
    score_columns = []
    if 'DB' in gymnast:
        score_columns.append('DB')
    if 'DA' in gymnast:
        score_columns.append('DA')

    # A scores
    a_count = len(gymnast.get('A', []))
    for i in range(a_count):
        score_columns.append(f'A{i+1}')

    # E scores
    e_count = len(gymnast.get('E', []))
    for i in range(e_count):
        score_columns.append(f'E{i+1}')

    if 'Desc' in gymnast:
        score_columns.append('Desc')

    return score_columns


def _get_score_value(gymnast, col):
    """Extract numeric value for a score column"""
    if col.startswith('E'):
        idx = int(col[1:]) - 1
        e_scores = gymnast.get('E', [])
        return e_scores[idx] if idx < len(e_scores) else 0.0
    elif col.startswith('A'):
        idx = int(col[1:]) - 1
        a_scores = gymnast.get('A', [])
        return a_scores[idx] if idx < len(a_scores) else 0.0
    else:
        return gymnast.get(col, 0.0)


def export_to_excel(championship_name, categories_data):
    """
    Export categories to Excel file with top-8 gymnasts highlighted.

    Args:
        championship_name: str
        categories_data: list of dicts with 'categoria' and 'gimnastas'

    Returns:
        BytesIO: Excel file in memory
    """
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)

    thin = Side(style='thin', color='CCCCCC')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for category_data in categories_data:
        category_name = category_data['categoria']
        gymnasts = category_data['gimnastas']

        # Sort by total score descending, tiebreaker by E score, then A score
        sorted_gymnasts = sorted(
            gymnasts,
            key=lambda g: (g.get('puntajeTotal', 0), calculate_e_score(g), calculate_a_score(g)),
            reverse=True
        )

        sheet_name = category_name[:31]
        worksheet = workbook.create_sheet(title=sheet_name)

        # Determine columns from first gymnast
        score_columns = []
        if sorted_gymnasts:
            score_columns = _get_score_columns(sorted_gymnasts[0])

        # Header row
        headers = ['Pos.', 'Nombre', 'Club'] + score_columns + ['Total']
        worksheet.append(headers)

        # Style header
        for col_idx, _ in enumerate(headers, 1):
            cell = worksheet.cell(row=1, column=col_idx)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border

        # Data rows
        for position, gymnast in enumerate(sorted_gymnasts, 1):
            row_data = [
                position,
                gymnast.get('nombre', ''),
                gymnast.get('club', '')
            ]
            for col in score_columns:
                row_data.append(_get_score_value(gymnast, col))
            row_data.append(gymnast.get('puntajeTotal', 0.0))

            worksheet.append(row_data)

            # Highlight top 8
            excel_row = position + 1  # +1 because row 1 is header
            is_top8 = position <= 8
            for col_idx in range(1, len(headers) + 1):
                cell = worksheet.cell(row=excel_row, column=col_idx)
                cell.border = border
                cell.alignment = Alignment(horizontal='center', vertical='center')
                if is_top8:
                    cell.fill = TOP8_FILL
                    cell.font = Font(bold=True)

        # Auto-fit column widths
        for col_cells in worksheet.columns:
            max_len = max((len(str(c.value)) for c in col_cells if c.value), default=8)
            worksheet.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 30)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def export_to_pdf(championship_name, categories_data):
    """
    Export categories to a non-editable PDF with top-8 highlighted.

    Args:
        championship_name: str
        categories_data: list of dicts with 'categoria' and 'gimnastas'

    Returns:
        BytesIO: PDF file in memory
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('title', parent=styles['Title'], fontSize=16, spaceAfter=6, alignment=TA_CENTER)
    cat_style = ParagraphStyle('cat', parent=styles['Heading2'], fontSize=13, spaceBefore=12, spaceAfter=6)
    note_style = ParagraphStyle('note', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#777777'))

    top8_color = colors.HexColor('#FFD700')
    header_color = colors.HexColor('#2D3561')
    white = colors.white
    light_gray = colors.HexColor('#F5F5F5')

    story = []

    # Title
    story.append(Paragraph(f"Resultados – {championship_name}", title_style))
    story.append(Paragraph("Ritmica Chile", ParagraphStyle('inst', parent=styles['Normal'], fontSize=9,
                                                           textColor=colors.HexColor('#555555'), alignment=TA_CENTER)))
    story.append(Spacer(1, 0.4*cm))

    for idx, category_data in enumerate(categories_data):
        category_name = category_data['categoria']
        gymnasts = category_data['gimnastas']

        sorted_gymnasts = sorted(
            gymnasts,
            key=lambda g: (g.get('puntajeTotal', 0), calculate_e_score(g), calculate_a_score(g)),
            reverse=True
        )

        story.append(Paragraph(f"Categoría: {category_name}", cat_style))

        if not sorted_gymnasts:
            story.append(Paragraph("Sin gimnastas registradas.", styles['Normal']))
            story.append(Spacer(1, 0.3*cm))
            continue

        score_columns = _get_score_columns(sorted_gymnasts[0])
        headers = ['Pos.', 'Nombre', 'Club'] + score_columns + ['Total']

        table_data = [headers]
        for position, gymnast in enumerate(sorted_gymnasts, 1):
            row = [
                str(position),
                gymnast.get('nombre', ''),
                gymnast.get('club', '')
            ]
            for col in score_columns:
                val = _get_score_value(gymnast, col)
                row.append(f"{val:.2f}" if isinstance(val, float) else str(val))
            row.append(f"{gymnast.get('puntajeTotal', 0.0):.2f}")
            table_data.append(row)

        # Column widths
        num_cols = len(headers)
        col_widths = [1.2*cm, 5*cm, 4*cm] + [1.8*cm] * (num_cols - 4) + [2*cm]

        table = Table(table_data, colWidths=col_widths, repeatRows=1)

        style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), header_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, light_gray]),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]

        # Highlight top 8
        for pos in range(1, min(8, len(sorted_gymnasts)) + 1):
            row_idx = pos  # row 0 is header
            style_commands.append(('BACKGROUND', (0, row_idx), (-1, row_idx), top8_color))
            style_commands.append(('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold'))

        table.setStyle(TableStyle(style_commands))
        story.append(table)
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph("★ Fondo dorado = Top 8 de la categoría", note_style))

        if idx < len(categories_data) - 1:
            story.append(PageBreak())

    doc.build(story)
    output.seek(0)
    return output
