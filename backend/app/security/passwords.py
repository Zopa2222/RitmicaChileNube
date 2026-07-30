from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


_password_hasher = PasswordHasher()


def hash_password(raw_password):
    if not isinstance(raw_password, str) or not raw_password:
        raise ValueError('La contraseña no puede estar vacía')
    return _password_hasher.hash(raw_password)


def verify_password(password_hash, raw_password):
    if not password_hash or not isinstance(raw_password, str):
        return False, False

    try:
        valid = _password_hasher.verify(password_hash, raw_password)
    except (VerifyMismatchError, InvalidHashError):
        return False, False

    needs_rehash = valid and _password_hasher.check_needs_rehash(password_hash)
    return valid, needs_rehash
