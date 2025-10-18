# Railway Deployment Guide for Enoki Mental Health Chatbot

## Prerequisites
- A GitHub account with this repository
- A Railway account (sign up at https://railway.app)
- Google OAuth2 credentials (for social authentication)
- Gemini API key (for AI chat functionality)

## Step 1: Prepare Your Repository

1. **Commit all changes to GitHub:**
   ```bash
   git add .
   git commit -m "Add Railway deployment configuration"
   git push origin main
   ```

## Step 2: Create a Railway Project

1. Go to https://railway.app and sign in
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your `EnokiMentalHealthChatbot` repository
5. Railway will automatically detect the Dockerfile

## Step 3: Add PostgreSQL Database

1. In your Railway project, click **"New"**
2. Select **"Database"** → **"Add PostgreSQL"**
3. Railway will automatically create a PostgreSQL database
4. The database will be linked to your service automatically

## Step 4: Configure Environment Variables

In your Railway project, go to your web service → **"Variables"** tab and add:

### Required Variables:

```bash
# Django Settings
SECRET_KEY=your-super-secret-key-here-change-this-in-production
DEBUG=0
ALLOWED_HOSTS=*.railway.app,yourdomain.com

# Database (Railway provides these automatically when you add PostgreSQL)
POSTGRES_DB=${{Postgres.PGDATABASE}}
POSTGRES_USER=${{Postgres.PGUSER}}
POSTGRES_PASSWORD=${{Postgres.PGPASSWORD}}
POSTGRES_HOST=${{Postgres.PGHOST}}
POSTGRES_PORT=${{Postgres.PGPORT}}

# Gemini AI
GEMINI_API_KEY=your-gemini-api-key-here

# Google OAuth2 (Optional but recommended)
GOOGLE_OAUTH2_KEY=your-google-oauth2-client-id
GOOGLE_OAUTH2_SECRET=your-google-oauth2-client-secret

# Django Superuser (Optional - for admin access)
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=change-this-secure-password
```

### How to Get API Keys:

#### Gemini API Key:
1. Go to https://makersuite.google.com/app/apikey
2. Create a new API key
3. Copy the key and add it to Railway

#### Google OAuth2 Credentials:
1. Go to https://console.cloud.google.com
2. Create a new project or select existing one
3. Enable "Google+ API"
4. Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client ID"
5. Set application type to "Web application"
6. Add authorized redirect URIs:
   - `https://your-app-name.railway.app/complete/google-oauth2/`
   - `http://localhost:8000/complete/google-oauth2/` (for local testing)
7. Copy the Client ID and Client Secret

#### Generate SECRET_KEY:
Run this command locally:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Step 5: Deploy

1. Railway will automatically deploy your application
2. Wait for the build to complete (check the "Deployments" tab)
3. Once deployed, Railway will provide a public URL (e.g., `https://your-app.railway.app`)

## Step 6: Post-Deployment Setup

1. **Update ALLOWED_HOSTS:**
   - Go to Variables and update `ALLOWED_HOSTS` with your Railway domain
   - Example: `your-app-name.railway.app`

2. **Update Google OAuth2 Redirect URIs:**
   - Add your Railway URL to Google Cloud Console
   - `https://your-app-name.railway.app/complete/google-oauth2/`

3. **Access Admin Panel:**
   - Go to `https://your-app-name.railway.app/admin`
   - Login with the superuser credentials you set

## Step 7: Custom Domain (Optional)

1. In Railway, go to your service → "Settings" → "Domains"
2. Click "Add Custom Domain"
3. Follow instructions to configure your DNS records
4. Update `ALLOWED_HOSTS` to include your custom domain

## Troubleshooting

### Build Fails:
- Check the build logs in Railway's "Deployments" tab
- Ensure all dependencies in `requirements.txt` are correct
- Verify Dockerfile syntax

### Application Won't Start:
- Check runtime logs in Railway
- Verify all required environment variables are set
- Make sure PostgreSQL database is running and connected

### Database Connection Issues:
- Ensure PostgreSQL service is running
- Verify database environment variables are correctly referenced
- Check that the database and web service are in the same project

### Static Files Not Loading:
- Railway automatically runs `collectstatic` during build
- Verify `STATIC_ROOT` and `STATIC_URL` in settings.py
- Check that WhiteNoise is installed and configured

### 500 Internal Server Error:
- Set `DEBUG=1` temporarily to see detailed errors
- Check Railway logs for Python tracebacks
- Verify all environment variables are set correctly

## Monitoring

1. **View Logs:**
   - Go to your service in Railway
   - Click on "Deployments" → Select latest deployment → "View Logs"

2. **Metrics:**
   - Railway provides CPU, Memory, and Network metrics
   - Access via the "Metrics" tab in your service

## Scaling

1. **Vertical Scaling (More Resources):**
   - Railway Pro plan allows you to allocate more CPU/RAM
   - Go to Settings → Resources

2. **Horizontal Scaling:**
   - Not directly supported in Railway's free tier
   - Consider Railway Pro for multiple replicas

## Cost Optimization

- Railway offers $5 free credits per month
- Monitor your usage in the "Usage" tab
- Optimize by:
  - Reducing build frequency
  - Using proper caching
  - Implementing database connection pooling

## Security Best Practices

1. **Never commit sensitive data:**
   - Use Railway environment variables for secrets
   - Keep `.env` in `.gitignore`

2. **Set DEBUG=0 in production**

3. **Use strong SECRET_KEY**

4. **Enable HTTPS (Railway provides this automatically)**

5. **Keep dependencies updated:**
   ```bash
   pip list --outdated
   pip install --upgrade <package-name>
   ```

## Backup Strategy

1. **Database Backups:**
   - Railway Pro provides automatic backups
   - Or use `pg_dump` to create manual backups
   ```bash
   railway run pg_dump > backup.sql
   ```

2. **Code Backups:**
   - Always push to GitHub
   - Create releases/tags for stable versions

## Additional Resources

- Railway Documentation: https://docs.railway.app
- Django Deployment Checklist: https://docs.djangoproject.com/en/stable/howto/deployment/checklist/
- Railway Discord: https://discord.gg/railway

## Support

If you encounter issues:
1. Check Railway status: https://status.railway.app
2. Search Railway documentation
3. Ask in Railway Discord community
4. Check Django logs for application-specific errors

---

**Note:** Remember to update your Google OAuth2 redirect URIs after deployment!
