from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('seats', '0021_meeting_venue_foundation')]
    operations = [
        migrations.AddField(
            model_name='seat',
            name='venue_role',
            field=models.CharField(
                choices=[('audience', '普通席'), ('stage', '主席台席')],
                default='audience',
                help_text='会场模板中的普通席/主席台席标记。',
                max_length=16,
                verbose_name='会场座位用途',
            ),
        ),
    ]
