# CLAUDE.md - Development Workflow Guidelines

## Critical Development Workflow Rules

### ⚠️ NEVER Make Direct Changes on Server

**IMPORTANT:** All code changes MUST follow this process:

1. **Create a branch locally**
   ```bash
   git checkout -b fix/descriptive-name
   ```

2. **Make changes locally and commit**
   ```bash
   # Make your changes
   git add .
   git commit -m "descriptive message"
   ```

3. **Push branch to remote**
   ```bash
   git push -u origin fix/descriptive-name
   ```

4. **Deploy to camera1 server**
   ```bash
   ssh camera1 "cd camera-platform-local && git fetch && git checkout fix/descriptive-name && git pull"
   ```

5. **Test on camera1**
   ```bash
   ssh camera1 "cd camera-platform-local && ./scripts/managed_start.sh restart"
   ```

6. **Merge to main when verified**
   ```bash
   git checkout main
   git merge fix/descriptive-name
   git push origin main
   ```

7. **Deploy main to camera1**
   ```bash
   ssh camera1 "cd camera-platform-local && git checkout main && git pull"
   ssh camera1 "cd camera-platform-local && ./scripts/managed_start.sh restart"
   ```

### ❌ NEVER Do This:
- DO NOT edit files directly on camera1
- DO NOT make changes via SSH without git
- DO NOT rush to fix without creating a branch
- DO NOT bypass the git workflow "just this once"

### ✅ Always Do This:
- ALWAYS create a branch for changes
- ALWAYS commit and push before deploying
- ALWAYS use git to manage code changes
- ALWAYS follow the proper workflow

## Why This Matters

1. **Version Control:** All changes are tracked in git history
2. **Reproducibility:** Changes can be rolled back if needed
3. **Testing:** Changes can be tested on branches before merging
4. **Collaboration:** Clear history of what changed and why
5. **Disaster Recovery:** Server can be rebuilt from git repo

## Server-Specific Notes

### Config Server Running as Root
- Config server runs as root (needed for port 80)
- This is intentional and required
- Files uploaded by cameras are created with root:root ownership
- DO NOT change config server to run as non-root user

## Common Issues and Solutions

### Issue: Files owned by root, cleanup fails
**Wrong approach:** Change permissions directly on server
**Right approach:** Modify code to set ownership after file creation, commit via git workflow

### Issue: Dashboard not showing changes
**Wrong approach:** Edit dashboard_server.py on server
**Right approach:** Make changes locally, commit, push, deploy via git

### Issue: Quick fix needed urgently
**Wrong approach:** SSH and edit files directly
**Right approach:** Still create a branch, just work quickly through the git workflow
