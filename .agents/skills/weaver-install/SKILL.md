---
name: weaver-install
description: Install Weaver from Docker or source for local development, testing, or production deployment. Covers Docker deployment and conda environment setup using Makefile targets. Use when setting up a new Weaver instance or development environment.
license: Apache-2.0
compatibility: Requires Python 3.10+, conda (recommended), Docker (for container deployment), Make.
metadata:
  category: setup-operations
  version: "1.0.0"
  author: CRIM
allowed-tools: run_command file_read
---

# Install Weaver

Install and set up Weaver for development, testing, or production use.

## When to Use

- Setting up a new Weaver development environment
- Installing Weaver for local testing
- Deploying Weaver in production
- Contributing to Weaver development
- Running Weaver services locally

## Prerequisites

### System Requirements

- **Python**: 3.10 or higher
- **Operating System**: Linux, macOS, or Windows (with WSL)
- **Make**: Build tool for using Makefile targets (if using source installation instead of Docker)

### Required Dependencies

- **Git**: For cloning repository
- **Conda/Miniconda**: For isolated environment management (recommended)
- **Docker**: For containerized deployment (portable production/testing)

**Note**: If you prefer to install directly in your current Python environment without conda, you can set `CONDA_CMD=""` (empty string) before running make commands. This bypasses conda creation/activation/detection and installs using the detected Python interpreter.

## Installation Methods

### Method 1: Docker (Recommended for Production)

#### Pull Pre-built Image

```bash
# Latest development version
docker pull pavics/weaver:latest

# Manager image (API and job management)
docker pull pavics/weaver:latest-manager

# Worker image (job execution)
docker pull pavics/weaver:latest-worker

# Specific version (check available tags on DockerHub)
docker pull pavics/weaver:X.Y.Z
docker pull pavics/weaver:X.Y.Z-manager
docker pull pavics/weaver:X.Y.Z-worker
```

#### Run Weaver Container

```bash
# Basic run
docker run -p 4001:4001 pavics/weaver:latest

# With configuration
docker run -p 4001:4001 \
  -v $(pwd)/config:/config \
  -e WEAVER_INI_FILE=/config/weaver.ini \
  pavics/weaver:latest

# With docker-compose
cd docker
cp docker-compose.yml.example docker-compose.yml
# Edit docker-compose.yml as needed
docker-compose up -d
```

#### Available Docker Tags

- `pavics/weaver:latest` - Latest development version
- `pavics/weaver:latest-manager` - Manager service (latest)
- `pavics/weaver:latest-worker` - Worker service (latest)
- `pavics/weaver:X.Y.Z` - Specific stable version
- `pavics/weaver:X.Y.Z-manager` - Manager service (specific version)
- `pavics/weaver:X.Y.Z-worker` - Worker service (specific version)

### Method 2: From Source with Makefile (Development)

#### Clone Repository

```bash
# Clone from GitHub
git clone https://github.com/crim-ca/weaver.git
cd weaver

# Checkout specific version (optional)
git checkout X.Y.Z
```

#### Install with Makefile Targets

The Makefile provides several installation targets for different use cases:

##### Standard Installation (Recommended)

```bash
# Install everything needed to run Weaver commands
make install
```

**This is sufficient for**:

- Running Weaver CLI commands (`weaver deploy`, `weaver execute`, etc.)
- Starting Weaver server locally
- Deploying and executing processes
- General usage and testing

This is an alias for `make install-all` and runs:

- `conda-env` - Creates conda environment
- `conda-install` - Installs conda packages (proj, etc.)
- `install-sys` - Installs system dependencies
- `install-pkg` - Installs application packages
- `install-pip` - Installs application as editable package
- `install-dev` - Installs development/test dependencies

##### Runtime-Only Installation (Minimal)

```bash
# Install only runtime dependencies (no development tools)
make install-run
```

**Use this if you only need**:

- To run Weaver server in production
- Minimal installation footprint
- No testing or development capabilities

This runs:

- `conda-install` - Installs conda packages
- `install-sys` - Installs system dependencies
- `install-pkg` - Installs application packages
- `install-raw` - Installs application without dependencies

##### Development-Specific Targets

**These are only needed for Weaver development** (not required for using Weaver):

```bash
# Install development/test dependencies only
make install-dev
# Required for: make test, make lint, make check-types

# Install documentation dependencies only
make install-doc
# Required for: make docs

# Install application as editable package only
make install-pip
# Required for: development with code changes reflected immediately
```

##### Individual Component Targets

```bash
# Just create/update conda environment
make conda-env

# Install system dependencies (pip, setuptools, etc.)
make install-sys

# Install application package dependencies
make install-pkg

# Install application without dependencies
make install-raw
```

#### Quick Installation

**For most users** (running Weaver commands and processes):

```bash
# One command does it all (with conda)
make install

# Activate environment
conda activate weaver

# You're ready to use Weaver
weaver --version
pserve config/weaver.ini
```

**Alternative**: Without conda (use current Python environment):

```bash
# Bypass conda and install directly in current Python
CONDA_CMD="" make install

# No conda activation needed - already in your environment
weaver --version
pserve config/weaver.ini
```

#### Manual Step-by-Step Installation

If you prefer to understand each step:

```bash
# 1. Create conda environment
make conda-env

# 2. Activate environment
conda activate weaver

# 3. Install system dependencies
make install-sys

# 4. Install application dependencies
make install-pkg

# 5. Install application itself
make install-pip

# 6. (Recommended) Install development tools for testing
make install-dev
```

**Note**: `make install` does all of the above automatically.

## Configuration

### Create Configuration File

```bash
# Copy example configuration
cp config/weaver.ini.example config/weaver.ini

# Edit configuration
vim config/weaver.ini
```

### Key Configuration Options

```ini
[app:main]
# Weaver mode: ADES, EMS, or HYBRID
weaver.configuration = HYBRID

# Database connection
weaver.url = http://localhost:4001
weaver.wps_output_url = http://localhost:4001/wpsoutputs
weaver.wps_output_dir = /tmp/weaver-outputs

# MongoDB connection
weaver.mongodb_connection = mongodb://localhost:27017/weaver

# Celery broker
celery.broker_url = mongodb://localhost:27017/celery
celery.result_backend = mongodb://localhost:27017/celery
```

### Configuration Modes

**ADES** (Application Deployment and Execution Service):

- Local process execution
- Direct access to data
- Single-node deployment

**EMS** (Execution Management Service):

- Orchestrates remote ADES
- Distributed workflow execution
- Multi-node deployment

**HYBRID**:

- Both ADES and EMS capabilities
- Most flexible configuration

## Running Weaver

### Development Mode

```bash
# With pserve (development server)
pserve config/weaver.ini --reload

# Access API at http://localhost:4001
```

### Production Mode

```bash
# Using gunicorn
gunicorn --paste config/weaver.ini -b 0.0.0.0:4001 --workers 4

# Using docker-compose
docker-compose -f docker/docker-compose.yml up -d
```

### Worker Process

```bash
# Start Celery worker for job execution
celery -A pyramid_celery.celery_app worker \
  --ini config/weaver.ini \
  --loglevel INFO
```

## Verification

### Check Installation

```bash
# Python package (after activating conda environment)
conda activate weaver
python -c "import weaver; print(weaver.__version__)"

# CLI tool
weaver --version

# API (after starting server)
weaver info -u http://localhost:4001
curl http://localhost:4001/
```

### Test Installation

```bash
# Run tests (requires install-dev)
make test

# Quick test
make test-unit

# Functional tests
make test-functional
```

### Verify Services

```bash
# Check API
curl http://localhost:4001/ | jq

# Check processes endpoint
curl http://localhost:4001/processes | jq

# Check conformance
curl http://localhost:4001/conformance | jq

# Using CLI
weaver info -u http://localhost:4001
weaver capabilities -u http://localhost:4001
```

## Common Installation Issues

### Issue: Python Version Too Old

```bash
# Error: Requires Python 3.10+

# Solution: Specify Python version when creating environment
conda create -n weaver python=3.10
conda activate weaver
make install
```

### Issue: Conda Not Found

```bash
# Error: conda command not found

# Solution 1: Install Miniconda
# Download from: https://docs.conda.io/en/latest/miniconda.html
# Or use the Makefile target
make conda-base

# Solution 2: Bypass conda and use current Python environment
CONDA_CMD="" make install
```

### Issue: Missing System Dependencies

```bash
# Error: gcc not found, or missing libraries

# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y build-essential python3-dev libproj-dev

# macOS (with Homebrew)
brew install proj

# Then reinstall
make install-sys
make install-pkg
```

### Issue: MongoDB Connection Failed

```bash
# Error: Cannot connect to MongoDB

# Solution 1: Install and start MongoDB
sudo apt-get install mongodb
sudo systemctl start mongodb

# Solution 2: Use Docker for MongoDB
docker run -d -p 27017:27017 --name mongodb mongo:latest

# Solution 3: Update connection string in weaver.ini
weaver.mongodb_connection = mongodb://localhost:27017/weaver
```

### Issue: Celery Worker Not Starting

```bash
# Error: Celery connection refused

# Solution: Ensure MongoDB is running (used as broker)
sudo systemctl status mongodb

# Or check Docker container
docker ps | grep mongo

# Verify broker URL in weaver.ini
celery.broker_url = mongodb://localhost:27017/celery
```

### Issue: Docker Permission Denied

```bash
# Error: permission denied while trying to connect to Docker daemon

# Solution: Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Or run with sudo
sudo docker pull pavics/weaver:latest
```

### Issue: Make Target Fails

```bash
# Error: make install-all fails

# Solution: Install dependencies step by step
make conda-env
conda activate weaver
make install-sys
make install-pkg
make install-pip

# Check for specific error messages and resolve
```

## Development Setup

### Standard Setup (Using Weaver)

```bash
# Clone and setup
git clone https://github.com/crim-ca/weaver.git
cd weaver

# Install everything needed to use Weaver
make install

# Activate environment
conda activate weaver

# Start development server
pserve config/weaver.ini --reload

# In another terminal, start worker
conda activate weaver
celery -A pyramid_celery.celery_app worker --ini config/weaver.ini
```

### Advanced Development Setup (Contributing to Weaver)

**Only needed if you're modifying Weaver's code**:

```bash
# After make install, you already have everything
# Additional tools are included in install-dev (part of make install)

# Run linting
make lint

# Run type checking
make check-types

# Format code
make format

# Generate documentation (requires install-doc)
make install-doc
make docs

# Clean build artifacts
make clean
```

### Updating Installation

```bash
# Pull latest changes
git pull origin master

# Reinstall (updates dependencies and application)
make install

# Alternatively, update specific parts:
# Update dependencies only
make install-pkg

# Reinstall application only
make install-pip
```

## Docker Compose Deployment

### Setup

```bash
cd docker

# Copy and customize configuration
cp docker-compose.yml.example docker-compose.yml
cp ../config/weaver.ini.example ../config/weaver.ini

# Edit as needed
vim docker-compose.yml
vim ../config/weaver.ini
```

### Deploy Services

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f weaver

# Check status
docker-compose ps

# Stop services
docker-compose down
```

### Services Included

- **weaver-manager**: API and job management
- **weaver-worker**: Job execution worker
- **mongodb**: Database
- **nginx**: Reverse proxy (optional)

## Environment Variables

### Common Variables

```bash
# Set Weaver URL
export WEAVER_URL=http://localhost:4001

# Set configuration file
export WEAVER_INI_FILE=/path/to/weaver.ini

# Set log level
export WEAVER_LOG_LEVEL=DEBUG

# Set output directory
export WEAVER_WPS_OUTPUT_DIR=/tmp/weaver-outputs

# MongoDB connection
export WEAVER_MONGODB_CONNECTION=mongodb://localhost:27017/weaver
```

## Post-Installation

### Deploy Sample Processes

```bash
# Activate environment
conda activate weaver

# Deploy a test process
weaver deploy -u $WEAVER_URL \
  -p hello-world \
  -b tests/functional/application-packages/DockerCopyImages/deploy.json

# List processes
weaver capabilities -u $WEAVER_URL

# Execute test
weaver execute -u $WEAVER_URL \
  -p hello-world \
  -I tests/functional/application-packages/DockerCopyImages/execute.json
```

### Configure Data Sources

```bash
# Copy data sources example
cp config/data_sources.yml.example config/data_sources.yml

# Edit data sources
vim config/data_sources.yml
```

### Set Up Vault (Optional)

```bash
# Configure vault for secure credentials
cp config/request_options.yml.example config/request_options.yml

# Edit vault settings
vim config/request_options.yml
```

## Production Considerations

### Security

- Use HTTPS in production
- Configure authentication (if needed)
- Secure MongoDB connections
- Isolate worker processes
- Restrict Docker socket access

### Performance

- Use multiple workers for job execution
- Configure appropriate resource limits
- Use external MongoDB for persistence
- Enable result caching
- Monitor resource usage

### Monitoring

- Set up log aggregation
- Configure health checks
- Monitor job queue
- Track resource usage
- Set up alerts

## Makefile Reference

### Installation Targets

```bash
make install           # Alias for install-all
make install-all       # Full development installation
make install-run       # Runtime-only installation
make install-dev       # Development dependencies only
make install-doc       # Documentation dependencies only
make install-pkg       # Application packages only
make install-sys       # System dependencies only
make install-pip       # Application as editable package
make install-raw       # Application without dependencies
```

### Environment Targets

```bash
make conda-base        # Install conda/miniconda
make conda-env         # Create conda environment
make conda-config      # Configure conda channels
make conda-install     # Install conda packages
```

### Testing Targets

```bash
make test              # Run all tests
make test-unit         # Unit tests only
make test-functional   # Functional tests only
```

### Development Targets

```bash
make start             # Start development server
make start-worker      # Start Celery worker
make clean             # Clean build artifacts
make lint              # Run linting
make docs              # Generate documentation
```

## Related Skills

- [api-info](../api-info/) - Verify installation
- [api-version](../api-version/) - Check installed version
- [process-deploy](../process-deploy/) - Deploy first process
- [job-execute](../job-execute/) - Run test job
- [api-conformance](../api-conformance/) - Verify OGC compliance

## Documentation

- [Installation Guide](https://pavics-weaver.readthedocs.io/en/latest/installation.html)
- [Configuration](https://pavics-weaver.readthedocs.io/en/latest/configuration.html)
- [Docker Deployment](https://pavics-weaver.readthedocs.io/en/latest/installation.html#docker-images)
- [GitHub Repository](https://github.com/crim-ca/weaver)
- [DockerHub Images](https://hub.docker.com/r/pavics/weaver)

## Quick Start Summary

```bash
# Method 1: Docker (fastest)
docker pull pavics/weaver:latest
docker run -p 4001:4001 pavics/weaver:latest

# Method 2: From source (for running weaver commands)
git clone https://github.com/crim-ca/weaver.git
cd weaver
make install
conda activate weaver
pserve config/weaver.ini

# Verify
weaver info -u http://localhost:4001
```

Choose the method that best fits your use case and environment!
