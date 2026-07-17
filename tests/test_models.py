"""Lightweight structural checks for the ORM models.

These do not touch a real database (that's ticket 21's test harness); they
just confirm the models import cleanly and are wired up with the expected
table names, columns, and cascade behavior on their foreign keys.
"""

from sqlalchemy import DateTime

from memory_ai.models import Base, Card, Folder, Review, Source, Subject, User, UserSettings


def test_tablenames() -> None:
    assert User.__tablename__ == "users"
    assert UserSettings.__tablename__ == "user_settings"
    assert Subject.__tablename__ == "subjects"
    assert Folder.__tablename__ == "folders"
    assert Source.__tablename__ == "sources"
    assert Card.__tablename__ == "cards"
    assert Review.__tablename__ == "reviews"


def test_all_models_registered_on_metadata() -> None:
    assert set(Base.metadata.tables) == {
        "users",
        "user_settings",
        "subjects",
        "folders",
        "sources",
        "cards",
        "reviews",
    }


def test_user_email_is_unique() -> None:
    email_column = Base.metadata.tables["users"].c.email
    assert email_column.unique
    assert not email_column.nullable


def test_cascade_chain_foreign_keys() -> None:
    expected_cascades = {
        ("user_settings", "user_id", "users"),
        ("subjects", "user_id", "users"),
        ("folders", "subject_id", "subjects"),
        ("sources", "folder_id", "folders"),
        ("cards", "source_id", "sources"),
        ("cards", "folder_id", "folders"),
        ("reviews", "card_id", "cards"),
    }
    for table_name, column_name, target_table in expected_cascades:
        table = Base.metadata.tables[table_name]
        fk = next(iter(table.c[column_name].foreign_keys))
        assert fk.column.table.name == target_table
        assert fk.ondelete == "CASCADE"


def test_cards_has_expected_indexes() -> None:
    cards = Base.metadata.tables["cards"]
    indexed_columns = {col.name for index in cards.indexes for col in index.columns}
    assert {"due_date", "folder_id"} <= indexed_columns


def test_due_date_is_plain_date_not_timestamp() -> None:
    due_date_column = Base.metadata.tables["cards"].c.due_date
    assert due_date_column.type.__class__.__name__ == "Date"


def test_created_at_columns_are_timezone_aware() -> None:
    for table_name in ("users", "subjects", "folders", "sources", "cards"):
        created_at_type = Base.metadata.tables[table_name].c.created_at.type
        assert isinstance(created_at_type, DateTime)
        assert created_at_type.timezone is True
