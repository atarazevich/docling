# Docling API Deployment Instructions for Dokploy

This guide provides step-by-step instructions to deploy the Docling API service to your Dokploy server.

## Overview

**Service**: Docling API
**Repository**: https://github.com/atarazevich/docling (forked, private)
**Tech Stack**: Python 3.12, FastAPI, Docling
**Purpose**: Document parsing and conversion service (PDF, DOCX, PPTX, HTML, images → Markdown/JSON)
**Resource Requirements**: ~2GB RAM, 2+ CPU cores recommended
**Port**: 8000 (internal)

## Pre-deployment Checklist

✅ Repository forked to atarazevich GitHub account (already done)
✅ Dockerfile created with multi-stage build
✅ FastAPI wrapper created (api.py)
✅ Health check endpoint included
✅ Models pre-downloaded in Docker image

## Step-by-Step Deployment Instructions

### Step 1: Access Dokploy UI

1. Connect to Tailscale VPN
2. Navigate to http://100.96.121.119:3000
3. Login with your credentials

### Step 2: Select or Create Project

1. Click on **"Personal"** project (already exists)
   - Or create new project if preferred

### Step 3: Create New Application

1. Inside the project, click **"Create Service"**
2. Select **"Application"** as service type
3. Fill in application details:
   - **Name**: `docling-api`
   - **Description**: `Document parsing API service powered by Docling`

### Step 4: Configure Git Repository

1. In the **Source** section:
   - **Provider**: GitHub
   - **Repository**: `atarazevich/docling`
   - **Branch**: `main` (or `master`)
   - **Build Path**: `/` (root directory)

### Step 5: Configure Build Settings

1. In the **Build** section:
   - **Build Type**: `Dockerfile` (⚠️ NOT Nixpacks - must be Dockerfile)
   - **Dockerfile Path**: `./Dockerfile`
   - **Docker Context**: `.`

2. **IMPORTANT - Add Build Arguments**:
   - This helps with caching and faster rebuilds
   - Click "Add Build Argument"
   - Name: `BUILDKIT_INLINE_CACHE`
   - Value: `1`

### Step 6: Configure Environment Variables

1. Click **"Environment"** tab
2. Add the following environment variables:

```env
# Core Settings (Required)
SERVICE_NAME=docling-api
LOG_LEVEL=info
API_PORT=8000

# Model Paths (Required)
DOCLING_ARTIFACTS_PATH=/home/docling/models
HF_HOME=/home/docling/.cache/huggingface
TORCH_HOME=/home/docling/.cache/torch

# Performance (Required)
OMP_NUM_THREADS=4
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1

# Optional Settings
MAX_FILE_SIZE_MB=100
REQUEST_TIMEOUT=300
METRICS_ENABLED=true
DEBUG=false
```

### Step 7: Configure Networking

1. In the **Networking** section:
   - **Port**: `8000`
   - **Exposed Port**: Leave empty (internal only initially)

### Step 8: Configure Domain (Optional)

1. In the **Domains** section:
   - Click **"Add Domain"**
   - **Host**: `docling.dev.cognition.design`
   - **Path**: `/`
   - **Container Port**: `8000`
   - **HTTPS**: Enable
   - **Certificate Type**: `letsencrypt`

**Alternative**: If not using custom domain, Dokploy will auto-generate a Traefik.me domain.

### Step 9: Configure Resources (Optional but Recommended)

1. In the **Advanced** tab:
   - **Memory Limit**: `2048` (2GB)
   - **CPU Limit**: `2` (2 cores)
   - **Restart Policy**: `unless-stopped`

### Step 10: Deploy the Application

1. Review all settings
2. Click **"Deploy"** button
3. Monitor deployment logs
4. **Note**: First deployment will take 5-10 minutes due to:
   - Building Docker image
   - Installing dependencies
   - Downloading AI models

### Step 11: Verify Deployment

1. Once deployment shows "Running", wait 1-2 minutes for service initialization
2. Check health endpoint:
   ```bash
   curl https://docling.dev.cognition.design/health
   ```

   Expected response:
   ```json
   {
     "status": "healthy",
     "service": "docling-api",
     "version": "2.61.1",
     "converter_ready": true
   }
   ```

3. Visit API documentation:
   - Swagger UI: https://docling.dev.cognition.design/docs
   - ReDoc: https://docling.dev.cognition.design/redoc

### Step 12: Test the API

1. Test with URL conversion:
   ```bash
   curl -X POST https://docling.dev.cognition.design/convert \
     -H "Content-Type: application/json" \
     -d '{
       "url": "https://arxiv.org/pdf/2408.09869",
       "output_format": "markdown"
     }'
   ```

2. Test with file upload:
   ```bash
   curl -X POST https://docling.dev.cognition.design/convert/upload \
     -F "file=@document.pdf" \
     -F "output_format=markdown"
   ```

## Post-Deployment Configuration

### Enable Auto-Deploy (Recommended)

1. In application settings, go to **"Git"** section
2. Enable **"Auto Deploy on Push"**
3. Copy the webhook URL
4. Add to GitHub repository settings → Webhooks

### Monitor Application

1. View logs: Deployments tab → View Logs
2. Check metrics: https://docling.dev.cognition.design/metrics
3. Monitor resource usage in Dokploy dashboard

## API Endpoints

- `GET /` - Service information
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `POST /convert` - Convert document from URL
- `POST /convert/upload` - Convert uploaded document
- `GET /docs` - Swagger UI documentation
- `GET /redoc` - ReDoc documentation

## Supported Input Formats

- PDF (with OCR support for scanned documents)
- DOCX (Microsoft Word)
- PPTX (PowerPoint)
- XLSX (Excel)
- HTML
- Images (PNG, JPEG, TIFF, etc.)
- Plain text files

## Output Formats

- `markdown` - Markdown formatted text
- `json` - Structured JSON document
- `doctags` - DocTags format
- `text` - Plain text

## Troubleshooting

### Issue: Build Fails

**Solution**:
- Check Dockerfile syntax
- Ensure repository is accessible
- Verify branch name is correct

### Issue: Service Crashes on Startup

**Solution**:
- Check environment variables are set correctly
- Increase memory limit to 3GB
- Check logs for specific error messages

### Issue: Slow First Request

**Solution**:
- This is normal - models are loaded on first use
- Consider adding a warm-up script
- Pre-load models in Dockerfile (already done)

### Issue: Out of Memory

**Solution**:
- Increase memory limit in Advanced settings
- Reduce `OMP_NUM_THREADS` to 2
- Limit concurrent requests

### Issue: SSL Certificate Issues

**Solution**:
- Wait 2-3 minutes for Let's Encrypt certificate generation
- Ensure domain DNS is pointing to server IP (49.12.188.93)
- Check Traefik logs in Dokploy

## Performance Optimization

1. **Model Caching**: Models are pre-downloaded in Docker image
2. **CPU Optimization**: Adjust `OMP_NUM_THREADS` based on available cores
3. **Memory Management**: Set appropriate limits to prevent OOM
4. **Health Checks**: Built-in health endpoint for monitoring

## Security Considerations

1. **File Size Limits**: 100MB default limit for uploads
2. **Non-root User**: Container runs as non-root user `docling`
3. **Input Validation**: All inputs are validated
4. **Rate Limiting**: Can be enabled via environment variables

## Maintenance

### Update Application

1. Push changes to GitHub repository
2. If auto-deploy enabled: Automatic
3. If manual: Click "Redeploy" in Dokploy

### View Logs

1. Go to application in Dokploy
2. Click "Deployments" tab
3. Click on specific deployment to view logs

### Rollback

1. Go to application settings
2. Click "Deployments" tab
3. Select previous successful deployment
4. Click "Rollback"

## Additional Notes

- The service includes Prometheus metrics at `/metrics` endpoint
- First deployment takes longer due to model downloads
- Service automatically restarts on failure
- All processing is done locally (no external API calls for conversion)
- Supports batch processing via multiple concurrent requests

## Support

For issues specific to:
- **Docling library**: Check https://github.com/docling-project/docling
- **Deployment**: Review Dokploy logs
- **API wrapper**: Check api.py implementation

---

*Created: 2025-11-07*
*Service Version: Docling 2.61.1*
*API Version: 1.0.0*