from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('seats', '0024_sync_meeting_model_state')]
    operations = [
        migrations.CreateModel(
            name='DeskCardTemplate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('large','大桌牌'),('small','小桌牌')], max_length=16, unique=True, verbose_name='桌牌类型')),
                ('width_mm', models.PositiveIntegerField(default=190, verbose_name='宽度(mm)')),
                ('height_mm', models.PositiveIntegerField(default=90, verbose_name='高度(mm)')),
                ('font_size_pt', models.PositiveIntegerField(default=52, verbose_name='字号(pt)')),
                ('active', models.BooleanField(default=True, verbose_name='启用')),
            ],
            options={'verbose_name':'桌牌模板','verbose_name_plural':'桌牌模板'},
        ),
    ]
