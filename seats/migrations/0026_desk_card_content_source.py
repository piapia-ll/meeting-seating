from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('seats', '0025_desk_card_template')]
    operations = [
        migrations.AddField(
            model_name='deskcardtemplate',
            name='content_source',
            field=models.CharField(choices=[('person','人员姓名'),('department','部门桌牌名')], default='person', max_length=16, verbose_name='内容来源'),
        ),
    ]
