from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('seats', '0019_classroomgroup_cloud_sync_fields')]

    operations = [
        migrations.CreateModel(
            name='PluginRuntimeKV',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plugin_id', models.CharField(db_index=True, max_length=64, verbose_name='插件 ID')),
                ('namespace', models.CharField(max_length=32, verbose_name='命名空间')),
                ('key', models.CharField(max_length=160, verbose_name='键')),
                ('value', models.TextField(blank=True, default='', verbose_name='JSON 值')),
                ('is_secret', models.BooleanField(default=False, verbose_name='加密值')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': '插件运行时数据',
                'verbose_name_plural': '插件运行时数据',
                'indexes': [models.Index(fields=['plugin_id', 'namespace'], name='plugin_runtime_ns_idx')],
                'constraints': [models.UniqueConstraint(fields=('plugin_id', 'namespace', 'key'), name='plugin_runtime_kv_unique')],
            },
        ),
    ]
