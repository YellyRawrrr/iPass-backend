# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api1', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AfterTravelReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pap', models.CharField(help_text='Program/Activity/Project', max_length=255)),
                ('actual_output', models.CharField(max_length=255)),
                ('cash_advance', models.DateField()),
                ('period_of_implementation', models.DateField()),
                ('date_of_submission', models.DateField()),
                ('background', models.TextField()),
                ('highlights_of_activity', models.TextField()),
                ('ways_forward', models.TextField()),
                ('photo_documentation', models.JSONField(default=list, help_text='List of photo file paths')),
                ('attachments', models.JSONField(default=list, help_text='List of attachment file paths')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('office_head', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_after_travel_reports', to='api1.customuser')),
                ('prepared_by', models.ManyToManyField(related_name='prepared_after_travel_reports', to='api1.customuser')),
                ('regional_director', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='director_approved_after_travel_reports', to='api1.customuser')),
            ],
        ),
        migrations.AddField(
            model_name='liquidation',
            name='after_travel_report',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='liquidation', to='api1.aftertravelreport'),
        ),
    ]

