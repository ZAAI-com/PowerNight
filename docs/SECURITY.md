# Security Guidelines

## ⚠️ **IMPORTANT: Security Assumptions**

PowerNight is designed for deployment in **trusted local networks only**:

- ✅ **Intended Use**: Deploy within your home/private network behind a firewall
- ❌ **NOT for Public Internet**: Do not expose PowerNight directly to the internet
- 🔓 **Web UI Access**: The web interface is **NOT password protected** by default
- 🌐 **Network Security**: Rely on network-level security (firewall, VPN) for access control

### Deployment Security Best Practices

1. **Local Network Only**: Only accessible from your trusted home/office network
2. **Firewall Protection**: Use router/firewall rules to block external access to port 8020
3. **VPN for Remote Access**: Use VPN (WireGuard, OpenVPN) for secure remote access

⚠️ **Warning**: Exposing PowerNight directly to the internet without additional security measures could allow unauthorized control of your Tesla Powerwall.

---

## 🔒 **IMPORTANT: Remove All Sensitive Data Before Committing**

This repository should **NEVER** contain:
- Real Powerwall passwords
- API keys or tokens
- Personal credentials
- Production configuration with sensitive data

## ✅ **Security Checklist**

Before committing any changes, ensure:

- [ ] No real passwords in configuration files
- [ ] No API keys or tokens in code
- [ ] No personal credentials in examples
- [ ] All sensitive data replaced with placeholders
- [ ] Configuration files use example values only

---

**Remember: Security is everyone's responsibility!** 🛡️
