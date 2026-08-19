# ONLYOFFICE Document Server Setup Guide

This guide covers the complete setup of ONLYOFFICE Document Server integration for the CRM system.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ for generating JWT secret

## Part 1: Generate Secure JWT Secret

Generate a secure 32-byte random secret for JWT authentication:

```bash
cd Backend-CRM
python generate_jwt_secret.py
```

This will output a 64-character hex string. Copy this value.

## Part 2: Configure Environment Variables

Add the following to your `Backend-CRM/.env` file:

```env
# ONLYOFFICE Document Server Configuration
ONLYOFFICE_JWT_SECRET=<generated_secret_from_step_1>
ONLYOFFICE_PUBLIC_URL=http://localhost:8080
ONLYOFFICE_JWT_ENABLED=true
```

**Important:** Use the same `ONLYOFFICE_JWT_SECRET` value in both:
- Backend `.env` file
- Docker Compose environment (automatically loaded from `.env`)

## Part 3: Start Services

Start all services including ONLYOFFICE:

```bash
docker-compose up -d
```

Verify ONLYOFFICE is running:

```bash
curl OnlyOfficeEditor.tsx:84  GET http://localhost:8080/web-apps/apps/api/documents/api.js net::ERR_CONNECTION_REFUSED
```

Expected response: `true`

## Part 4: Verify LibreOffice Installation

LibreOffice is required for DOCX to PDF conversion. Verify it's installed in the backend container:

```bash
docker-compose exec backend soffice --version
```

Expected output: LibreOffice version information

## Part 5: Database Migration

Run the migration to add `document_file_path` column:

```bash
docker-compose exec backend python add_document_file_path_to_agreement_documents.py
```

## Part 6: Testing Checklist

### 6.1 Start Services
- [ ] All Docker containers are running
- [ ] ONLYOFFICE accessible at http://localhost:8080
- [ ] Backend API accessible at http://localhost:8000

### 6.2 Template Upload
- [ ] Upload a DOCX template
- [ ] Template is saved with `template_file_path` in database
- [ ] Template file exists in filesystem

### 6.3 Agreement Creation
- [ ] Create agreement from template
- [ ] DOCX file is created with placeholders replaced
- [ ] `document_file_path` is stored in database

### 6.4 Editor Loading
- [ ] Open agreement in frontend
- [ ] ONLYOFFICE editor loads correctly
- [ ] Document is displayed with proper formatting

### 6.5 Document Editing
- [ ] Edit document in ONLYOFFICE editor
- [ ] Save document
- [ ] New version is created automatically
- [ ] Version history shows new version

### 6.6 Locking Rules
- [ ] When status = SENT_FOR_SIGNATURE: Editor opens in read-only mode
- [ ] When status = EXECUTED: Editor is disabled (403 error)

### 6.7 PDF Conversion
- [ ] Convert DOCX to PDF using LibreOffice
- [ ] PDF formatting is preserved
- [ ] PDF can be sent to Zoho Sign

### 6.8 Zoho Integration
- [ ] Send agreement for signature
- [ ] PDF is generated from DOCX
- [ ] Signed PDF is stored correctly

## Troubleshooting

### ONLYOFFICE Not Loading

1. Check ONLYOFFICE container logs:
   ```bash
   docker-compose logs onlyoffice
   ```

2. Verify JWT secret is set:
   ```bash
   docker-compose exec onlyoffice env | grep JWT
   ```

3. Check backend can reach ONLYOFFICE:
   ```bash
   docker-compose exec backend curl http://onlyoffice:80/healthcheck
   ```

### LibreOffice Not Found

1. Rebuild backend container:
   ```bash
   docker-compose build backend
   docker-compose up -d backend
   ```

2. Verify installation:
   ```bash
   docker-compose exec backend which soffice
   docker-compose exec backend soffice --version
   ```

### JWT Token Errors

1. Verify secret is the same in:
   - Backend `.env` file
   - Docker Compose environment
   - ONLYOFFICE container environment

2. Check backend logs for JWT errors:
   ```bash
   docker-compose logs backend | grep -i jwt
   ```

### Document Not Saving

1. Check callback endpoint logs:
   ```bash
   docker-compose logs backend | grep -i callback
   ```

2. Verify callback URL is accessible from ONLYOFFICE:
   - Callback URL must be publicly accessible
   - For local development, use ngrok or similar tunnel

## Architecture

```
┌─────────────┐
│   Frontend  │
│  (React)    │
└──────┬──────┘
       │
       │ HTTP API
       │
┌──────▼──────────────────┐
│   Backend API           │
│   (FastAPI)             │
│                         │
│  ┌──────────────────┐  │
│  │ ONLYOFFICE Config│  │
│  │ Endpoint         │  │
│  └──────────────────┘  │
│                         │
│  ┌──────────────────┐  │
│  │ Callback Endpoint│  │
│  └──────────────────┘  │
└──────┬──────────────────┘
       │
       │ JWT Signed Requests
       │
┌──────▼──────────────┐
│  ONLYOFFICE Server  │
│  (Port 8080)        │
└─────────────────────┘
```

## Security Notes

1. **JWT Secret**: Never commit the JWT secret to version control
2. **Public URL**: In production, use HTTPS for ONLYOFFICE_PUBLIC_URL
3. **Callback URL**: Must be accessible from ONLYOFFICE server
4. **Document Access**: Documents are served via authenticated endpoints

## Production Deployment

For production:

1. Use strong JWT secret (64+ characters)
2. Enable HTTPS for ONLYOFFICE_PUBLIC_URL
3. Configure proper CORS origins
4. Use reverse proxy (nginx) for ONLYOFFICE
5. Set up monitoring for ONLYOFFICE service
6. Configure backup for document storage

## Support

For issues or questions:
- Check ONLYOFFICE documentation: https://api.onlyoffice.com/
- Review backend logs: `docker-compose logs backend`
- Review ONLYOFFICE logs: `docker-compose logs onlyoffice`
