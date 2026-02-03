# Generated manually to populate username field

from django.db import migrations


def populate_usernames(apps, schema_editor):
    CustomUser = apps.get_model('api1', 'CustomUser')
    
    for user in CustomUser.objects.all():
        if not user.username or user.username == '':
            # Generate username from email (part before @)
            if user.email:
                username = user.email.split('@')[0]
                # Ensure username is unique
                counter = 1
                original_username = username
                while CustomUser.objects.filter(username=username).exists():
                    username = f"{original_username}{counter}"
                    counter += 1
                user.username = username
                user.save()
            else:
                # If no email, use a default pattern
                username = f"user_{user.id}"
                user.username = username
                user.save()


def reverse_populate_usernames(apps, schema_editor):
    # No need to reverse this operation
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api1', '0036_add_username_field'),
    ]

    operations = [
        migrations.RunPython(populate_usernames, reverse_populate_usernames),
    ]
