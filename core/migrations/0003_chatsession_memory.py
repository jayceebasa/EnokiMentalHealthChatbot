from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_chatsession_summary"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatsession",
            name="memory",
            field=models.JSONField(null=True, blank=True, help_text="Structured memory (stressor, motivation, coping, trajectory, bot_openings)"),
        ),
    ]