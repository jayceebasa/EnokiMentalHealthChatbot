"""
Script to create the missing social_auth tables in the existing SQLite database.
This is needed when migrations were run on PostgreSQL but now using SQLite.
"""
import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'enoki.settings')
django.setup()

from django.core.management import call_command
from django.db import connection

# Check if social_auth_usersocialauth table exists
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='social_auth_usersocialauth';
    """)
    result = cursor.fetchone()
    
    if result:
        print("✅ social_auth_usersocialauth table already exists!")
    else:
        print("❌ social_auth_usersocialauth table does NOT exist")
        print("🔧 Creating social_auth tables...")
        
        # Run the social_django migrations
        call_command('migrate', 'social_django', verbosity=2)
        
        print("✅ Social auth tables created successfully!")

print("\n📊 Checking all tables in database:")
with connection.cursor() as cursor:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = cursor.fetchall()
    for table in tables:
        print(f"  - {table[0]}")

print("\n✅ Database check complete!")
