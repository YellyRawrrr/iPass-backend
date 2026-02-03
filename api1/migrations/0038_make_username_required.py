# Generated manually to make username field required

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api1', '0037_populate_username_field'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='username',
            field=models.CharField(max_length=150, unique=True),
        ),
    ]
