# OAuth Setup Guide

This guide will help you set up Google OAuth authentication for Enoki.

## Prerequisites

- A Google account
- Your application running locally (typically at `http://localhost:8000`)

## Google OAuth Setup

1. **Go to Google Cloud Console**
   - Visit [https://console.cloud.google.com/](https://console.cloud.google.com/)
   - Create a new project or select an existing one

2. **Enable Google+ API**
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google+ API"
   - Click "Enable"

3. **Create OAuth Credentials**
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Choose "Web application"
   - Set the following:
     - **Name**: Enoki Mental Health Chatbot (or your preferred name)
     - **Authorized JavaScript origins**: 
       - `http://localhost:8000`
       - `http://127.0.0.1:8000`
     - **Authorized redirect URIs**:
       - `http://localhost:8000/oauth/complete/google-oauth2/`
       - `http://127.0.0.1:8000/oauth/complete/google-oauth2/`

4. **Copy Credentials**
   - Copy the "Client ID" and "Client Secret"
   - Add them to your `.env` file:
     ```
     GOOGLE_OAUTH2_KEY=your-client-id.apps.googleusercontent.com
     GOOGLE_OAUTH2_SECRET=your-client-secret
     ```

## Installation

1. **Install required packages** (already done):
   ```bash
   pip install -r requirements.txt
   ```

2. **Run migrations** (already done):
   ```bash
   python manage.py migrate
   ```

3. **Run the development server**:
   ```bash
   python manage.py runserver
   ```

4. **Test OAuth login**:
   - Navigate to `http://localhost:8000/login/`
   - Click "Continue with Google"
   - Authorize the application
   - You should be redirected to the chat page

## Production Setup

For production deployment, update your OAuth redirect URIs to use your production domain:

**Google OAuth**:
- Authorized JavaScript origins: `https://yourdomain.com`
- Authorized redirect URIs: `https://yourdomain.com/oauth/complete/google-oauth2/`

## Troubleshooting

### "redirect_uri_mismatch" error
- Ensure your redirect URIs exactly match in both the OAuth provider settings and your application
- Check for trailing slashes
- Make sure you're using the correct protocol (http vs https)

### "Invalid client" error
- Verify your client ID and secret are correctly copied to `.env`
- Ensure there are no extra spaces or newlines
- Restart your Django server after updating `.env`

### User not created after OAuth
- Check Django logs for any errors
- Ensure migrations have been run: `python manage.py migrate`
- Verify the OAuth pipeline in `settings.py` is configured correctly

## Features

- **Google OAuth**: Users can sign in with their Google account
- **Traditional Login**: Users can create an account with username/password
- **Anonymous Mode**: Users can chat without creating an account (data not persisted)

## Security Notes

- Never commit your `.env` file to version control
- Use strong, unique secrets for production
- Rotate your OAuth secrets regularly
- Use HTTPS in production
- Keep `social-auth-app-django` updated for security patches
