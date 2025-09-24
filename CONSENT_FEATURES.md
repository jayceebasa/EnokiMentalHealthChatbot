# Consent Management Features

## Overview

The Enoki Mental Health Chatbot now includes comprehensive consent management to ensure privacy compliance and user control over their data.

## Features Implemented

### 1. **Data Consent Management**
- Users can explicitly consent to or revoke data storage permissions
- Consent status is tracked with timestamps and version control
- All consent changes are logged for audit purposes

### 2. **Session-Only Memory (No Consent)**
When users haven't given consent:
- Conversations are stored only in the browser session (temporary)
- No data is persisted to the database
- Conversation context is maintained during the session but lost when browser closes
- Users are clearly informed about the temporary nature of the conversation

### 3. **Full Database Storage (With Consent)**
When users have given consent:
- Full conversation history is stored and encrypted in the database
- Conversation continuity across sessions
- Memory and summary features work normally
- Ephemeral session data is automatically migrated to database when consent is given

### 4. **Audit Logging**
- All consent changes are logged with user ID and timestamps
- All database operations are logged for compliance
- Ephemeral conversations are logged (without content) for system monitoring

## API Endpoints

### Check Consent Status
```bash
GET /api/consent/status/
```
Returns current consent status, timestamp, and ephemeral data info.

### Update Consent
```bash
POST /api/consent/
Content-Type: application/json

{
  "consent": true  // or false
}
```

### Chat with Consent Parameter
```bash
POST /api/chat/
Content-Type: application/json

{
  "message": "Hello",
  "consent": true  // optional: provide consent in chat request
}
```

## Database Schema Changes

### UserPreference Model (New Fields)
- `data_consent`: Boolean field indicating consent status
- `consent_timestamp`: When consent was given/updated
- `consent_version`: Version of privacy policy consented to

## Docker Integration

The system automatically handles database migrations when containers start:

1. **entrypoint.sh**: Waits for database, runs migrations, collects static files
2. **Dockerfile**: Updated to use entrypoint script and install required dependencies
3. **docker-compose.yml**: Updated with database connection environment variables

## Testing

Run the consent functionality test:
```bash
./test_consent.sh
```

This script tests:
1. Initial consent status (should be false)
2. Chat without consent (ephemeral)
3. Multiple messages without consent (no persistence)
4. Giving consent
5. Chat with consent (full database storage)
6. Context retention with consent
7. Consent status verification
8. Consent revocation
9. Post-revocation behavior (ephemeral again)

## User Experience

### Without Consent
- "Conversation stored in browser only - enable data storage for full continuity across sessions."
- Conversation works normally but doesn't persist beyond browser session
- Users can change their mind and enable data storage at any time

### With Consent
- Full conversation history and continuity
- All mental health companion features work normally
- Data is encrypted at rest

### Consent Migration
- When consent is given, any existing session conversation is automatically migrated to the database
- When consent is revoked, ephemeral session data is cleared

## Privacy Compliance

This implementation ensures:
- ✅ No personal data stored without explicit consent
- ✅ Clear user control over data storage
- ✅ Transparent communication about data handling
- ✅ Audit trail for all consent decisions
- ✅ Graceful degradation (system works without consent)
- ✅ Easy consent management (can be changed at any time)

## Security

- All stored messages are encrypted using Fernet encryption
- Session data is temporary and automatically expires
- Audit logs capture all critical operations
- Database connections use environment variables for security