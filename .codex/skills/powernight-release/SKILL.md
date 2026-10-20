---
name: powernight-release
description: Publish and promote a PowerNight Docker release (version tag, Docker Publish, canary, Docker Promote to latest) and help Synology users pick up the update. Use when cutting a release, when `latest` looks stale, or when Container Manager does not show a new PowerNight image.
---

# PowerNight release and `latest` promotion

The full runbook is in `.github/workflows/README.md` (Release Process). This skill covers the parts that are easy to miss.

## Key fact: publishing does NOT move `latest`

- Pushing a version tag (for example `2.0.0`) runs **Docker Publish** (`.github/workflows/docker-publish.yml`). It pushes only the version tag (`flavor: latest=false`) to `ghcr.io/zaai-com/powernight` and `zaaicom/powernight`.
- `latest` moves only when someone runs **Docker Promote** (`.github/workflows/docker-promote.yml`) by hand. Until then, anyone running `latest` stays on the old release and sees no update.
- Example: 2.0.0 was published on 2026-10-19, but `latest` pointed to 1.0.0 until Docker Promote was run on 2026-10-20.

## Steps after Docker Publish succeeds

1. Get the manifest-list digest from the publish run (`gh run view <id> --log | grep "exporting manifest list"`) or from Docker Hub:
   ```bash
   curl -s "https://hub.docker.com/v2/repositories/zaaicom/powernight/tags?page_size=10" \
     | python3 -I -c 'import json,sys; [print(t["name"], t["last_updated"], t.get("digest")) for t in json.load(sys.stdin)["results"]]'
   ```
2. Canary: run the exact version tag on a real install, then check it through an upgrade, a restart, a Tesla reconnect, and one overnight scheduling cycle. `canary_verified=true` is the maintainer's sign-off on this, so ask the user before setting it.
3. Promote (must run from `main`; the workflow checks the digest on both registries and the amd64/arm64/arm-v7 platforms, then retags without rebuilding):
   ```bash
   gh workflow run docker-promote.yml --ref main \
     -f version=<X.Y.Z> \
     -f digest=sha256:<64 hex> \
     -f canary_verified=true
   gh run watch <run-id> --exit-status
   ```
4. Verify: re-run the curl from step 1. `latest` and `<X.Y.Z>` must show the same digest.

Promotion publishes to public registries. Always get explicit user confirmation before dispatching Docker Publish or Docker Promote.

## Synology Container Manager does not show the update

Check in this order:

1. **Is `latest` promoted?** If `latest` still has the old digest, Synology has nothing to find. Promote first.
2. **Which tag is the container using?** Version tags never change, so a container on `2.0.0` will never show an update. Only `latest` does.
3. **Force the check.** Container Manager checks upstream only occasionally. DSM 7.3 has an internal tool that forces it:
   ```
   /var/packages/ContainerManager/target/tool/image_upgradable_checker
   ```
   Run it from a Task Scheduler user-defined script with **User = `root`**. Run as a regular user, it ends with "Interrupted (255)". It prints nothing, even when it works (empty `output.log` is normal). Check the result in Container Manager > Image after a refresh.

User-facing steps are in `docs/README.md` (Synology NAS > Update notifications).
