"""Regression for upgrading a non-empty pre-metering database."""

from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_existing_usage_gets_distinct_call_ids_without_changing_amounts():
    target = [("billing", "0002_metered_usage")]
    executor = MigrationExecutor(connection)
    executor.migrate([("billing", "0001_initial")])
    try:
        old_apps = executor.loader.project_state([("billing", "0001_initial")]).apps
        User = old_apps.get_model("auth", "User")
        Usage = old_apps.get_model("billing", "UsageRecord")
        user = User.objects.create(username="legacy-migration")
        Usage.objects.create(user_id=user.pk, tokens_in=15, tokens_out=8, cost="0.125")
        Usage.objects.create(user_id=user.pk, tokens_in=16, tokens_out=9, cost="0.25")
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        upgraded = executor.loader.project_state(target).apps.get_model("billing", "UsageRecord")
        rows = list(upgraded.objects.filter(user_id=user.pk).order_by("id"))
        assert len({row.call_id for row in rows}) == 2
        assert all(row.call_id is not None for row in rows)
        assert [row.cost for row in rows] == [Decimal("0.125"), Decimal("0.25")]
        assert all(row.measurement == "legacy" for row in rows)
    finally:
        MigrationExecutor(connection).migrate(target)
