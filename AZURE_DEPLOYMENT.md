# Azure Web App Deployment Guide

This guide covers deploying the VayuDrishti FastAPI backend to Azure Web App.

## Prerequisites

- Azure subscription (free tier available)
- Azure CLI installed (`az`) or use Azure Portal
- GitHub repo configured with your code
- Visual Studio Code with Azure extension (optional but helpful)

## Deployment Option 1: Using Azure Portal (Easiest)

### Step 1: Create a Web App

1. Go to [Azure Portal](https://portal.azure.com)
2. Click "Create a resource" → "Web App"
3. Configure:
   - **Name:** `vayu-drishti-backend` (must be globally unique)
   - **Publish:** Docker Container (or Code for Linux)
   - **Runtime stack:** Python 3.11
   - **Operating System:** Linux (recommended for Python)
   - **App Service Plan:** Create new or use existing (B1 minimum recommended)

### Step 2: Configure Deployment

1. Go to **Deployment Center**
2. Select **GitHub** as source
3. Authorize and select:
   - **Organization:** Your GitHub org
   - **Repository:** VayuDrishti
   - **Branch:** main
4. Configure build settings:
   - **Build provider:** GitHub Actions
   - **Runtime stack:** Python 3.11
   - **Startup command:** Use the field to add custom command

### Step 3: Set Environment Variables

1. Go to **Configuration** → **Application settings**
2. Add these app settings:
   - `DATABASE_URL` - Your PostgreSQL connection string
   - `REDIS_URL` - Your Redis connection string
   - `ENVIRONMENT` - Set to `azure`
   - `PYTHONUNBUFFERED` - Set to `1`
   - `SCM_DO_BUILD_DURING_DEPLOYMENT` - Set to `true`
   - `ENABLE_ORYX_BUILD` - Set to `true`

3. For Linux App Service, also add:
   - `WEBSITE_RUN_FROM_PACKAGE` - Set to `0` (we'll run from repo)

### Step 4: Configure Startup Command

In **Configuration** → **General settings** → **Startup Command**, add:
```bash
bash startup.sh
```

For Docker-based: Use the `Dockerfile` instead

### Step 5: Deploy

The GitHub Actions workflow will trigger automatically on push to main branch.

Monitor deployment in **Deployment Center** → **Logs**

## Deployment Option 2: Using Azure CLI

```bash
# Install Azure CLI if you haven't
# https://docs.microsoft.com/cli/azure/install-azure-cli

# Login to Azure
az login

# Create a resource group
az group create --name vayu-rg --location eastus

# Create an App Service plan (B1 for testing, B2 for production)
az appservice plan create \
  --name vayu-plan \
  --resource-group vayu-rg \
  --sku B1 \
  --is-linux

# Create the web app
az webapp create \
  --resource-group vayu-rg \
  --plan vayu-plan \
  --name vayu-drishti-backend \
  --runtime "PYTHON:3.11"

# Set environment variables
az webapp config appsettings set \
  --resource-group vayu-rg \
  --name vayu-drishti-backend \
  --settings \
    DATABASE_URL="postgresql://..." \
    REDIS_URL="redis://..." \
    ENVIRONMENT="azure" \
    PYTHONUNBUFFERED="1"

# Set startup command
az webapp config set \
  --resource-group vayu-rg \
  --name vayu-drishti-backend \
  --startup-file "bash startup.sh"

# Deploy from GitHub
az webapp deployment github-actions add \
  --repo pavansreekar44/VayuDrishti \
  --branch main \
  --resource-group vayu-rg \
  --name vayu-drishti-backend
```

## Deployment Option 3: Using Docker Container

If you prefer Docker deployment:

```bash
# Create Container Registry
az acr create \
  --resource-group vayu-rg \
  --name vayudristhi \
  --sku Basic

# Build and push image
az acr build \
  --registry vayudristhi \
  --image vayu-drishti:latest \
  --file Dockerfile .

# Create web app from container
az webapp create \
  --resource-group vayu-rg \
  --plan vayu-plan \
  --name vayu-drishti-backend \
  --deployment-container-image-name vayudristhi.azurecr.io/vayu-drishti:latest
```

## Configuration Files Included

- **startup.sh** - Entry point for Linux App Service (Oryx build system)
- **web.config** - Configuration for Windows App Service (IIS)
- **.deployment** - Azure deployment configuration
- **gunicorn_config.py** - Gunicorn WSGI server configuration
- **Dockerfile** - For containerized deployment

## Testing Locally

Test the startup script locally before deploying:

```bash
# Make it executable
chmod +x startup.sh

# Run it
./startup.sh
```

The app should be accessible at `http://localhost:8000/docs` (Swagger UI)

## Monitoring

After deployment, monitor your app:

```bash
# View logs
az webapp log tail \
  --resource-group vayu-rg \
  --name vayu-drishti-backend

# View deployment logs
az webapp deployment log show \
  --resource-group vayu-rg \
  --name vayu-drishti-backend

# Restart the app
az webapp restart \
  --resource-group vayu-rg \
  --name vayu-drishti-backend
```

Or in the Azure Portal:
- Go to **Log Stream** to see real-time logs
- Go **Advanced Tools** → **Kudu** (`https://vayu-drishti-backend.scm.azurewebsites.net`) for full console access

## Troubleshooting

### Build takes too long
- Increase App Service Plan to B2 or higher
- Use Docker deployment for faster builds

### 502 Bad Gateway errors
- Check startup command in Configuration
- Check Python path in web.config
- Review logs in Log Stream
- Ensure requirements.txt has all dependencies

### Module not found errors
- Verify PYTHONPATH is set correctly
- Check that all packages are in requirements.txt
- Ensure backend/ directory structure is correct

### Connection timeouts to database/Redis
- Check DATABASE_URL and REDIS_URL format
- Verify firewall rules allow Azure App Service IP range
- For local testing, check if services are running

## Scaling

When you need to scale:

1. **Vertical scaling** - Change App Service Plan size
   ```bash
   az appservice plan update \
     --name vayu-plan \
     --resource-group vayu-rg \
     --sku B2  # or higher
   ```

2. **Horizontal scaling** - Add instances
   ```bash
   az appservice plan update \
     --name vayu-plan \
     --resource-group vayu-rg \
     --number-of-workers 2
   ```

3. **Auto-scaling** - Set up automatic scaling rules in Azure Portal

## Cost Optimization

- Use B1 tier for development/testing (~$10/month)
- Use B2 or higher for production (~$30-50/month)
- Consider reserved instances for long-term savings
- Use Linux App Service (cheaper than Windows)

## Next Steps

1. Update `requirements.txt` if needed
2. Test deployment on Azure
3. Set up custom domain (optional)
4. Enable HTTPS/SSL (automatic with Azure)
5. Set up Application Insights for monitoring
6. Configure auto-deployment from GitHub

For more information, see [Azure Web App Documentation](https://docs.microsoft.com/azure/app-service/)
