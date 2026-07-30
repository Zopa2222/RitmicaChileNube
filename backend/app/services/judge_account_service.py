import re
import secrets
import unicodedata

from sqlalchemy import or_, select

from app.extensions import db
from app.models import (
    AccountType,
    CredentialEvent,
    CredentialEventType,
    User,
)
from app.security.passwords import hash_password


PASSWORD_WORDS = (
    'Alerce',
    'Andes',
    'Atlas',
    'Brisa',
    'Canelo',
    'Cobre',
    'Condor',
    'Copihue',
    'Estrella',
    'Lago',
    'Lima',
    'Luna',
    'Nube',
    'Pacifico',
    'Quillay',
    'Sol',
)


class JudgeAccountError(ValueError):
    pass


def normalize_identity_text(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    without_accents = ''.join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return re.sub(r'[^A-Z0-9]', '', without_accents.upper())


def normalize_rut(value):
    normalized = normalize_identity_text(value)
    if not re.fullmatch(r'\d{6,8}[0-9K]', normalized):
        raise JudgeAccountError('El RUT no tiene un formato válido')

    digits = normalized[:-1]
    expected_digit = normalized[-1]
    factor = 2
    total = 0
    for digit in reversed(digits):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    calculated_digit = (
        '0' if remainder == 11
        else 'K' if remainder == 10
        else str(remainder)
    )
    if expected_digit != calculated_digit:
        raise JudgeAccountError('El dígito verificador del RUT no es válido')
    return normalized


def build_judge_username(first_name, last_name, rut_normalized):
    first_token = str(first_name or '').strip().split()
    last_token = str(last_name or '').strip().split()
    if not first_token or not last_token:
        raise JudgeAccountError('Nombre y apellido son obligatorios')

    username = normalize_identity_text(
        f'{first_token[0]}{last_token[0]}{rut_normalized}'
    )
    if not username:
        raise JudgeAccountError('No fue posible generar el nombre de usuario')
    if len(username) > 120:
        raise JudgeAccountError(
            'El usuario generado supera el largo permitido'
        )
    return username


def generate_initial_password():
    words = secrets.SystemRandom().sample(PASSWORD_WORDS, 3)
    number = secrets.randbelow(90) + 10
    return f'{words[0]}-{words[1]}-{number}-{words[2]}'


def find_judge(query):
    normalized_query = str(query or '').strip()
    if not normalized_query:
        return []

    compact_query = normalize_identity_text(normalized_query)
    conditions = [
        User.first_name.ilike(f'%{normalized_query}%'),
        User.last_name.ilike(f'%{normalized_query}%'),
        User.username.ilike(f'%{compact_query}%'),
    ]
    if compact_query:
        conditions.append(User.rut_normalized.ilike(f'%{compact_query}%'))

    return db.session.execute(
        select(User)
        .where(
            User.account_type == AccountType.JUDGE,
            or_(*conditions),
        )
        .order_by(User.last_name, User.first_name)
        .limit(25)
    ).scalars().all()


def create_judge_account(first_name, last_name, rut, created_by_user_id):
    clean_first_name = str(first_name or '').strip()
    clean_last_name = str(last_name or '').strip()
    if not clean_first_name or not clean_last_name:
        raise JudgeAccountError('Nombre, apellido y RUT son obligatorios')
    if len(clean_first_name) > 100 or len(clean_last_name) > 100:
        raise JudgeAccountError('Nombre y apellido admiten hasta 100 caracteres')

    rut_normalized = normalize_rut(rut)
    existing_rut = db.session.execute(
        select(User).where(User.rut_normalized == rut_normalized)
    ).scalar_one_or_none()
    if existing_rut is not None:
        if existing_rut.account_type != AccountType.JUDGE:
            raise JudgeAccountError(
                'El RUT ya pertenece a una cuenta que no es de juez'
            )
        return existing_rut, None

    username = build_judge_username(
        clean_first_name,
        clean_last_name,
        rut_normalized,
    )
    if db.session.execute(
        select(User.id).where(User.username == username)
    ).scalar_one_or_none():
        raise JudgeAccountError(
            'El usuario generado ya existe; revise los datos antes de continuar'
        )

    initial_password = generate_initial_password()
    judge = User(
        account_type=AccountType.JUDGE,
        first_name=clean_first_name,
        last_name=clean_last_name,
        rut_normalized=rut_normalized,
        username=username,
        password_hash=hash_password(initial_password),
    )
    db.session.add(judge)
    db.session.flush()
    db.session.add(
        CredentialEvent(
            user_id=judge.id,
            event_type=CredentialEventType.CREATED,
            created_by_user_id=created_by_user_id,
        )
    )
    return judge, {
        'username': username,
        'password': initial_password,
    }
