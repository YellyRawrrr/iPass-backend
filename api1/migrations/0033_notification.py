# Generated manually for Notification model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api1', '0032_remove_customuser_verification_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notification_type', models.CharField(choices=[('travel_approved', 'Travel Request Approved'), ('travel_rejected', 'Travel Request Rejected'), ('travel_rejected_by_next_approver', 'Travel Request Rejected by Next Approver'), ('travel_final_approved', 'Travel Request Finally Approved')], max_length=50)),
                ('title', models.CharField(max_length=200)),
                ('message', models.TextField()),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('travel_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='api1.travelorder')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='api1.customuser')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
