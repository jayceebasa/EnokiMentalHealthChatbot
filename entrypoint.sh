#!/bin/bash

# Exit on error
set -e

echo "Starting Django application setup..."

# Check if we're using PostgreSQL
if [ "$POSTGRES_DB" ]; then
    echo "Waiting for database..."
    python << END
import os
import time
import psycopg2
from psycopg2 import OperationalError

def wait_for_db():
    db_conn = None
    retries = 30
    while not db_conn and retries > 0:
        try:
            db_conn = psycopg2.connect(
                host=os.getenv('POSTGRES_HOST', 'db'),
                port=os.getenv('POSTGRES_PORT', '5432'),
                database=os.getenv('POSTGRES_DB', 'enoki'),
                user=os.getenv('POSTGRES_USER', 'postgres'),
                password=os.getenv('POSTGRES_PASSWORD', 'postgres')
            )
        except OperationalError:
            print('Database unavailable, waiting 2 seconds...')
            time.sleep(2)
            retries -= 1
    if db_conn:
        print('Database available!')
    else:
        print('Could not connect to database after 30 retries')

wait_for_db()
END
else
    echo "Using SQLite database..."
fi

# Run database migrations
echo "Running database migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Create superuser if it doesn't exist (for development)
if [ "$DJANGO_SUPERUSER_USERNAME" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ] && [ "$DJANGO_SUPERUSER_EMAIL" ]; then
    echo "Creating superuser..."
    python manage.py shell << END
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')
    print('Superuser created.')
else:
    print('Superuser already exists.')
END
fi

echo "Setup complete. Starting server..."

# Execute the main container command
exec "$@"