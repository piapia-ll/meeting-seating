# Generated manually for 会场排排座 V1 venue foundation.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('seats', '0020_pluginruntimekv'),
    ]

    operations = [
        migrations.AlterField(
            model_name='classroom',
            name='name',
            field=models.CharField(max_length=100, verbose_name='会场名称'),
        ),
        migrations.AddField(
            model_name='seat',
            name='meeting_zone',
            field=models.CharField(
                choices=[('audience', '普通席'), ('stage', '主席台')],
                default='audience',
                help_text='普通席或主席台。与原布局单元类型分开保存，便于逐步兼容原编辑器。',
                max_length=16,
                verbose_name='会务区域',
            ),
        ),
        migrations.AddField(
            model_name='seat',
            name='meeting_status',
            field=models.CharField(
                choices=[('normal', '参与自动排座'), ('skip', '本次跳过'), ('locked', '锁定座位')],
                default='normal',
                help_text='正常参与排座、跳过，或锁定。V1 阶段先保存到会场座位，后续会议模块会覆盖为会议级状态。',
                max_length=16,
                verbose_name='会务座位状态',
            ),
        ),
    ]
