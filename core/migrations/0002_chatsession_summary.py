from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatsession",
            name="summary",
            field=models.TextField(null=True, blank=True, help_text="Running condensed emotional/context summary for continuity."),
        ),
    ]