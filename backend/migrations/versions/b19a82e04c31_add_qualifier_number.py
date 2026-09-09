"""Persist qualifier number; legacy championships remain unnumbered."""
from alembic import op
import sqlalchemy as sa

revision = 'b19a82e04c31'
down_revision = 'acf6e5ed93a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('championships', sa.Column('qualifier_number', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('championships', 'qualifier_number')
