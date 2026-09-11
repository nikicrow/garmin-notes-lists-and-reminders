"""Current application schema assembled from immutable revision snapshots.

The Phase 2 snapshot is copied into separate ``Table`` objects so ORM mappings
can evolve without retroactively changing Alembic revisions.
"""

from sqlalchemy import MetaData

from tuck_api.schema import phase2

metadata = MetaData(naming_convention=phase2.metadata.naming_convention)
for snapshot_table in phase2.application_tables:
    snapshot_table.to_metadata(metadata)

users = metadata.tables["users"]
user_sessions = metadata.tables["user_sessions"]
notes = metadata.tables["notes"]
lists = metadata.tables["lists"]
resource_memberships = metadata.tables["resource_memberships"]
list_items = metadata.tables["list_items"]
reminders = metadata.tables["reminders"]
push_subscriptions = metadata.tables["push_subscriptions"]
reminder_recipients = metadata.tables["reminder_recipients"]
notification_deliveries = metadata.tables["notification_deliveries"]

application_tables = (
    users,
    user_sessions,
    notes,
    lists,
    resource_memberships,
    list_items,
    reminders,
    push_subscriptions,
    reminder_recipients,
    notification_deliveries,
)
