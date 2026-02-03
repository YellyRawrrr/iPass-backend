#!/usr/bin/env python
"""Script to create a Django superuser with all required fields."""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project1.settings')
django.setup()

from api1.models import CustomUser

def create_superuser():
    print("Creating a new superuser account...")
    print("=" * 50)
    
    # Get user input
    email = input("Email address: ").strip()
    if not email:
        print("Error: Email is required.")
        return
    
    # Check if user already exists
    if CustomUser.objects.filter(email=email).exists():
        print(f"Error: A user with email '{email}' already exists.")
        return
    
    first_name = input("First name: ").strip()
    last_name = input("Last name: ").strip()
    
    print("\nAvailable user levels:")
    print("1. employee")
    print("2. head")
    print("3. admin")
    print("4. director")
    print("5. bookkeeper")
    print("6. accountant")
    
    user_level = input("\nUser level (enter number or name): ").strip().lower()
    
    # Map numbers to user levels
    level_map = {
        '1': 'employee',
        '2': 'head',
        '3': 'admin',
        '4': 'director',
        '5': 'bookkeeper',
        '6': 'accountant'
    }
    
    if user_level in level_map:
        user_level = level_map[user_level]
    
    valid_levels = ['employee', 'head', 'admin', 'director', 'bookkeeper', 'accountant']
    if user_level not in valid_levels:
        print(f"Error: Invalid user level. Using 'admin' as default.")
        user_level = 'admin'
    
    password = input("Password: ").strip()
    if not password:
        print("Error: Password is required.")
        return
    
    confirm_password = input("Password (again): ").strip()
    if password != confirm_password:
        print("Error: Passwords do not match.")
        return
    
    # Create the superuser
    try:
        # Create user directly since we're using email as username
        user = CustomUser(
            email=email,
            first_name=first_name,
            last_name=last_name,
            user_level=user_level,
            is_staff=True,
            is_superuser=True,
            is_active=True
        )
        user.set_password(password)
        user.save()
        
        print("\n" + "=" * 50)
        print(f"Superuser created successfully!")
        print(f"Email: {user.email}")
        print(f"Name: {user.full_name}")
        print(f"User Level: {user.user_level}")
        print("=" * 50)
    except Exception as e:
        print(f"\nError creating superuser: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    create_superuser()

