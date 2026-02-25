import openpyxl
from io import BytesIO
from app.services.scoring_service import calculate_e_score

def parse_excel_file(file_stream):
    """
    Parse Excel file and extract categories with gymnasts
    
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
                # Convert to string and upper case for reliable matching
                row_values = [str(cell).upper() if cell is not None else '' for cell in row]
                if 'NOMBRE' in row_values:
                    # Double check it has "CATEGORIA" too to be sure
                    if 'CATEGORIA' in row_values or 'CATEGORÍA' in row_values:
                        header_row = row_idx
                        print(f"DEBUG: Header found at row {header_row}")
                        break
            
            if not header_row:
                print(f"WARN: No header 'NOMBRE' found in sheet {sheet_name}")
                continue
            
            # Extract gymnasts from BANCA A and BANCA B
            # Use explicit max_row to ensure we read ALL rows
            max_row = worksheet.max_row
            print(f"DEBUG: Reading rows from {header_row + 1} to {max_row} (total: {max_row - header_row} rows)")
            
            processed_count = 0
            rows_read = 0
            skipped_footer = 0
            
            for row in worksheet.iter_rows(min_row=header_row + 1, max_row=max_row, values_only=True):
                rows_read += 1
                
                if not row:
                    continue
                
                # Check for empty rows
                if all(cell is None or str(cell).strip() == '' for cell in row):
                    continue

                # Normalizar longitud de fila para evitar IndexError
                # Necesitamos al menos hasta índice 7 (col 8) para Banca B
                padded_row = list(row) + [None] * max(0, 8 - len(row))
                
                # BANCA A (columns 0-3: N, NOMBRE, CLUB, CATEGORIA)
                # Indices: 1 (Nombre), 2 (Club), 3 (Categoria)
                name_a = padded_row[1]
                cat_a = padded_row[3]
                
                # Check if this is a footer row (contains text like "PREMIACION", "HORARIO", etc.)
                is_footer_row = False
                if name_a:
                    name_upper = str(name_a).strip().upper()
                    if any(keyword in name_upper for keyword in ['PREMIACION', 'HORARIO', 'INICIO', 'FIN', 'ENTREGA']):
                        is_footer_row = True
                        skipped_footer += 1
                
                if not is_footer_row:
                    # Filter out header rows and invalid values
                    if (name_a and cat_a and 
                        str(name_a).strip() and str(cat_a).strip() and
                        str(name_a).strip().upper() not in ['NOMBRE', 'NAME'] and
                        str(cat_a).strip().upper() not in ['CATEGORIA', 'CATEGORÍA', 'CATEGORY']):
                        add_gymnast_to_category(categories, {
                            'nombre': str(name_a).strip(),
                            'club': str(padded_row[2]).strip() if padded_row[2] else '',
                            'categoria': str(cat_a).strip()
                        })
                        processed_count += 1
                
                # BANCA B (columns 4-7: N, NOMBRE, CLUB, CATEGORIA)
                # Indices: 5 (Nombre), 6 (Club), 7 (Categoria)
                name_b = padded_row[5]
                cat_b = padded_row[7]
                
                # Check footer for Banca B as well
                if name_b and not is_footer_row:
                    name_b_upper = str(name_b).strip().upper()
                    if any(keyword in name_b_upper for keyword in ['PREMIACION', 'HORARIO', 'INICIO', 'FIN', 'ENTREGA']):
                        is_footer_row = True
                        skipped_footer += 1
                
                if not is_footer_row:
                    # Filter out header rows and invalid values
                    if (name_b and cat_b and 
                        str(name_b).strip() and str(cat_b).strip() and
                        str(name_b).strip().upper() not in ['NOMBRE', 'NAME'] and
                        str(cat_b).strip().upper() not in ['CATEGORIA', 'CATEGORÍA', 'CATEGORY']):
                        add_gymnast_to_category(categories, {
                            'nombre': str(name_b).strip(),
                            'club': str(padded_row[6]).strip() if padded_row[6] else '',
                            'categoria': str(cat_b).strip()
                        })
                        processed_count += 1
                    
            print(f"DEBUG: Sheet {sheet_name}: Read {rows_read} rows, processed {processed_count} gymnasts, skipped {skipped_footer} footer rows")
        
        # Log final categories found
        print(f"\n=== EXCEL PARSING SUMMARY ===")
        print(f"Total categories found: {len(categories)}")
        print(f"Category names: {list(categories.keys())}")
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
        'nombre': data['nombre'],
        'club': data['club'],
        'DA': 0.0,
        'DB': 0.0,
        'E': [],
        'A': [],
        'Desc': 0.0,
        'puntajeTotal': 0.0,
        'order': len(categories[category_name])
    })


def export_to_excel(championship_name, categories_data):
    """
    Export categories to Excel file
    
    Args:
        championship_name: str
        categories_data: list of dicts with 'categoria' and 'gimnastas'
    
    Returns:
        BytesIO: Excel file in memory
    """
    workbook = openpyxl.Workbook()
    # Remove default sheet
    workbook.remove(workbook.active)
    
    for category_data in categories_data:
        category_name = category_data['categoria']
        gymnasts = category_data['gimnastas']
        
        # Sort by puntajeTotal (highest first), then by E score for tiebreaker
        sorted_gymnasts = sorted(
            gymnasts, 
            key=lambda g: (g.get('puntajeTotal', 0), calculate_e_score(g)), 
            reverse=True
        )
        
        # Create worksheet (limit name to 31 chars)
        sheet_name = category_name[:31]
        worksheet = workbook.create_sheet(title=sheet_name)
        
        # Determine score columns based on first gymnast
        score_columns = []
        if sorted_gymnasts:
            first = sorted_gymnasts[0]
            if 'DA' in first: score_columns.append('DA')
            if 'DB' in first: score_columns.append('DB')
            
            # E scores
            e_count = len(first.get('E', []))
            for i in range(e_count):
                score_columns.append(f'E{i+1}')
            
            # A scores
            a_count = len(first.get('A', []))
            for i in range(a_count):
                score_columns.append(f'A{i+1}')
            
            if 'Desc' in first: score_columns.append('Desc')
        
        # Header row
        headers = ['Posición', 'Nombre', 'Club'] + score_columns + ['Total']
        worksheet.append(headers)
        
        # Data rows
        for position, gymnast in enumerate(sorted_gymnasts, 1):
            row = [
                position,
                gymnast.get('nombre', ''),
                gymnast.get('club', '')
            ]
            
            # Add scores
            for col in score_columns:
                if col.startswith('E'):
                    idx = int(col[1:]) - 1
                    e_scores = gymnast.get('E', [])
                    row.append(e_scores[idx] if idx < len(e_scores) else 0.0)
                elif col.startswith('A'):
                    idx = int(col[1:]) - 1
                    a_scores = gymnast.get('A', [])
                    row.append(a_scores[idx] if idx < len(a_scores) else 0.0)
                else:
                    row.append(gymnast.get(col, 0.0))
            
            # Add total
            row.append(gymnast.get('puntajeTotal', 0.0))
            worksheet.append(row)
    
    # Save to BytesIO
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    
    return output
