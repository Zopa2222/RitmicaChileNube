"""Store published score breakdown; legacy snapshots remain unknown."""
from alembic import op
import sqlalchemy as sa

revision = 'c28d71f09a62'
down_revision = 'b19a82e04c31'
branch_labels = None
depends_on = None


def upgrade():
    for name in ('db_score', 'da_score', 'discount'):
        op.add_column('published_results', sa.Column(name, sa.Numeric(5, 2), nullable=True))


def downgrade():
    for name in ('discount', 'da_score', 'db_score'):
        op.drop_column('published_results', name)
