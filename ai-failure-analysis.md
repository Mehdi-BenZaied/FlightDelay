# AI Pipeline Failure Analysis

**Status:** insufficient_evidence
**Failed stage:** Build Frontend
**Component:** Docker API connection
**Category:** docker
**Confidence:** 80%

## Summary

The Jenkins build agent is unable to connect to the Docker API, which indicates a problem with Docker Desktop WSL integration.

## Probable root cause

Docker Desktop WSL integration is disabled or not properly configured.

## Evidence

### ci-logs/docker-test.log

```text
ERROR: failed to connect to the docker API at unix:///var/run/docker.sock
dial unix /var/run/docker.sock: connect: no such file or directory
```

This error clearly indicates that the Jenkins agent is unable to establish a connection to the Docker daemon, which is essential for building and running Docker images.

## Checks

### Windows PowerShell

Purpose: Check if WSL is properly installed and running.

```text
wsl --list --verbose
```

Expected: The output should list the Ubuntu distribution as running.

### Windows PowerShell

Purpose: Verify that Docker Desktop service is running on Windows.

```text
Get-Service -Name docker-desktop
```

Expected: The service status should be 'Running'.

### WSL

Purpose: Check if Docker is installed and accessible within WSL.

```text
docker --version
```

Expected: The command should return the version of Docker installed.

## Remediation

- **HIGH** [destructive]: Ensure that Docker Desktop is running on Windows.

```text
Start-Service -Name docker-desktop
```

- **MEDIUM** [destructive]: Re-enable WSL integration in Docker Desktop settings.

```text
docker desktop --settings
```

## Prevention

- Ensure that Docker Desktop is always running on the Windows host before initiating Jenkins builds.
- Regularly check and re-enable WSL integration if it becomes disabled.

## Missing information

- The exact status of Docker Desktop service on Windows.
- The output of `wsl --list --verbose` to confirm WSL is properly installed and running.
