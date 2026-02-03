# Generated manually to add username field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api1', '0035_alter_liquidation_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='username',
            field=models.CharField(max_length=150, unique=True, null=True, blank=True),
        ),
    ]
