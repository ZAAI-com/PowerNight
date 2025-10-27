# FAQ & Troubleshooting

## Table of Contents

- [Frequently Asked Questions](#frequently-asked-questions)
  - [Why Not Use Tesla's Time-Based Control?](#why-not-use-teslas-time-based-control)
- [Common Issues](#common-issues)
  - [Powerwall Connection Failed](#powerwall-connection-failed)
  - [Web Interface Not Accessible](#web-interface-not-accessible)
  - [Tasks Not Executing](#tasks-not-executing)
  - [OAuth Token Expired](#oauth-token-expired)
  - [High Memory Usage](#high-memory-usage)
- [Log Analysis](#log-analysis)
- [Debug Mode](#debug-mode)
- [Health Check Endpoint](#health-check-endpoint)

---

## Frequently Asked Questions

### Why Not Use Tesla's Time-Based Control?

**Question**: Tesla Powerwall has a built-in "Time-Based Control" feature. Why should I use PowerNight instead?

**Answer**: I tested the built-in "Time-Based Control" (TBC) mode for several weeks and found it unreliable for my needs. The charging behavior was unpredictable - TBC tends to charge only during the last 1-2 hours of the off-peak window at full speed. This means I would need to monitor the battery State of Charge (SOC) between 3-4 AM to ensure proper charging, which is not practical. PowerNight gives me predictable, rule-based control over exactly when and how much the battery charges.

**Key Differences:**
- **TBC**: Unpredictable charging pattern, typically charges at the end of off-peak period
- **PowerNight**: Predictable schedule-based control with precise timing
- **TBC**: No visibility into when charging will occur
- **PowerNight**: Full control over reserve percentage changes at specific times
- **TBC**: Requires monitoring overnight to verify charging
- **PowerNight**: Set-and-forget automation with execution history

---

## Common Issues

### Powerwall Connection Failed

**Symptoms**: Dashboard shows "Unable to connect to Powerwall"

**Solutions:**

```bash
# 1. Check logs
docker logs PowerNight

# 2. Verify OAuth tokens exist
docker exec PowerNight ls -la /data/.pypowerwall.*

# 3. Test connection
curl http://localhost:8020/health

# 4. Re-authorize Tesla OAuth
# Navigate to Settings � Tesla Configuration � Authorize
```

### Web Interface Not Accessible

**Symptoms**: Cannot access `http://localhost:8020`

**Solutions:**

```bash
# 1. Check container status
docker ps | grep PowerNight

# 2. Verify port mapping
docker port PowerNight
# Should show: 8020/tcp -> 0.0.0.0:8020

# 3. Check container logs for startup errors
docker logs PowerNight | grep ERROR

# 4. Verify firewall allows port 8020
sudo ufw status | grep 8020  # Linux
```

### Tasks Not Executing

**Symptoms**: Scheduled tasks don't run at specified times

**Solutions:**

```bash
# 1. Check automation enabled
docker exec PowerNight cat /data/config.yaml | grep automation -A 5

# 2. Check task execution logs
docker logs PowerNight | grep "Task execution"

# 3. Verify timezone configuration
# Ensure automation.timezone matches your local timezone

# 4. Check scheduler status
curl http://localhost:8020/api/v1/tasks
```

### OAuth Token Expired

**Symptoms**: "Authentication failed" errors after working previously

**Solutions:**

```bash
# 1. Check token file modification time
docker exec PowerNight ls -l /data/.pypowerwall.auth

# 2. Re-authorize via web interface
# Settings � Tesla Configuration � Authorize

# 3. Restart container to trigger token refresh
docker-compose restart PowerNight
```

### High Memory Usage

**Symptoms**: Container using >512MB memory

**Solutions:**

```bash
# 1. Check current memory usage
docker stats PowerNight

# 2. Review log file size
docker exec PowerNight du -sh /data/logs/

# 3. Rotate logs
docker exec PowerNight find /data/logs/ -type f -name "*.log.*" -delete

# 4. Adjust log retention in config
# logging.backup_count: 3  # Reduce from 5
```

---

## Log Analysis

PowerNight uses structured JSON logging. Filter logs by component or level:

```bash
# Filter by component
docker logs PowerNight 2>&1 | grep '"component":"POWERWALL"'

# Filter by error level
docker logs PowerNight 2>&1 | grep '"level":"ERROR"'

# Last 100 lines with timestamps
docker logs PowerNight --tail 100 --timestamps

# Follow logs in real-time
docker logs PowerNight -f

# Export logs to file
docker logs PowerNight > powernight-logs-$(date +%Y%m%d).log
```

---

## Debug Mode

Enable debug logging for detailed diagnostics:

```bash
# Via environment variable
docker-compose stop
docker-compose up -d -e POWERNIGHT_LOG_LEVEL=DEBUG

# Via config file
docker exec PowerNight vi /data/config.yaml
# Set logging.level: DEBUG
docker-compose restart PowerNight

# View debug logs
docker logs PowerNight | grep DEBUG
```

---

## Health Check Endpoint

Monitor system health programmatically:

```bash
curl http://localhost:8020/health | jq
```

Response:

```json
{
  "status": "healthy",
  "timestamp": "2025-10-22T10:30:00Z",
  "version": "1.0.0"
}
```

**Status values:**
- `healthy` - All systems operational
- `degraded` - Some subsystems failing (e.g., Powerwall unreachable)
- `unhealthy` - Critical failures
