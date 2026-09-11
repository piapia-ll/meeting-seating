from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cloud', '0006_cloudclassroomgroup_data_snapshot_and_modified_at')]

    operations = [
        migrations.CreateModel(
            name='PluginRuntimeKV',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plugin_id', models.CharField(db_index=True, max_length=64)),
                ('namespace', models.CharField(max_length=32)),
                ('key', models.CharField(max_length=160)),
                ('value', models.TextField(blank=True, default='')),
                ('is_secret', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'indexes': [models.Index(fields=['plugin_id', 'namespace'], name='cloud_plugin_runtime_ns_idx')],
                'constraints': [models.UniqueConstraint(fields=('plugin_id', 'namespace', 'key'), name='cloud_plugin_runtime_kv_unique')],
            },
        ),
    ]
