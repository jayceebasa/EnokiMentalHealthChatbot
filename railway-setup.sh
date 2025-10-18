#!/bin/bash

# Railway Quick Deploy Script
# This script helps you set up environment variables for Railway deployment

echo "==================================="
echo "Railway Deployment Setup Assistant"
echo "==================================="
echo ""

# Function to generate SECRET_KEY
generate_secret_key() {
    python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
}

echo "1. Generating Django SECRET_KEY..."
SECRET_KEY=$(generate_secret_key)
echo "SECRET_KEY=$SECRET_KEY"
echo ""

echo "2. Required Environment Variables for Railway:"
echo "-------------------------------------------"
echo ""
echo "# Copy these to Railway Variables tab:"
echo ""
echo "SECRET_KEY=$SECRET_KEY"
echo "DEBUG=0"
echo "ALLOWED_HOSTS=*.railway.app"
echo ""
echo "# Database (auto-filled by Railway PostgreSQL):"
echo 'POSTGRES_DB=${{Postgres.PGDATABASE}}'
echo 'POSTGRES_USER=${{Postgres.PGUSER}}'
echo 'POSTGRES_PASSWORD=${{Postgres.PGPASSWORD}}'
echo 'POSTGRES_HOST=${{Postgres.PGHOST}}'
echo 'POSTGRES_PORT=${{Postgres.PGPORT}}'
echo ""
echo "# API Keys (you need to provide these):"
echo "GEMINI_API_KEY=your-gemini-api-key"
echo ""
echo "# Optional - Google OAuth2:"
echo "GOOGLE_OAUTH2_KEY=your-google-client-id"
echo "GOOGLE_OAUTH2_SECRET=your-google-client-secret"
echo ""
echo "# Optional - Django Admin:"
echo "DJANGO_SUPERUSER_USERNAME=admin"
echo "DJANGO_SUPERUSER_EMAIL=admin@example.com"
echo "DJANGO_SUPERUSER_PASSWORD=your-secure-password"
echo ""
echo "==================================="
echo "Next Steps:"
echo "==================================="
echo "1. Go to https://railway.app and create a new project"
echo "2. Connect your GitHub repository"
echo "3. Add a PostgreSQL database to your project"
echo "4. Copy the environment variables above to Railway's Variables tab"
echo "5. Replace placeholder values with your actual API keys"
echo "6. Deploy and wait for the build to complete"
echo ""
echo "For detailed instructions, see RAILWAY_DEPLOYMENT.md"
echo "==================================="
