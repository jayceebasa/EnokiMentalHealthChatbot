# Railway Deployment - Quick Reference

## Files Created for Railway Deployment

1. **railway.json** - Railway build configuration
2. **railway.toml** - Railway deployment configuration
3. **.railwayignore** - Files to exclude from Railway deployment
4. **.env.example** - Template for environment variables
5. **RAILWAY_DEPLOYMENT.md** - Comprehensive deployment guide
6. **railway-setup.sh** - Helper script to generate configuration

## Updated Files

1. **Dockerfile** - Updated to work with Railway's PORT variable
2. **entrypoint.sh** - Improved database wait logic and Railway compatibility

## Quick Deployment Steps

### 1. Commit Changes to GitHub
```bash
git add .
git commit -m "Add Railway deployment configuration"
git push origin main
```

### 2. Deploy on Railway
1. Visit https://railway.app
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your repository
4. Add PostgreSQL database: Click "New" → "Database" → "PostgreSQL"

### 3. Set Environment Variables

Go to your service → "Variables" tab and add:

**Essential Variables:**
```bash
SECRET_KEY=<generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DEBUG=0
ALLOWED_HOSTS=*.railway.app

# Database - Use Railway References
POSTGRES_DB=${{Postgres.PGDATABASE}}
POSTGRES_USER=${{Postgres.PGUSER}}
POSTGRES_PASSWORD=${{Postgres.PGPASSWORD}}
POSTGRES_HOST=${{Postgres.PGHOST}}
POSTGRES_PORT=${{Postgres.PGPORT}}

# API Keys
GEMINI_API_KEY=<your-gemini-api-key>
```

**Optional Variables:**
```bash
GOOGLE_OAUTH2_KEY=<your-google-client-id>
GOOGLE_OAUTH2_SECRET=<your-google-client-secret>
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=<secure-password>
```

### 4. Get API Keys

**Gemini API:**
- Visit: https://makersuite.google.com/app/apikey

**Google OAuth2:**
- Visit: https://console.cloud.google.com
- Create OAuth 2.0 credentials
- Add redirect URI: `https://your-app.railway.app/complete/google-oauth2/`

### 5. Deploy and Monitor
- Railway automatically deploys after setting variables
- Monitor logs in "Deployments" tab
- Access your app at the provided Railway URL

## Important Notes

✅ **DO:**
- Use Railway's environment variables (never hardcode secrets)
- Update ALLOWED_HOSTS with your Railway domain
- Set DEBUG=0 in production
- Add your Railway URL to Google OAuth2 redirect URIs

❌ **DON'T:**
- Commit .env file to git
- Use DEBUG=1 in production
- Share your SECRET_KEY or API keys
- Forget to run migrations (entrypoint.sh handles this)

## Troubleshooting

**Build fails?**
- Check build logs in Railway
- Verify requirements.txt is correct

**App won't start?**
- Check runtime logs
- Verify all environment variables are set
- Ensure PostgreSQL is running

**Database connection issues?**
- Verify database variables use `${{Postgres.*}}` syntax
- Check that database is in the same project

**Static files missing?**
- Collectstatic runs automatically in Dockerfile
- WhiteNoise serves static files

## Support

- Full guide: See `RAILWAY_DEPLOYMENT.md`
- Railway docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway

---

## Estimated Deployment Time
- Initial setup: 5-10 minutes
- Build time: 3-5 minutes
- Total: ~15 minutes
