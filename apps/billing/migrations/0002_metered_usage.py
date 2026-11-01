"""Add metering without assigning the same UUID to existing usage rows."""
import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def assign_call_ids(apps, schema_editor):
    UsageRecord = apps.get_model("billing", "UsageRecord")
    for record in UsageRecord.objects.using(schema_editor.connection.alias).filter(call_id__isnull=True).iterator():
        record.call_id = uuid.uuid4()
        record.save(update_fields=["call_id"], using=schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]

    operations = [
        migrations.AddField("priceplan", "provider", models.CharField(blank=True, max_length=32)),
        migrations.AddField("priceplan", "model", models.CharField(blank=True, max_length=128)),
        migrations.AddField("priceplan", "cached_input_per_1k", models.DecimalField(blank=True, null=True, max_digits=10, decimal_places=6)),
        migrations.AddField("priceplan", "effective_from", models.DateTimeField(default=timezone.now)),
        migrations.AddField("usagerecord", "call_id", models.UUIDField(null=True, unique=True, editable=False)),
        migrations.RunPython(assign_call_ids, migrations.RunPython.noop),
        migrations.AlterField("usagerecord", "call_id", models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
        migrations.AlterField("usagerecord", "model", models.CharField(blank=True, max_length=128)),
        migrations.AddField("usagerecord", "agent", models.CharField(blank=True, max_length=64)),
        migrations.AddField("usagerecord", "trace_id", models.CharField(blank=True, max_length=64, db_index=True)),
        migrations.AddField("usagerecord", "run_id", models.CharField(blank=True, max_length=64, db_index=True)),
        migrations.AddField("usagerecord", "request_id", models.CharField(blank=True, max_length=256)),
        migrations.AddField("usagerecord", "tokens_cached", models.PositiveIntegerField(default=0)),
        migrations.AddField("usagerecord", "measurement", models.CharField(max_length=16, default="legacy"), preserve_default=False),
        migrations.AlterField("usagerecord", "measurement", models.CharField(max_length=16, default="provider")),
        migrations.AddField("usagerecord", "currency", models.CharField(max_length=8, default="CNY")),
        migrations.AddField("usagerecord", "price_snapshot", models.JSONField(default=dict)),
        migrations.AddField("dailybudget", "tokens_reserved", models.PositiveIntegerField(default=0)),
        migrations.AddField("dailybudget", "cost_reserved", models.DecimalField(max_digits=12, decimal_places=6, default=0)),
        migrations.CreateModel(
            name="UsageReservation",
            fields=[
                ("call_id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("status", models.CharField(max_length=16, default="reserved", choices=[("reserved", "已预占"), ("settled", "已结算"), ("released", "已释放")])),
                ("tokens", models.PositiveIntegerField()),
                ("cost", models.DecimalField(max_digits=12, decimal_places=6)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(null=True, blank=True)),
                ("budget", models.ForeignKey(to="billing.dailybudget", related_name="reservations", on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
    ]
