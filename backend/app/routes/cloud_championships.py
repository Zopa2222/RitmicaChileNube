import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    AccountType,
    AuditLog,
    Bench,
    Category,
    Championship,
    ChampionshipStatus,
    CompetitionDay,
    FileKind,
    FileObject,
    Gymnast,
    JudgeAssignment,
    JudgeRole,
    ImportPreview,
    Session,
    SystemRole,
    User,
    UserStatus,
)
from app.security.permissions import account_types_required
from app.services.cloud_excel_service import (
    ExcelImportError,
    analyze_excel,
    render_preview,
    validate_cutoff_decisions,
    single_day_analysis,
    confirmed_single_day_plan,
)
from app.services.file_storage_service import delete_object, store_bytes
from app.services.judge_account_service import (
    JudgeAccountError,
    create_judge_account,
    normalize_rut,
)
from app.services.championship_operations_service import (
    ChampionshipOperationError,
    initialize_score_entries_for_assignment,
    recalculate_judge_access_window,
)


bp = Blueprint(
    'cloud_championships',
    __name__,
    url_prefix='/api/v1/championships',
)
ADMIN_ACCOUNT_TYPES = (
    AccountType.SUPER_ADMIN,
    AccountType.GLOBAL_ADMIN,
)


def parse_uuid(raw_value, field_name='id'):
    try:
        return uuid.UUID(str(raw_value))
    except (TypeError, ValueError, AttributeError):
        raise ExcelImportError(f'{field_name} no es válido') from None


def get_championship_or_404(championship_id):
    try:
        parsed_id = parse_uuid(championship_id, 'championship_id')
    except ExcelImportError:
        return None
    return db.session.get(Championship, parsed_id)


def get_preview_or_404(championship, preview_id):
    try:
        parsed_id = parse_uuid(preview_id, 'preview_id')
    except ExcelImportError:
        return None
    return db.session.execute(
        select(ImportPreview).where(
            ImportPreview.id == parsed_id,
            ImportPreview.championship_draft_id == championship.id,
        )
    ).scalar_one_or_none()


def championship_response(championship):
    return {
        'id': str(championship.id),
        'name': championship.name,
        'kind': championship.kind,
        'zone': championship.zone,
        'qualifier_number': championship.qualifier_number,
        'start_date': championship.start_date.isoformat(),
        'timezone': championship.timezone,
        'status': championship.status.value,
        'responsible_admin_id': str(championship.responsible_admin_id),
        'created_at': championship.created_at.isoformat(),
    }


def preview_response(preview, include_gymnasts=False):
    return {
        'id': str(preview.id),
        'championship_id': str(preview.championship_draft_id),
        'expires_at': preview.expires_at.isoformat(),
        'decisions': preview.decisions,
        'preview': render_preview(
            preview.detected_data,
            preview.decisions,
            include_gymnasts=include_gymnasts,
        ),
    }


def is_preview_expired(preview):
    expires_at = preview.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def validation_error(message, code='VALIDATION_ERROR', status=400):
    return jsonify({'error': message, 'code': code}), status


@bp.get('')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def list_championships(current_user):
    championships = db.session.execute(
        select(Championship).order_by(Championship.created_at.desc())
    ).scalars().all()
    return jsonify({
        'championships': [
            championship_response(championship)
            for championship in championships
        ]
    })


@bp.post('')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def create_championship(current_user):
    payload = request.get_json(silent=True) or {}
    name = str(payload.get('name', '')).strip()
    kind = str(payload.get('kind', '')).strip().upper()
    zone = str(payload.get('zone', '')).strip().upper()
    raw_start_date = payload.get('start_date')
    qualifier_number = payload.get('qualifier_number')
    if zone not in {'NORTE', 'CENTRO', 'SUR'}:
        return validation_error('La zona debe ser Norte, Centro o Sur')
    if kind not in {'CLASIFICATORIO', 'FINAL'}:
        return validation_error('El tipo debe ser Clasificatorio o Final')
    if kind == 'CLASIFICATORIO':
        if type(qualifier_number) is not int or qualifier_number not in (1, 2):
            return validation_error('Selecciona Clasificatorio 1 o 2')
    elif qualifier_number is not None:
        return validation_error('Solo los clasificatorios admiten número')

    if not name or not kind or not zone or not raw_start_date:
        return validation_error(
            'name, kind, zone y start_date son obligatorios'
        )
    try:
        start_date = date.fromisoformat(str(raw_start_date))
    except ValueError:
        return validation_error('start_date debe usar formato YYYY-MM-DD')

    if current_user.account_type == AccountType.GLOBAL_ADMIN:
        responsible_admin_id = current_user.id
    else:
        system_roles = db.session.get(SystemRole, 1)
        if system_roles is None:
            return validation_error(
                'Debe crear las cuentas fijas antes del campeonato',
                code='SYSTEM_NOT_BOOTSTRAPPED',
                status=409,
            )
        responsible_admin_id = system_roles.global_admin_user_id

    championship = Championship(
        name=name,
        kind=kind,
        zone=zone,
        qualifier_number=qualifier_number,
        start_date=start_date,
        status=ChampionshipStatus.DRAFT,
        responsible_admin_id=responsible_admin_id,
    )
    db.session.add(championship)
    db.session.flush()
    db.session.add(
        AuditLog(
            actor_user_id=current_user.id,
            action='CHAMPIONSHIP_CREATED',
            championship_id=championship.id,
            entity_type='CHAMPIONSHIP',
            entity_id=championship.id,
            details={
                'name': name,
                'kind': kind,
                'zone': zone,
                'qualifier_number': qualifier_number,
            },
        )
    )
    db.session.commit()
    return jsonify({
        'championship': championship_response(championship)
    }), 201


@bp.get('/<championship_id>')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def get_championship(current_user, championship_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )

    counts = db.session.execute(
        select(
            func.count(func.distinct(CompetitionDay.id)),
            func.count(func.distinct(Category.id)),
            func.count(func.distinct(Gymnast.id)),
        )
        .select_from(Championship)
        .outerjoin(
            CompetitionDay,
            CompetitionDay.championship_id == Championship.id,
        )
        .outerjoin(
            Category,
            Category.championship_id == Championship.id,
        )
        .outerjoin(Gymnast, Gymnast.category_id == Category.id)
        .where(Championship.id == championship.id)
    ).one()
    response = championship_response(championship)
    response['counts'] = {
        'days': counts[0],
        'categories': counts[1],
        'gymnasts': counts[2],
    }
    return jsonify({'championship': response})


def analyze_day_upload(contents, sequence=1):
    analysis = analyze_excel(contents)
    if not analysis.get('has_judges_sheet'):
        raise ExcelImportError('Falta la hoja obligatoria Jueces')
    if not analysis.get('judges'):
        raise ExcelImportError('La hoja Jueces no contiene jueces con RUT y roles válidos')
    if len(analysis['sheets']) != 1:
        raise ExcelImportError('Cada archivo debe contener exactamente una hoja de orden del día')
    analysis = single_day_analysis(analysis, sequence)
    render_preview(analysis)
    return analysis


@bp.post('/validate-day-file')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def validate_day_file(current_user):
    upload = request.files.get('file')
    if upload is None or not upload.filename:
        return validation_error('Debe adjuntar un archivo Excel')
    safe_name = secure_filename(upload.filename)
    if not safe_name.lower().endswith('.xlsx'):
        return validation_error('El archivo debe tener extensión .xlsx')

    contents = upload.read()
    if not contents:
        return validation_error('El archivo está vacío')
    if len(contents) > current_app.config['MAX_CONTENT_LENGTH']:
        return validation_error('El archivo supera el tamaño permitido')

    try:
        analyze_day_upload(contents)
    except ExcelImportError as error:
        return validation_error(str(error), code='INVALID_EXCEL')
    return jsonify({'valid': True})


@bp.post('/<championship_id>/import-previews')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def create_import_preview(current_user, championship_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    if championship.status != ChampionshipStatus.DRAFT:
        return validation_error(
            'Solo un campeonato en borrador admite importaciones',
            code='CHAMPIONSHIP_NOT_DRAFT',
            status=409,
        )
    try:
        competition_date = date.fromisoformat(
            str(request.form.get('competition_date') or '')
        )
    except ValueError:
        return validation_error('Debe seleccionar una fecha válida para el día')
    if competition_date < championship.start_date:
        return validation_error('La fecha no puede ser anterior al primer día del campeonato')
    existing_date = db.session.execute(
        select(CompetitionDay.id).where(
            CompetitionDay.championship_id == championship.id,
            CompetitionDay.competition_date == competition_date,
        )
    ).scalar_one_or_none()
    if existing_date:
        return validation_error('Ya existe un día con esa fecha', code='COMPETITION_DAY_CONFLICT', status=409)

    existing_days = db.session.execute(
        select(CompetitionDay.sequence).where(
            CompetitionDay.championship_id == championship.id
        )
    ).scalars().all()
    next_sequence = max(existing_days, default=0) + 1
    pending = db.session.execute(
        select(ImportPreview).where(
            ImportPreview.championship_draft_id == championship.id,
            ImportPreview.expires_at > datetime.now(timezone.utc),
        )
    ).scalars().all()
    reserved = [
        item.detected_data.get('sheets', [{}])[0].get('sequence', 0)
        for item in pending
        if item.detected_data.get('sheets')
        and not item.decisions.get('import_confirmed_at')
    ]
    proposed_sequence = max([next_sequence - 1, *reserved], default=0) + 1

    upload = request.files.get('file')
    if upload is None or not upload.filename:
        return validation_error('Debe adjuntar un archivo Excel')
    safe_name = secure_filename(upload.filename)
    if not safe_name.lower().endswith('.xlsx'):
        return validation_error('El archivo debe tener extensión .xlsx')

    contents = upload.read()
    if not contents:
        return validation_error('El archivo está vacío')
    if len(contents) > current_app.config['MAX_CONTENT_LENGTH']:
        return validation_error('El archivo supera el tamaño permitido')

    try:
        analysis = analyze_day_upload(contents, proposed_sequence)
    except ExcelImportError as error:
        return validation_error(str(error), code='INVALID_EXCEL')

    file_id = uuid.uuid4()
    object_name = (
        f'imports/{championship.id}/{file_id}_{safe_name}'
    )
    try:
        store_bytes(
            object_name,
            contents,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    except Exception:
        current_app.logger.exception('Unable to store source Excel')
        return validation_error(
            'No fue posible almacenar el archivo',
            code='FILE_STORAGE_ERROR',
            status=503,
        )

    try:
        source_file = FileObject(
            id=file_id,
            championship_id=championship.id,
            kind=FileKind.SOURCE_EXCEL,
            bucket_object=object_name,
            original_name=upload.filename,
            sha256=hashlib.sha256(contents).hexdigest(),
        )
        decisions = {'sheets': {}}
        for sheet in analysis['sheets']:
            if sheet['detected_cutoff_row'] is not None:
                decisions['sheets'][str(sheet['sequence'])] = {
                    'cutoff_row': sheet['detected_cutoff_row'],
                    'confirmed': False,
                    'source': 'AUTO',
                }
        decisions['competition_date'] = competition_date.isoformat()

        preview = ImportPreview(
            championship_draft_id=championship.id,
            source_file_id=source_file.id,
            detected_data=analysis,
            decisions=decisions,
            expires_at=datetime.now(timezone.utc) + timedelta(
                hours=current_app.config['IMPORT_PREVIEW_TTL_HOURS']
            ),
        )
        db.session.add_all([source_file, preview])
        db.session.flush()
        db.session.add(
            AuditLog(
                actor_user_id=current_user.id,
                action='IMPORT_PREVIEW_CREATED',
                championship_id=championship.id,
                entity_type='IMPORT_PREVIEW',
                entity_id=preview.id,
                details={
                    'filename': upload.filename,
                    'sha256': source_file.sha256,
                },
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            delete_object(object_name)
        except Exception:
            current_app.logger.exception('Unable to remove orphan source file')
        raise

    return jsonify(preview_response(preview)), 201


@bp.get('/<championship_id>/import-previews/<preview_id>')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def get_import_preview(current_user, championship_id, preview_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    preview = get_preview_or_404(championship, preview_id)
    if preview is None:
        return validation_error(
            'Previsualización no encontrada',
            code='IMPORT_PREVIEW_NOT_FOUND',
            status=404,
        )
    return jsonify(preview_response(preview))


@bp.patch('/<championship_id>/import-previews/<preview_id>')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def update_import_preview(current_user, championship_id, preview_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    preview = get_preview_or_404(championship, preview_id)
    if preview is None:
        return validation_error(
            'Previsualización no encontrada',
            code='IMPORT_PREVIEW_NOT_FOUND',
            status=404,
        )
    if is_preview_expired(preview):
        return validation_error(
            'La previsualización expiró',
            code='IMPORT_PREVIEW_EXPIRED',
            status=410,
        )

    payload = request.get_json(silent=True) or {}
    requested = []
    if payload.get('accept_detected'):
        requested.extend(
            {
                'sequence': sheet['sequence'],
                'cutoff_row': sheet['detected_cutoff_row'],
                'confirmed': True,
                'source': 'AUTO',
            }
            for sheet in preview.detected_data['sheets']
            if sheet['detected_cutoff_row'] is not None
        )
    requested.extend(payload.get('sheets') or [])
    if not requested:
        return validation_error('Debe enviar al menos una decisión de corte')

    try:
        decisions = validate_cutoff_decisions(
            preview.detected_data,
            requested,
            preview.decisions,
        )
        rendered = render_preview(preview.detected_data, decisions)
    except ExcelImportError as error:
        return validation_error(str(error), code='INVALID_CUTOFF')

    preview.decisions = decisions
    db.session.add(
        AuditLog(
            actor_user_id=current_user.id,
            action='IMPORT_CUTOFFS_UPDATED',
            championship_id=championship.id,
            entity_type='IMPORT_PREVIEW',
            entity_id=preview.id,
            details={
                'sheets': requested,
                'total_categories': rendered['total_categories'],
                'total_gymnasts': rendered['total_gymnasts'],
            },
        )
    )
    db.session.commit()
    return jsonify(preview_response(preview))


@bp.post('/<championship_id>/import-previews/<preview_id>/confirm')
@account_types_required(*ADMIN_ACCOUNT_TYPES)
def confirm_import_preview(current_user, championship_id, preview_id):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error(
            'Campeonato no encontrado',
            code='CHAMPIONSHIP_NOT_FOUND',
            status=404,
        )
    if championship.status != ChampionshipStatus.DRAFT:
        return validation_error(
            'Solo un campeonato en borrador admite importaciones',
            code='CHAMPIONSHIP_NOT_DRAFT',
            status=409,
        )
    preview = get_preview_or_404(championship, preview_id)
    if preview is None:
        return validation_error(
            'Previsualización no encontrada',
            code='IMPORT_PREVIEW_NOT_FOUND',
            status=404,
        )
    if is_preview_expired(preview):
        return validation_error(
            'La previsualización expiró',
            code='IMPORT_PREVIEW_EXPIRED',
            status=410,
        )
    if preview.decisions.get('import_confirmed_at'):
        return validation_error(
            'La importación ya fue confirmada',
            code='IMPORT_ALREADY_CONFIRMED',
            status=409,
        )
    try:
        day_sequence = preview.detected_data['sheets'][0]['sequence']
        cutoff = preview.decisions.get('sheets', {}).get(str(day_sequence), {})
        if not cutoff.get('confirmed'):
            raise ExcelImportError(
                f'Falta confirmar el corte AM/PM del día {day_sequence}'
            )
        import_plan = [confirmed_single_day_plan(
            preview.detected_data,
            cutoff.get('cutoff_row'),
        )]
        competition_date = date.fromisoformat(
            str(preview.decisions.get('competition_date') or '')
        )
    except ExcelImportError as error:
        return validation_error(str(error), code='UNCONFIRMED_CUTOFF')
    except (ValueError, TypeError):
        return validation_error('Debe seleccionar una fecha válida para el día')

    if competition_date < championship.start_date:
        return validation_error('La fecha no puede ser anterior al primer día del campeonato')

    existing_day = db.session.execute(
        select(CompetitionDay.id).where(
            CompetitionDay.championship_id == championship.id,
            (CompetitionDay.sequence == day_sequence)
            | (CompetitionDay.competition_date == competition_date),
        )
    ).scalar_one_or_none()
    if existing_day:
        return validation_error(
            'Ya existe un día con esa secuencia o fecha',
            code='COMPETITION_DAY_CONFLICT',
            status=409,
        )

    source_file = db.session.get(FileObject, preview.source_file_id)
    if source_file is None:
        return validation_error(
            'No se encontró la planilla fuente',
            code='SOURCE_FILE_NOT_FOUND',
            status=409,
        )
    total_categories = 0
    total_gymnasts = 0
    new_judge_credentials = []
    try:
        for sheet in import_plan:
            max_sequence = db.session.execute(
                select(func.max(CompetitionDay.sequence)).where(
                    CompetitionDay.championship_id == championship.id
                )
            ).scalar_one() or 0
            if sheet['sequence'] != max_sequence + 1:
                raise ExcelImportError(
                    'Otro día fue agregado mientras revisabas la planilla. Vuelve a cargarla.'
                )
            competition_day = CompetitionDay(
                championship_id=championship.id,
                sequence=sheet['sequence'],
                competition_date=(
                    competition_date
                ),
                source_sheet_name=sheet['name'],
            )
            db.session.add(competition_day)
            db.session.flush()

            for category_data in sheet['categories']:
                category = Category(
                    championship_id=championship.id,
                    competition_day_id=competition_day.id,
                    name=category_data['name'],
                    bench=category_data['bench'],
                    session=category_data['session'],
                    passing_order=category_data['passing_order'],
                    source_row=category_data['first_row'],
                )
                db.session.add(category)
                db.session.flush()
                total_categories += 1

                for gymnast_data in category_data['gymnasts']:
                    db.session.add(
                        Gymnast(
                            category_id=category.id,
                            full_name=gymnast_data['full_name'],
                            club_name=gymnast_data['club_name'],
                            passing_order=gymnast_data['passing_order'],
                        )
                    )
                    total_gymnasts += 1

            for judge_data in sheet['judges']:
                rut = normalize_rut(judge_data['rut'])
                judge = db.session.execute(
                    select(User).where(User.rut_normalized == rut)
                ).scalar_one_or_none()
                credentials = None
                if judge is None:
                    judge, credentials = create_judge_account(
                        judge_data['first_name'],
                        judge_data['last_name'],
                        rut,
                        current_user.id,
                    )
                    if credentials:
                        new_judge_credentials.append({
                            'judge': judge_data['full_name'],
                            **credentials,
                        })
                if judge.account_type != AccountType.JUDGE:
                    raise JudgeAccountError(
                        'El RUT de un juez pertenece a otra cuenta'
                    )
                if judge.status == UserStatus.DISABLED:
                    # Import assignments without undoing a manual deactivation.
                    # Authentication still requires an ACTIVE account.
                    pass
                if judge.status == UserStatus.LOCKED:
                    raise JudgeAccountError(
                        f'La cuenta de {judge_data["full_name"]} está bloqueada'
                    )
                if db.session.execute(
                    select(JudgeAssignment.id).where(
                        JudgeAssignment.championship_id == championship.id,
                        JudgeAssignment.judge_user_id == judge.id,
                        JudgeAssignment.competition_day_id == competition_day.id,
                        JudgeAssignment.bench == Bench(judge_data['bench']),
                        JudgeAssignment.session == Session(judge_data['session']),
                        JudgeAssignment.superseded_at.is_(None),
                    ).limit(1)
                ).scalar_one_or_none():
                    raise ExcelImportError(
                        f'{judge_data["full_name"]} ya tiene una asignación '
                        'en esa banca y jornada'
                    )
                role_count = db.session.execute(select(func.count(JudgeAssignment.id)).where(
                    JudgeAssignment.competition_day_id == competition_day.id,
                    JudgeAssignment.bench == Bench(judge_data['bench']),
                    JudgeAssignment.session == Session(judge_data['session']),
                    JudgeAssignment.role == JudgeRole(judge_data['role']),
                    JudgeAssignment.superseded_at.is_(None),
                )).scalar_one()
                if role_count >= 4:
                    raise ExcelImportError('Máximo 4 jueces por área, banca y jornada')
                role = JudgeRole(judge_data['role'])
                bench = Bench(judge_data['bench'])
                session = Session(judge_data['session'])
                categories = db.session.execute(
                    select(Category).where(
                        Category.competition_day_id == competition_day.id,
                        Category.bench == bench,
                        Category.session == session,
                    ).order_by(Category.passing_order)
                ).scalars().all()
                if not categories:
                    raise ExcelImportError(
                        f'No hay categorías para juez {judge_data["full_name"]}, '
                        f'banca {bench.value}, jornada {session.value}'
                    )
                assignment = JudgeAssignment(
                    championship_id=championship.id,
                    judge_user_id=judge.id,
                    competition_day_id=competition_day.id,
                    bench=bench,
                    session=session,
                    role=role,
                    effective_from_category_id=categories[0].id,
                    assigned_by_user_id=current_user.id,
                )
                db.session.add(assignment)
                db.session.flush()
                initialize_score_entries_for_assignment(assignment, categories)
                recalculate_judge_access_window(
                    judge.id, championship, competition_day
                )

        source_file.championship_id = championship.id

        updated_decisions = dict(preview.decisions)
        updated_decisions['import_confirmed_at'] = (
            datetime.now(timezone.utc).isoformat()
        )
        updated_decisions['confirmed_by_user_id'] = str(current_user.id)
        preview.decisions = updated_decisions
        db.session.add(
            AuditLog(
                actor_user_id=current_user.id,
                action='IMPORT_CONFIRMED',
                championship_id=championship.id,
                entity_type='IMPORT_PREVIEW',
                entity_id=preview.id,
                details={
                    'days': len(import_plan),
                    'categories': total_categories,
                    'gymnasts': total_gymnasts,
                },
            )
        )
        db.session.commit()
    except (IntegrityError, JudgeAccountError, ChampionshipOperationError, ExcelImportError):
        db.session.rollback()
        current_app.logger.exception('Import confirmation violated data rules')
        return validation_error(
            'La importación contiene datos incompatibles con categorías o jueces',
            code='IMPORT_CONFLICT',
            status=409,
        )

    return jsonify({
        'championship': championship_response(championship),
        'imported': {
            'days': len(import_plan),
            'categories': total_categories,
            'gymnasts': total_gymnasts,
            'new_judge_credentials': new_judge_credentials,
        },
    })
