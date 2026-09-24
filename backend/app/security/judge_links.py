"""Reusable bearer links; authorization still follows live assignment windows."""
import hashlib
import re
import secrets
import uuid

from app.models import AccountType


def token_digest(token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def issue_judge_link(judge):
    if judge.account_type != AccountType.JUDGE:
        raise ValueError('Los enlaces son exclusivos para jueces')
    token = secrets.token_urlsafe(32)
    judge.judge_access_token_hash = token_digest(token)
    judge.judge_access_version = str(uuid.uuid4())
    # A fragment is not sent to HTTP servers, access logs or referrer headers.
    return {'username': judge.username, 'access_path': f'/acceso-juez#{token}'}
