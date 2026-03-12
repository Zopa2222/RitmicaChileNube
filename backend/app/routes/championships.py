from flask import Blueprint, request, jsonify, send_file
from app.utils.db import MongoDB
from app.services import excel_service, scoring_service
from datetime import datetime
import traceback

bp = Blueprint('championships', __name__)


@bp.route('/campeonatos', methods=['GET'])
def list_championships():
    """List all championships"""
    try:
        championship_dbs = MongoDB.list_championships()
        championships = []
        
        for db_name in championship_dbs:
            db = MongoDB.get_database(db_name)
            metadata = db.metadata.find_one({}, {'_id': 0})
            if metadata:
                # Get categories from collection names (excluding metadata and jueces)
                all_collections = db.list_collection_names()
                categories = [
                    col for col in all_collections 
                    if col not in ['metadata', 'jueces']
                ]
                
                # Get judges list
                jueces_list = list(db.jueces.find({}, {'_id': 0}))
                
                championships.append({
                    'id': db_name,
                    'nombre': metadata.get('nombre_campeonato'),
                    'categorias': categories,
                    'jueces': jueces_list,
                    'created_at': metadata.get('created_at')
                })
        
        return jsonify({
            'success': True,
            'campeonatos': championships,
            'total': len(championships)
        }), 200
        
    except Exception as e:
        print(f"Error listing championships: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/campeonatos', methods=['POST'])
def create_championship():
    """Create a new championship"""
    try:
        data = request.get_json()
        nombre = data.get('nombre')
        
        if not nombre:
            return jsonify({'error': 'Nombre del campeonato es requerido'}), 400
        
        # Check if championship already exists
        if MongoDB.championship_exists(nombre):
            db_name = MongoDB.get_championship_db_name(nombre)
            return jsonify({
                'error': f'El campeonato "{nombre}" ya existe',
                'id': db_name
            }), 400
        
        # Get database name
        db_name = MongoDB.get_championship_db_name(nombre)
        db = MongoDB.get_database(db_name)
        
        # Create metadata collection with initial document
        # This ensures the database is created
        metadata = {
            'nombre_campeonato': nombre,
            'created_at': datetime.utcnow()
        }
        db.metadata.insert_one(metadata)
        
        # Note: No need to explicitly create 'jueces' collection
        # MongoDB will create it automatically when first judge is inserted
        
        return jsonify({
            'campeonato': nombre,
            'id': db_name,
            'success': True,
            'mensaje': f'Campeonato "{nombre}" creado exitosamente con base de datos: {db_name}'
        }), 201
        
    except Exception as e:
        print(f"Error creating championship: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/campeonatos/<campeonato>/jueces', methods=['POST'])
def add_judge(campeonato):
    """Add a judge to the championship"""
    try:
        data = request.get_json()
        nombre = data.get('nombre')
        rol = data.get('rol')
        
        if not nombre or not rol:
            return jsonify({'error': 'Nombre y rol son requeridos'}), 400
        
        # Validate rol
        valid_roles = ['DA', 'DA2', 'DB', 'DB2', 'E1', 'E2', 'E3', 'E4', 'A1', 'A2', 'A3', 'A4', 'L']
        if rol not in valid_roles:
            return jsonify({'error': f'Rol inválido. Debe ser uno de: {", ".join(valid_roles)}'}), 400
        
        # Check if championship exists
        db = MongoDB.get_database(campeonato)
        if 'metadata' not in db.list_collection_names():
            return jsonify({
                'error': f'El campeonato "{campeonato}" no existe. Debe crear el campeonato primero.'
            }), 404
        
        # Check if a judge with this role already exists
        existing_judge = db.jueces.find_one({'rol': rol})
        if existing_judge:
            return jsonify({
                'error': f'Ya existe un juez con el rol "{rol}": {existing_judge.get("nombre")}',
                'existente': {
                    'nombre': existing_judge.get('nombre'),
                    'rol': existing_judge.get('rol')
                }
            }), 400
        
        juez = {
            'nombre': nombre,
            'rol': rol,
            'created_at': datetime.utcnow()
        }
        
        result = db.jueces.insert_one(juez)
        juez['_id'] = str(result.inserted_id)
        
        return jsonify({
            'success': True,
            'juez': juez,
            'mensaje': f'Juez "{nombre}" agregado con rol "{rol}" en colección "jueces"'
        }), 201
        
    except Exception as e:
        print(f"Error adding judge: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/campeonatos/<campeonato>/orden-paso', methods=['POST'])
def upload_orden_paso(campeonato):
    """Upload Excel file with orden de paso"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No se encontró archivo'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'Archivo vacío'}), 400
        
        # Check if championship exists
        db = MongoDB.get_database(campeonato)
        if 'metadata' not in db.list_collection_names():
            return jsonify({
                'error': f'El campeonato "{campeonato}" no existe. Debe crear el campeonato primero.'
            }), 404
        
        # Parse Excel
        categories = excel_service.parse_excel_file(file)
        
        if not categories:
            print(f"ERROR: No se encontraron categorías en el archivo {file.filename}")
            return jsonify({'error': 'No se encontraron categorías en el archivo'}), 400
        
        print(f"DEBUG: Conectado a base de datos '{campeonato}'")
        print(f"DEBUG: Se procesarán {len(categories)} categorías")
        
        # Create collection for each category and insert gymnasts
        category_names = []
        for category_name, gymnasts in categories.items():
            collection_name = MongoDB.normalize_name(category_name)
            category_names.append(category_name)
            
            print(f"DEBUG: Procesando categoría '{category_name}' -> creando colección '{collection_name}'")
            print(f"DEBUG: Encontradas {len(gymnasts)} gimnastas")
            
            # Drop existing collection if it exists
            if collection_name in db.list_collection_names():
                print(f"DEBUG: Eliminando colección existente '{collection_name}'")
                db[collection_name].drop()
            
            # Insert gymnasts - MongoDB creates the collection automatically
            if gymnasts:
                try:
                    result = db[collection_name].insert_many(gymnasts)
                    print(f"DEBUG: ✓ Insertadas {len(result.inserted_ids)} gimnastas en colección '{collection_name}'")
                    
                    # Create non-unique index on 'nombre' field for efficient queries
                    # Note: NOT unique because multiple gymnasts can have the same name
                    db[collection_name].create_index('nombre')
                    print(f"DEBUG: ✓ Índice creado en campo 'nombre' para colección '{collection_name}'")
                except Exception as insert_error:
                    print(f"ERROR: Falló insert_many en colección '{collection_name}': {insert_error}")
                    raise
            else:
                print(f"WARN: Lista de gimnastas vacía para categoría '{category_name}'")
        
        # Save category order in metadata to preserve Excel presentation order
        db.metadata.update_one(
            {},
            {'$set': {'categorias_orden': category_names}},
            upsert=False
        )
        print(f"DEBUG: ✓ Guardado orden de categorías en metadata")
        print(f"DEBUG: ✓ Procesadas {len(category_names)} categorías como colecciones")
        
        return jsonify({
            'success': True,
            'categorias': category_names,
            'mensaje': f'Se crearon {len(category_names)} colecciones de categorías en la base de datos "{campeonato}"',
            'base_datos': campeonato,
            'colecciones': [MongoDB.normalize_name(cat) for cat in category_names]
        }), 201
        
    except Exception as e:
        print(f"Error uploading orden-paso: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/campeonatos/<campeonato>/categorias', methods=['GET'])
def list_categories(campeonato):
    """List all categories for a championship"""
    try:
        db = MongoDB.get_database(campeonato)
        
        # Check if championship exists
        if 'metadata' not in db.list_collection_names():
            return jsonify({
                'error': f'El campeonato "{campeonato}" no existe.'
            }), 404
        
        # Get categories from collection names (excluding metadata and jueces)
        all_collections = db.list_collection_names()
        available_categories = [
            col for col in all_collections 
            if col not in ['metadata', 'jueces']
        ]
        
        # Get ordering from metadata if available
        metadata = db.metadata.find_one({}, {'_id': 0})
        categorias_orden = metadata.get('categorias_orden', []) if metadata else []
        
        # Order categories according to metadata, then append any new ones not in order list
        if categorias_orden:
            # Normalize names for comparison
            normalized_orden = [MongoDB.normalize_name(cat) for cat in categorias_orden]
            
            # Order existing categories
            categories = []
            for normalized_cat in normalized_orden:
                if normalized_cat in available_categories:
                    categories.append(normalized_cat)
            
            # Add any categories not in the order list (shouldn't happen, but just in case)
            for cat in available_categories:
                if cat not in categories:
                    categories.append(cat)
                    print(f"WARN: Category '{cat}' not in metadata order, appending at end")
        else:
            # No order saved, return as-is
            categories = available_categories
            print("WARN: No category order found in metadata, returning unordered")
        
        return jsonify({
            'success': True,
            'campeonato': campeonato,
            'categorias': categories,
            'total': len(categories)
        }), 200
        
    except Exception as e:
        print(f"Error listing categories: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/campeonatos/<campeonato>/categorias/<categoria>', methods=['GET'])
def get_category(campeonato, categoria):
    """Get all gymnasts from a category"""
    try:
        db = MongoDB.get_database(campeonato)
        collection_name = MongoDB.normalize_name(categoria)
        
        # Get all gymnasts
        gymnasts = list(db[collection_name].find({}, {'_id': 0}))
        
        # Sort by order
        gymnasts.sort(key=lambda g: g.get('order', 0))
        
        return jsonify({
            'categoria': categoria,
            'gimnastas': gymnasts
        }), 200
        
    except Exception as e:
        print(f"Error getting category: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/campeonatos/<campeonato>/categorias/<categoria>', methods=['PUT'])
def update_category(campeonato, categoria):
    """Update category with scores"""
    try:
        data = request.get_json()
        gimnastas = data.get('gimnastas', [])
        
        if not gimnastas:
            return jsonify({'error': 'No se enviaron gimnastas'}), 400
        
        db = MongoDB.get_database(campeonato)
        collection_name = MongoDB.normalize_name(categoria)
        
        # Get judges to calculate scores
        judges = list(db.jueces.find({}, {'_id': 0}))
        
        # Process each gymnast
        response_gimnastas = []
        for gymnast in gimnastas:
            # Recalculate puntajeTotal on backend
            puntaje_total = scoring_service.calculate_total_score(gymnast, judges)
            gymnast['puntajeTotal'] = puntaje_total

            # Use RUT as unique key; fall back to nombre for legacy records
            filter_key = {'rut': gymnast['rut']} if gymnast.get('rut') else {'nombre': gymnast['nombre']}

            # Update in database
            db[collection_name].update_one(
                filter_key,
                {'$set': gymnast},
                upsert=True
            )

            response_gimnastas.append({
                'rut': gymnast.get('rut', ''),
                'nombre': gymnast['nombre'],
                'puntajeTotal': puntaje_total
            })
        
        return jsonify({
            'success': True,
            'gimnastas': response_gimnastas
        }), 200
        
    except Exception as e:
        print(f"Error updating category: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/campeonatos/<campeonato>/export', methods=['GET'])
def export_championship(campeonato):
    """Export championship results to Excel"""
    try:
        db = MongoDB.get_database(campeonato)
        
        # Get metadata
        metadata = db.metadata.find_one({})
        if not metadata:
            return jsonify({'error': 'Campeonato no encontrado'}), 404
        
        championship_name = metadata.get('nombre_campeonato', campeonato)
        
        # Get categories dynamically from collection names
        all_collections = db.list_collection_names()
        categorias = [col for col in all_collections if col not in ['metadata', 'jueces']]
        
        print(f"DEBUG: Exporting championship '{championship_name}' with {len(categorias)} categories")
        
        # Get all categories with gymnasts
        categories_data = []
        for collection_name in categorias:
            gimnastas = list(db[collection_name].find({}, {'_id': 0}))
            
            print(f"DEBUG: Category '{collection_name}' has {len(gimnastas)} gymnasts")
            
            categories_data.append({
                'categoria': collection_name,
                'gimnastas': gimnastas
            })
        
        # Generate Excel
        excel_file = excel_service.export_to_excel(championship_name, categories_data)
        
        filename = f"{championship_name}_resultados.xlsx"
        
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"Error exporting championship: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/campeonatos/<campeonato>/export/pdf', methods=['GET'])
def export_championship_pdf(campeonato):
    """Export championship results to PDF (non-editable, top-8 highlighted)"""
    try:
        db = MongoDB.get_database(campeonato)

        metadata = db.metadata.find_one({})
        if not metadata:
            return jsonify({'error': 'Campeonato no encontrado'}), 404

        championship_name = metadata.get('nombre_campeonato', campeonato)

        all_collections = db.list_collection_names()
        categorias = [col for col in all_collections if col not in ['metadata', 'jueces']]

        # Respect ordering from metadata if available
        metadata_order = metadata.get('categorias_orden', [])
        if metadata_order:
            normalized_order = [MongoDB.normalize_name(c) for c in metadata_order]
            ordered = [c for c in normalized_order if c in categorias]
            for c in categorias:
                if c not in ordered:
                    ordered.append(c)
            categorias = ordered

        categories_data = []
        for collection_name in categorias:
            gimnastas = list(db[collection_name].find({}, {'_id': 0}))
            categories_data.append({
                'categoria': collection_name,
                'gimnastas': gimnastas
            })

        pdf_file = excel_service.export_to_pdf(championship_name, categories_data)

        filename = f"{championship_name}_resultados.pdf"

        return send_file(
            pdf_file,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        print(f"Error exporting PDF: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Zona keywords mapped to championship name fragments
# ---------------------------------------------------------------------------
ZONA_KEYWORDS = {
    'norte':  'zona norte',
    'centro': 'zona centro',
    'sur':    'zona sur',
}


def _get_zona_championships(zona: str, anio: str = None):
    """
    Return championship databases whose nombre_campeonato contains
    the zone keyword (case-insensitive) AND optionally the given year.
    Sorted by created_at ascending so index 0 = 1st control, index 1 = 2nd control.
    """
    results, err = _get_zona_championships_with_meta(zona, anio)
    if err:
        return None, err
    return [db for _, db in results], None


def _get_zona_championships_with_meta(zona: str, anio: str = None):
    """
    Like _get_zona_championships but returns list of (nombre_campeonato, db) tuples,
    so callers can record which championship each gymnast came from.
    """
    from app.utils.db import MongoDB
    keyword = ZONA_KEYWORDS.get(zona.lower())
    if not keyword:
        return None, f"Zona '{zona}' no válida. Use: norte, centro, sur."

    client = MongoDB.get_client()
    matches = []
    for db_name in client.list_database_names():
        if not db_name.startswith('campeonato_'):
            continue
        db = MongoDB.get_database(db_name)
        meta = db.metadata.find_one({}, {'_id': 0})
        if not meta:
            continue
        nombre = meta.get('nombre_campeonato', '')
        nombre_lower = nombre.lower()
        if keyword not in nombre_lower:
            continue
        # If a year filter is given, also require it in the name
        if anio and str(anio) not in nombre_lower:
            continue
        matches.append((meta.get('created_at'), nombre, db))

    # Sort by created_at
    matches.sort(key=lambda x: x[0] or '')
    return [(m[1], m[2]) for m in matches], None


def _calculate_zona_finalists(zona: str, anio: str = None):
    """
    Core logic: for each category present in any control of the zone
    (and year, if specified), pick each gymnast's best puntajeTotal
    (identified by RUT), then return top-8 sorted descending.

    Returns: (results_dict, error_str)
      results_dict = { category_name: [ enriched_gymnast_doc, ... ] }  (top-8, sorted)
      Each doc has an extra 'controles' key: list of {campeonato, puntajeTotal}.
    """
    from app.utils.db import MongoDB
    databases_with_meta, err = _get_zona_championships_with_meta(zona, anio)
    if err:
        return None, err
    if not databases_with_meta:
        year_hint = f" del año {anio}" if anio else ""
        return None, f"No se encontraron campeonatos para la zona '{zona}'{year_hint}."

    # Excluded collections
    EXCLUDED = {'metadata', 'jueces'}

    # all_by_cat[category][rut] = {'best': gymnast_doc, 'controles': [{campeonato, puntajeTotal}, ...]}
    all_by_cat = {}

    for camp_name, db in databases_with_meta:
        all_cols = [c for c in db.list_collection_names() if c not in EXCLUDED]
        for col_name in all_cols:
            gymnasts = list(db[col_name].find({}, {'_id': 0}))
            if col_name not in all_by_cat:
                all_by_cat[col_name] = {}

            for g in gymnasts:
                rut = g.get('rut', '').strip()
                if not rut:
                    rut = f'__nombre__{g.get("nombre", "")}'
                total = g.get('puntajeTotal', 0.0) or 0.0
                control_entry = {'campeonato': camp_name, 'puntajeTotal': round(total, 3)}

                if rut not in all_by_cat[col_name]:
                    all_by_cat[col_name][rut] = {'best': g, 'controles': [control_entry]}
                else:
                    all_by_cat[col_name][rut]['controles'].append(control_entry)
                    if total > (all_by_cat[col_name][rut]['best'].get('puntajeTotal', 0.0) or 0.0):
                        all_by_cat[col_name][rut]['best'] = g

    # Sort each category and take top-8
    from app.services.scoring_service import calculate_e_score
    results = {}
    for cat_name, gymnasts_by_rut in all_by_cat.items():
        all_gymnasts = []
        for data in gymnasts_by_rut.values():
            enriched = dict(data['best'])          # copy the best doc
            enriched['controles'] = sorted(data['controles'], key=lambda c: c['campeonato'])
            all_gymnasts.append(enriched)

        sorted_gymnasts = sorted(
            all_gymnasts,
            key=lambda g: (g.get('puntajeTotal', 0), calculate_e_score(g)),
            reverse=True
        )
        results[cat_name] = sorted_gymnasts[:8]

    return results, None


@bp.route('/finalistas/<zona>', methods=['GET'])
def get_finalists(zona):
    """Return top-8 finalists per category for a given zone.
    Optional query param: anio (e.g. ?anio=2026). Defaults to current year.
    """
    try:
        from datetime import datetime
        anio = request.args.get('anio', str(datetime.utcnow().year))
        results, err = _calculate_zona_finalists(zona, anio)
        if err:
            return jsonify({'error': err}), 400

        # Serialize for JSON
        output = []
        for cat_name, gymnasts in results.items():
            output.append({
                'categoria': cat_name,
                'finalistas': [
                    {
                        'rut':          g.get('rut', ''),
                        'nombre':       g.get('nombre', ''),
                        'club':         g.get('club', ''),
                        'puntajeTotal': g.get('puntajeTotal', 0.0),
                        'controles':    g.get('controles', [])
                    }
                    for g in gymnasts
                ]
            })

        return jsonify({
            'success': True,
            'zona': zona,
            'anio': anio,
            'categorias': output
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/finalistas/<zona>/export/pdf', methods=['GET'])
def export_finalists_pdf(zona):
    """Export finalist results as PDF for a given zone.
    Optional query param: anio (e.g. ?anio=2026). Defaults to current year.
    """
    try:
        from datetime import datetime
        anio = request.args.get('anio', str(datetime.utcnow().year))
        results, err = _calculate_zona_finalists(zona, anio)
        if err:
            return jsonify({'error': err}), 400

        zona_label = zona.replace('norte', 'Norte').replace('centro', 'Centro').replace('sur', 'Sur')
        championship_name = f"Finalistas Zona {zona_label} {anio}"

        categories_data = [
            {'categoria': cat_name, 'gimnastas': gymnasts}
            for cat_name, gymnasts in results.items()
        ]

        pdf_file = excel_service.export_to_pdf(championship_name, categories_data)

        return send_file(
            pdf_file,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{championship_name}.pdf"
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/finalistas/<zona>/export/excel', methods=['GET'])
def export_finalists_excel(zona):
    """Export finalist results as editable Excel for a given zone.
    Optional query param: anio (e.g. ?anio=2026). Defaults to current year.
    """
    try:
        from datetime import datetime
        anio = request.args.get('anio', str(datetime.utcnow().year))
        results, err = _calculate_zona_finalists(zona, anio)
        if err:
            return jsonify({'error': err}), 400

        zona_label = zona.replace('norte', 'Norte').replace('centro', 'Centro').replace('sur', 'Sur')
        championship_name = f"Finalistas Zona {zona_label} {anio}"

        categories_data = [
            {'categoria': cat_name, 'gimnastas': gymnasts}
            for cat_name, gymnasts in results.items()
        ]

        excel_file = excel_service.export_to_excel(championship_name, categories_data)

        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f"{championship_name}.xlsx"
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
