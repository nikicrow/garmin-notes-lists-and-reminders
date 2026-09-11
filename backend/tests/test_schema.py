from tuck_api import models, schema
from tuck_api.schema import phase2


def test_orm_models_use_the_canonical_schema_tables() -> None:
    expected_tables = {
        models.User: schema.users,
        models.UserSession: schema.user_sessions,
        models.Note: schema.notes,
        models.List: schema.lists,
        models.ResourceMembership: schema.resource_memberships,
        models.ListItem: schema.list_items,
        models.Reminder: schema.reminders,
        models.PushSubscription: schema.push_subscriptions,
        models.ReminderRecipient: schema.reminder_recipients,
        models.NotificationDelivery: schema.notification_deliveries,
    }

    for model, table in expected_tables.items():
        assert model.__table__ is table
        assert models.Base.metadata.tables[table.name] is table


def test_current_schema_is_independent_from_the_migration_snapshot() -> None:
    for current_table, snapshot_table in zip(
        schema.application_tables, phase2.application_tables, strict=True
    ):
        assert current_table is not snapshot_table
        assert current_table.name == snapshot_table.name
        assert tuple(current_table.columns.keys()) == tuple(snapshot_table.columns.keys())
