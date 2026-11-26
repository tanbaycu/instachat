# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.0.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in **InstaChat** (e.g., credential exposure, unsafe deserialization, XSS in the telemetry dashboard, or proxy credential leakage), please do **not** open a public issue with exploit details.

1. Open a private security advisory via GitHub Security Advisories on [`tanbaycu/instachat`](https://github.com/tanbaycu/instachat/security/advisories/new).
2. Include steps to reproduce, affected files, and any suggested mitigation.

## Operational Security Guidelines

- Never commit `.env`, `data/sessions/`, `session.key`, or proxy credential files to version control.
- The local telemetry dashboard binds to `127.0.0.1` by default; place it behind an authenticated reverse proxy if exposing remotely.
- Session cookies and stored account passwords use Fernet symmetric encryption (`data/sessions/session.key`) and JSON serialization (no `pickle`).
