"""Add revocable personal access links for judges (existing links are not issued)."""
from alembic import op
import sqlalchemy as sa

revision = 'd39e82a10b73'
down_revision = 'c28d71f09a62'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('judge_access_token_hash', sa.String(64), nullable=True))
        batch.add_column(sa.Column('judge_access_version', sa.String(36), nullable=True))
        batch.create_unique_constraint('uq_users_judge_access_token_hash', ['judge_access_token_hash'])


def downgrade():
    with op.batch_alter_table('users') as batch:
        batch.drop_constraint('uq_users_judge_access_token_hash', type_='unique')
        batch.drop_column('judge_access_version')
        batch.drop_column('judge_access_token_hash')
