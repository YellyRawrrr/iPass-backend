# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api1', '0099_certificateoftravel_recommending_approval'),
    ]

    operations = [
        migrations.AddField(
            model_name='travelorder',
            name='director_travel_classification',
            field=models.CharField(
                blank=True,
                choices=[('official_time', 'On Official Time'), ('official_business', 'On Official Business')],
                help_text='Set by Regional Director on final approval',
                max_length=32,
                null=True,
            ),
        ),
    ]
