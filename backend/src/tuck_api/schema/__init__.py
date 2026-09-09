"""Current application schema assembled from immutable revision snapshots.

The Phase 1 snapshot is copied into separate ``Table`` objects so ORM mappings
can evolve without retroactively changing Alembic revisions 0002–0006.
"""

from sqlalchemy import MetaData

from tuck_api.schema import phase1

metadata = MetaData(naming_convention=phase1.metadata.naming_convention)
for snapshot_table in phase1.application_tables:
    snapshot_table.to_metadata(metadata)

users = metadata.tables["users"]
user_sessions = metadata.tables["user_sessions"]
notes = metadata.tables["notes"]
lists = metadata.tables["lists"]
resource_memberships = metadata.tables["resource_memberships"]
list_items = metadata.tables["list_items"]
reminders = metadata.tables["reminders"]

application_tables = (
    users,
    user_sessions,
    notes,
    lists,
    resource_memberships,
    list_items,
    reminders,
)
