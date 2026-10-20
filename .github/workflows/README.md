# GitHub Actions Workflows

This directory contains automated workflows for PowerNight's CI/CD pipeline.

## Workflows Overview

### 1. `docker-publish.yml` - Multi-Registry Publishing

**Trigger**: Git tags matching `[0-9]+.[0-9]+.[0-9]+` (e.g., `1.0.0`, `1.1.0`, `10.15.2`) or manual workflow dispatch

**Purpose**: Automatically builds and publishes multi-architecture Docker images to GitHub Container Registry (GHCR) and Docker Hub when a new version is tagged.

**Steps**:
1. Checkout repository
2. Extract version from git tag
3. Set up Node.js and Python
4. Build frontend with `./build.sh --no-docker`
5. Set up QEMU and Docker Buildx for multi-arch builds
6. Login to GitHub Container Registry (GHCR)
7. Login to Docker Hub using organization secrets
8. Build and push images for:
   - `linux/amd64` (Intel/AMD x86_64)
   - `linux/arm64` (ARM 64-bit)
   - `linux/arm/v7` (ARM 32-bit)
9. Update Docker Hub repository description from docs/README.md
10. Generate build summary

**Versioned Docker Tags Created** (latest is promoted separately):

*GitHub Container Registry (Primary):*
- `ghcr.io/zaai-com/powernight:<version>` (e.g., `1.0.0`)
- `ghcr.io/zaai-com/powernight:latest` (only after Docker Promote)

*Docker Hub (Mirror):*
- `zaaicom/powernight:<version>` (e.g., `1.0.0`)
- `zaaicom/powernight:latest` (only after Docker Promote)

**Required Secrets** (Organization-level):
- `DOCKERHUB_USERNAME` - Docker Hub username (zaaicom)
- `DOCKERHUB_TOKEN` - Docker Hub access token
- `GITHUB_TOKEN` - Automatically provided by GitHub Actions for GHCR access

**Usage**:
```bash
# Create and push a new version tag
git tag -a 1.0.0 -m "Release 1.0.0"
git push origin 1.0.0

# GitHub Actions automatically builds and publishes to both registries
# Monitor progress at: https://github.com/ZAAI-com/PowerNight/actions

# Pull from GHCR (recommended)
docker pull ghcr.io/zaai-com/powernight:1.0.0

# Or pull from Docker Hub (mirror)
docker pull zaaicom/powernight:1.0.0
```

---

### 2. `docker-health-test.yml` - Docker Health Test

**Trigger**:
- Pull requests to `main` branch
- Pushes to `main` branch
- Changes to Docker-related files

**Purpose**: Validates Docker builds work correctly before merging or releasing.

**Steps**:
1. Checkout repository
2. Build frontend
3. Build Docker image (amd64 only for speed)
4. Run `scripts/release_smoke.py` with isolated Docker Compose projects
5. Verify open and protected API access, SPA routes, and bundled assets
6. Migrate synthetic legacy data and verify preset conflicts return HTTP 409
7. Confirm saved configuration excludes environment-provided API keys
8. Recreate containers and verify database, auth artifacts, and Flask secret persist
9. Save container logs and generate a JSON test summary; remove disposable volumes

**Why This Matters**:
- Catches Dockerfile issues early
- Validates build script changes
- Ensures container starts correctly
- Tests health checks work

**Viewing Results**:
- Check the "Actions" tab on GitHub
- PR checks must pass before merge
- Failed builds block merging

---

### 3. `docker-hub-readme-sync.yml` - README Sync

**Trigger**:
- Changes to `docs/README.md` on `main` branch
- Manual workflow dispatch

**Purpose**: Keeps Docker Hub repository description in sync with the project README.

**Steps**:
1. Checkout repository
2. Update Docker Hub description with docs/README.md content
3. Generate sync summary

**Why This Matters**:
- Docker Hub overview page stays up-to-date
- Users see current documentation on Docker Hub
- No manual updates needed

**Manual Trigger**:
```bash
# Via GitHub UI:
# Actions → Sync README to Docker Hub → Run workflow
```

---

### 4. `docker-security-scan.yml` - Security Scanning

**Trigger**:
- Manual workflow dispatch only (auto-run disabled)
- Optional: Can be configured for scheduled scans or on dependency changes

**Purpose**: Scans published Docker images for security vulnerabilities using Trivy.

**Steps**:
1. Checkout repository
2. Determine image tag to scan (default: `latest`)
3. Run Trivy vulnerability scanner on the published image
4. Generate SARIF report
5. Upload scan results to GitHub Security tab
6. Display detailed vulnerability table
7. Generate scan summary

**Configuration**:
- **Severity**: HIGH, CRITICAL
- **Failure Policy**: Continues on error (reports but doesn't fail)
- **Output**: SARIF format uploaded to GitHub Security + table format for review
- **Scope**: Full image scan (OS packages and application dependencies)

**Manual Trigger**:
```bash
# Via GitHub UI:
# Actions → Docker Security Scan → Run workflow
# Optional: Specify custom image tag (default: latest)
```

**Viewing Scan Results**:
1. Go to repository → Security → Code scanning alerts
2. View Trivy findings and vulnerability details
3. Address HIGH/CRITICAL vulnerabilities before release

**Why This Matters**:
- Identifies known vulnerabilities in dependencies
- Provides security compliance reporting
- Helps maintain secure Docker images
- Can be run on-demand before releases

**Local Scanning**:
```bash
# Scan locally using Trivy
docker pull zaaicom/powernight:latest
trivy image zaaicom/powernight:latest

# Or scan specific version
trivy image zaaicom/powernight:1.0.0
```

---

## Release Process

Releases are staged: Docker Publish writes version-only tags, and Docker Promote
updates `latest` separately after a verified live canary. Local-only validation
must not dispatch either publishing or promotion.

1. Complete CI and Docker Compose persistence/migration tests for the release commit.
   `python scripts/release_smoke.py --image powernight-release:test` runs the same
   isolated smoke checks used by Docker Health Test, with no Tesla access.
2. Verify all version identifiers using `python scripts/check_release_version.py 2.0.2`.
3. Merge to `main` and tag the verified commit as `2.0.2` (no `v` prefix).
   Pushing the tag triggers Docker Publish. Manual publication must also select
   the release tag as its ref. Only commits contained in `main` are publishable.
4. Record the image digest from the publish summary. Verify both registries have
   that version and the required amd64, arm64, and arm/v7 manifests.
5. Back up canary data, pin the version/digest in Docker Compose, and validate
   upgrade, restart, reconnect, and one overnight scheduling cycle.
6. Run Docker Promote from `main` with the version, exact digest, and
   `canary_verified=true`. It verifies both registry tags before changing either
   `latest` and promotes the tested digest without rebuilding.
7. Publish the GitHub release notes and monitor the rollout. Registry promotion
   is not atomic; on a partial failure, inspect both registries and finish using
   the same verified digest.

See [2.0.0 release notes and rollback runbook](../../docs/releases/2.0.0.md).
Database rollback requires the pre-upgrade data backup as well as the old image.

---

## Security Scanning

### Trivy Vulnerability Scanner

Security scanning is performed via the `docker-security-scan.yml` workflow, which can be triggered manually or configured for automated scans.

**Configuration**:
- **Severity**: HIGH, CRITICAL
- **Failure Policy**: Continues on error (reports but doesn't fail workflow)
- **Output**: SARIF format uploaded to GitHub Security + detailed table
- **Scope**: Full image scan (OS packages and application dependencies)

**How to Run**:
1. Go to Actions → Docker Security Scan → Run workflow
2. Optionally specify an image tag (default: `latest`)
3. Wait for scan to complete (~2-5 minutes)

**Viewing Scan Results**:
1. Go to repository → Security → Code scanning alerts
2. View Trivy findings with severity levels
3. Click on findings for detailed CVE information
4. Address HIGH/CRITICAL vulnerabilities before release

**Fixing Vulnerabilities**:
```bash
# Update base image in Dockerfile
FROM python:3.11-slim  # Use latest patch version

# Update Python dependencies
pip install --upgrade <package>

# Update frontend dependencies
npm update

# Rebuild and test
./build.sh

# Rescan to verify fixes
# Actions → Docker Security Scan → Run workflow
```

**Automated Scanning** (Optional):
You can enable automated scans by uncommenting the schedule section in `docker-security-scan.yml`:
```yaml
schedule:
  # Run every Monday at 9:00 AM UTC
  - cron: '0 9 * * 1'
```

---

## Troubleshooting Workflows

### Build Fails on Frontend Build

**Symptom**: Workflow fails at "Build frontend" step

**Solution**:
```bash
# Test build locally
./build.sh --no-docker

# Check for errors
npm run build

# Verify dist/ directory created
ls -la dist/
```

### Docker Login Fails

**Symptom**: "Error: Cannot perform an interactive login from a non TTY device"

**Solution**:
1. Verify organization secrets are set:
   - Go to GitHub → ZAAI-com → Settings → Secrets
   - Confirm `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` exist
2. Verify repository access:
   - Check secret has access to PowerNight repository
3. Verify token is valid:
   - Login to Docker Hub
   - Check access token hasn't expired

### Multi-Arch Build Fails

**Symptom**: Build fails for arm64 or arm/v7

**Solution**:
- Usually a dependency issue
- Check if all Python packages support ARM
- Check base image supports all architectures
- View detailed logs in Actions tab

### Security Scan Fails

**Symptom**: `docker-security-scan.yml` workflow fails or shows vulnerabilities

**Solution**:
1. View scan results in Security tab
2. Review CVE details for each vulnerability
3. Update vulnerable dependencies (Python packages or base image)
4. Rebuild and republish Docker image
5. Re-run security scan to verify fixes
6. For false positives, document and consider adding to exceptions

### README Sync Fails

**Symptom**: docs/README.md not updating on Docker Hub

**Solution**:
1. Check Docker Hub credentials
2. Verify repository name is correct: `zaaicom/powernight`
3. Check README.md is valid Markdown
4. Manually trigger workflow to retry

---

## Workflow Maintenance

### Updating Workflow Dependencies

Periodically update GitHub Actions to latest versions:

```yaml
# Before
uses: actions/checkout@v3

# After
uses: actions/checkout@v4
```

**Actions to Monitor**:
- `actions/checkout`
- `actions/setup-node`
- `actions/setup-python`
- `docker/setup-qemu-action`
- `docker/setup-buildx-action`
- `docker/build-push-action`
- `docker/login-action`
- `docker/metadata-action`
- `aquasecurity/trivy-action`
- `peter-evans/dockerhub-description`

### Adding New Platforms

To add a new architecture (e.g., `linux/riscv64`):

1. Update `docker-publish.yml`:
   ```yaml
   env:
     PLATFORMS: linux/amd64,linux/arm64,linux/arm/v7,linux/riscv64
   ```

2. Test build locally:
   ```bash
   docker buildx build --platform linux/riscv64 -t test .
   ```

3. Ensure dependencies support new platform

---

## Best Practices

1. **Always test locally first**
   ```bash
   ./build.sh --no-docker
   docker build -t powernight-release:test .
   python scripts/release_smoke.py --image powernight-release:test
   ```

2. **Use semantic versioning**
   - MAJOR.MINOR.PATCH (e.g., 1.0.0)
   - Breaking changes → bump MAJOR
   - New features → bump MINOR
   - Bug fixes → bump PATCH

3. **Write descriptive tag messages**
   ```bash
   git tag -a 0.4.0 -m "Release 0.4.0

   New features:
   - Multi-site support
   - Enhanced scheduling

   Bug fixes:
   - Fixed OAuth token refresh
   "
   ```

4. **Monitor builds**
   - Watch Actions tab during release
   - Don't assume success - verify!

5. **Test staged images before promoting latest**
   ```bash
   # After version publication, test in isolated Compose projects (no Tesla access)
   docker pull ghcr.io/zaai-com/powernight:2.0.2
   python scripts/release_smoke.py --image ghcr.io/zaai-com/powernight:2.0.2

   # Or test Docker Hub image (mirror)
   docker pull zaaicom/powernight:2.0.2
   python scripts/release_smoke.py --image zaaicom/powernight:2.0.2
   ```

---

## GitHub Actions Costs

PowerNight uses GitHub-hosted runners:
- **Free tier**: 2,000 minutes/month for public repos
- **Typical build**: ~15-20 minutes
- **Monthly releases**: 2-3 builds/month = ~60 minutes
- **PR builds**: Variable, usually < 10 minutes each

**Optimization Tips**:
- Cache dependencies (`cache: 'npm'`, `cache: 'pip'`)
- Use Docker layer caching (`cache-from: type=gha`)
- Test workflow only runs on relevant file changes
- Multi-arch builds run in parallel

---

## Support

If workflows fail or you need help:

1. **Check Logs**: Actions tab → Failed workflow → View logs
2. **GitHub Discussions**: Ask questions in repository discussions
3. **GitHub Issues**: Report bugs or request features
4. **Documentation**: Review this file and workflow comments

---

## Related Documentation

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Build Push Action](https://github.com/docker/build-push-action)
- [GitHub Container Registry](https://github.com/ZAAI-com/PowerNight/pkgs/container/powernight)
- [Docker Hub (Mirror)](https://hub.docker.com/r/zaaicom/powernight)
- [PowerNight Main README](../../docs/README.md)
- [Trivy Security Scanner](https://github.com/aquasecurity/trivy)
