from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('seats', '0023_meeting_business_models')]
    operations = [
        migrations.AlterModelOptions(name='classroom', options={'verbose_name':'会场','verbose_name_plural':'会场'}),
        migrations.AlterModelOptions(name='meeting', options={'ordering':['-meeting_date','-id'],'verbose_name':'会议','verbose_name_plural':'会议'}),
        migrations.AlterModelOptions(name='participant', options={'ordering':['id'],'verbose_name':'参会人员','verbose_name_plural':'参会人员'}),
        migrations.AlterModelOptions(name='personnellevel', options={'ordering':['order','id'],'verbose_name':'行政级别','verbose_name_plural':'行政级别'}),
        migrations.AlterModelOptions(name='policedepartment', options={'ordering':['order','id'],'verbose_name':'警种部门','verbose_name_plural':'警种部门'}),
        migrations.AlterField(model_name='meeting', name='id', field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        migrations.AlterField(model_name='meetingparticipant', name='id', field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        migrations.AlterField(model_name='meetingseatassignment', name='id', field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        migrations.AlterField(model_name='participant', name='id', field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        migrations.AlterField(model_name='personnellevel', name='id', field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        migrations.AlterField(model_name='policedepartment', name='id', field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        migrations.AlterField(model_name='seat', name='cell_type', field=models.CharField(choices=[('seat','普通席'),('aisle','走廊'),('podium','主席台'),('empty','空位')], default='seat', max_length=10, verbose_name='单元类型')),
    ]
