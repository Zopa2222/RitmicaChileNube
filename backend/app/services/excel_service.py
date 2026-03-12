import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from io import BytesIO
from app.services.scoring_service import calculate_e_score

# Top-8 highlight color (gold-ish)
TOP8_FILL = PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid")
HEADER_FILL = PatternFill(start_color="2D3561", end_color="2D3561", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def parse_excel_file(file_stream):
    """
    Parse Excel file and extract categories with gymnasts.

    Column layout (per side):
        col[0]=RUT_A, col[1]=NOMBRE_A, col[2]=CLUB_A, col[3]=CAT_A
        col[4]=RUT_B, col[5]=NOMBRE_B, col[6]=CLUB_B, col[7]=CAT_B

    Args:
        file_stream: file object or BytesIO

    Returns:
        dict: { category_name: [gymnasts] }
    """
    try:
        workbook = openpyxl.load_workbook(file_stream, data_only=True)
        categories = {}

        print(f"DEBUG: Sheets found: {workbook.sheetnames}")

        for sheet_name in workbook.sheetnames:
            worksheet = workbook[sheet_name]
            print(f"DEBUG: Processing sheet {sheet_name}")

            # Find header row (contains "NOMBRE")
            header_row = None
            for row_idx, row in enumerate(worksheet.iter_rows(min_row=1, max_row=20, values_only=True), 1):
                row_values = [str(cell).upper() if cell is not None else '' for cell in row]
                if 'NOMBRE' in row_values:
                    if 'CATEGORIA' in row_values or 'CATEGORÍA' in row_values:
                        header_row = row_idx
                        print(f"DEBUG: Header found at row {header_row}")
                        break

            if not header_row:
                print(f"WARN: No header 'NOMBRE' found in sheet {sheet_name}")
                continue

            max_row = worksheet.max_row
            print(f"DEBUG: Reading rows from {header_row + 1} to {max_row}")

            processed_count = 0
            rows_read = 0
            skipped_footer = 0

            for row in worksheet.iter_rows(min_row=header_row + 1, max_row=max_row, values_only=True):
                rows_read += 1

                if not row:
                    continue

                if all(cell is None or str(cell).strip() == '' for cell in row):
                    continue

                # Pad to at least 10 columns.
                # Actual Excel layout per side:
                #   col[0]=Pos, col[1]=RUT_A, col[2]=NOMBRE_A, col[3]=CLUB_A, col[4]=CAT_A
                #   col[5]=Pos, col[6]=RUT_B, col[7]=NOMBRE_B, col[8]=CLUB_B, col[9]=CAT_B
                padded_row = list(row) + [None] * max(0, 10 - len(row))

                rut_a  = padded_row[1]
                name_a = padded_row[2]
                cat_a  = padded_row[4]

                is_footer_row = False
                if name_a:
                    name_upper = str(name_a).strip().upper()
                    if any(keyword in name_upper for keyword in ['PREMIACION', 'HORARIO', 'INICIO', 'FIN', 'ENTREGA']):
                        is_footer_row = True
                        skipped_footer += 1

                if not is_footer_row:
                    if (name_a and cat_a and
                        str(name_a).strip() and str(cat_a).strip() and
                        str(name_a).strip().upper() not in ['NOMBRE', 'NAME'] and
                            str(cat_a).strip().upper() not in ['CATEGORIA', 'CATEGORÍA', 'CATEGORY']):
                        add_gymnast_to_category(categories, {
                            'rut':       str(rut_a).strip() if rut_a else '',
                            'nombre':    str(name_a).strip(),
                            'club':      str(padded_row[3]).strip() if padded_row[3] else '',
                            'categoria': str(cat_a).strip()
                        })
                        processed_count += 1

                rut_b  = padded_row[6]
                name_b = padded_row[7]
                cat_b  = padded_row[9]

                if name_b and not is_footer_row:
                    name_b_upper = str(name_b).strip().upper()
                    if any(keyword in name_b_upper for keyword in ['PREMIACION', 'HORARIO', 'INICIO', 'FIN', 'ENTREGA']):
                        is_footer_row = True
                        skipped_footer += 1

                if not is_footer_row:
                    if (name_b and cat_b and
                        str(name_b).strip() and str(cat_b).strip() and
                        str(name_b).strip().upper() not in ['NOMBRE', 'NAME'] and
                            str(cat_b).strip().upper() not in ['CATEGORIA', 'CATEGORÍA', 'CATEGORY']):
                        add_gymnast_to_category(categories, {
                            'rut':       str(rut_b).strip() if rut_b else '',
                            'nombre':    str(name_b).strip(),
                            'club':      str(padded_row[8]).strip() if padded_row[8] else '',
                            'categoria': str(cat_b).strip()
                        })
                        processed_count += 1

            print(f"DEBUG: Sheet {sheet_name}: Read {rows_read} rows, processed {processed_count} gymnasts, skipped {skipped_footer} footer rows")

        print(f"\n=== EXCEL PARSING SUMMARY ===")
        print(f"Total categories found: {len(categories)}")
        for cat_name, gymnasts in categories.items():
            print(f"  - {cat_name}: {len(gymnasts)} gimnastas")
        print(f"=============================\n")

        return categories

    except Exception as e:
        print(f"ERROR parsing Excel: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}


def add_gymnast_to_category(categories, data):
    """Helper to add gymnast to category dict"""
    category_name = data['categoria']

    if category_name not in categories:
        categories[category_name] = []
        print(f"DEBUG: New category created: '{category_name}'")

    categories[category_name].append({
        'rut':          data.get('rut', ''),
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

        # Sort by total score descending, tiebreaker by E score
        sorted_gymnasts = sorted(
            gymnasts,
            key=lambda g: (g.get('puntajeTotal', 0), calculate_e_score(g)),
            reverse=True
        )

        sheet_name = category_name[:31]
        worksheet = workbook.create_sheet(title=sheet_name)

        # Determine columns from first gymnast
        score_columns = []
        if sorted_gymnasts:
            score_columns = _get_score_columns(sorted_gymnasts[0])

        # Header row
        headers = ['Pos.', 'RUT', 'Nombre', 'Club'] + score_columns + ['Total']
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
                gymnast.get('rut', ''),
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
            key=lambda g: (g.get('puntajeTotal', 0), calculate_e_score(g)),
            reverse=True
        )

        story.append(Paragraph(f"Categoría: {category_name}", cat_style))

        if not sorted_gymnasts:
            story.append(Paragraph("Sin gimnastas registradas.", styles['Normal']))
            story.append(Spacer(1, 0.3*cm))
            continue

        score_columns = _get_score_columns(sorted_gymnasts[0])
        headers = ['Pos.', 'RUT', 'Nombre', 'Club'] + score_columns + ['Total']

        table_data = [headers]
        for position, gymnast in enumerate(sorted_gymnasts, 1):
            row = [
                str(position),
                gymnast.get('rut', ''),
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
        col_widths = [1.2*cm, 2.8*cm, 5*cm, 4*cm] + [1.8*cm] * (num_cols - 5) + [2*cm]

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
