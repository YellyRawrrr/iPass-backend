# Generated manually to remove Province, City, Barangay, and Region models

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api1', '0094_purpose_specificrole_alter_travelorder_purpose_and_more'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Barangay',
        ),
        migrations.DeleteModel(
            name='City',
        ),
        migrations.DeleteModel(
            name='Province',
        ),
        migrations.DeleteModel(
            name='Region',
        ),
    ]

