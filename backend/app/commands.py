import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import select

from app.extensions import db
from app.models import (
    AccountType,
    CredentialEvent,
    CredentialEventType,
    SystemRole,
    User,
)
from app.security.passwords import hash_password


def _fixed_user(account_type, username, password, first_name, last_name):
    existing = db.session.execute(
        select(User).where(User.account_type == account_type)
    ).scalar_one_or_none()
    if existing:
        return existing, False

    user = User(
        account_type=account_type,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        username=username.strip().upper(),
        password_hash=hash_password(password),
    )
    db.session.add(user)
    db.session.flush()
    return user, True


@click.command('bootstrap-fixed-users')
@click.option(
    '--super-username',
    envvar='SUPER_ADMIN_USERNAME',
    required=True,
)
@click.option(
    '--super-password',
    envvar='SUPER_ADMIN_PASSWORD',
    required=True,
    hide_input=True,
)
@click.option(
    '--admin-username',
    envvar='GLOBAL_ADMIN_USERNAME',
    required=True,
)
@click.option(
    '--admin-password',
    envvar='GLOBAL_ADMIN_PASSWORD',
    required=True,
    hide_input=True,
)
@click.option(
    '--super-name',
    envvar='SUPER_ADMIN_NAME',
    default='Super',
)
@click.option(
    '--super-last-name',
    envvar='SUPER_ADMIN_LAST_NAME',
    default='Administrador',
)
@click.option(
    '--admin-name',
    envvar='GLOBAL_ADMIN_NAME',
    default='Administrador',
)
@click.option(
    '--admin-last-name',
    envvar='GLOBAL_ADMIN_LAST_NAME',
    default='Global',
)
@with_appcontext
def bootstrap_fixed_users(
    super_username,
    super_password,
    admin_username,
    admin_password,
    super_name,
    super_last_name,
    admin_name,
    admin_last_name,
):
    """Create the one super administrator and one global administrator."""
    super_admin, super_created = _fixed_user(
        AccountType.SUPER_ADMIN,
        super_username,
        super_password,
        super_name,
        super_last_name,
    )
    global_admin, admin_created = _fixed_user(
        AccountType.GLOBAL_ADMIN,
        admin_username,
        admin_password,
        admin_name,
        admin_last_name,
    )

    roles = db.session.get(SystemRole, 1)
    if roles is None:
        roles = SystemRole(
            id=1,
            super_admin_user_id=super_admin.id,
            global_admin_user_id=global_admin.id,
        )
        db.session.add(roles)
    elif (
        roles.super_admin_user_id != super_admin.id
        or roles.global_admin_user_id != global_admin.id
    ):
        raise click.ClickException(
            'Las cuentas fijas existentes no coinciden con system_roles'
        )

    for user, created in (
        (super_admin, super_created),
        (global_admin, admin_created),
    ):
        if created:
            db.session.add(
                CredentialEvent(
                    user_id=user.id,
                    event_type=CredentialEventType.CREATED,
                    created_by_user_id=super_admin.id,
                )
            )

    db.session.commit()
    current_app.logger.info('Fixed system accounts are ready')
    click.echo('Cuentas fijas creadas o verificadas correctamente.')


@click.command('purge-expired-championships')
@with_appcontext
def purge_expired_championships_command():
    """Elimina definitivamente los campeonatos vencidos en recuperación."""
    from app.routes.cloud_administration import purge_expired_championships

    purged = purge_expired_championships()
    click.echo(f'Campeonatos eliminados definitivamente: {len(purged)}')
