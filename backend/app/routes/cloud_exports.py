import hashlib
import uuid

from flask import Blueprint, send_file

from app.extensions import db
from app.models import AccountType, FileKind, FileObject
from app.routes.cloud_championships import get_championship_or_404, validation_error
from app.security.permissions import account_types_required
from app.services.cloud_export_service import build_excel, build_pdf
from app.services.file_storage_service import FileStorageError, store_bytes


bp = Blueprint('cloud_exports', __name__, url_prefix='/api/v1/championships')
ADMINS = (AccountType.SUPER_ADMIN, AccountType.GLOBAL_ADMIN)


def _export(current_user, championship_id, kind, content_type, extension, builder):
    championship = get_championship_or_404(championship_id)
    if championship is None:
        return validation_error('Campeonato no encontrado', code='CHAMPIONSHIP_NOT_FOUND', status=404)
    output = builder(championship)
    contents = output.getvalue()
    filename = f'resultados-{championship.id}.{extension}'
    object_name = f'exports/{championship.id}/{uuid.uuid4()}.{extension}'
    try:
        store_bytes(object_name, contents, content_type)
        db.session.add(FileObject(
            championship_id=championship.id,
            kind=kind,
            bucket_object=object_name,
            original_name=filename,
            sha256=hashlib.sha256(contents).hexdigest(),
        ))
        db.session.commit()
    except FileStorageError as error:
        db.session.rollback()
        return validation_error(str(error), code='EXPORT_STORAGE_ERROR', status=503)
    output.seek(0)
    return send_file(output, mimetype=content_type, as_attachment=True,
                     download_name=filename)


@bp.get('/<championship_id>/exports/excel')
@account_types_required(*ADMINS)
def export_excel(current_user, championship_id):
    return _export(current_user, championship_id, FileKind.EXCEL_EXPORT,
                   'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                   'xlsx', build_excel)


@bp.get('/<championship_id>/exports/pdf')
@account_types_required(*ADMINS)
def export_pdf(current_user, championship_id):
    return _export(current_user, championship_id, FileKind.PDF_EXPORT,
                   'application/pdf', 'pdf', build_pdf)
