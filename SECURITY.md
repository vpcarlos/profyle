# Security policy

## Supported versions

Security fixes are released for the latest minor version of Profyle.

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately through
[GitHub security advisories](https://github.com/vpcarlos/profyle/security/advisories/new),
or by email to vpcarlos97@gmail.com. Include the affected version, a description and,
if possible, steps to reproduce.

You can expect an acknowledgement within a week. Once a fix is available we will
publish an advisory and credit you, unless you prefer to stay anonymous.

## Things to know when using Profyle

Profyle is a **development tool**. Do not enable `ProfyleMiddleware` in production.

- Traces contain source code, function arguments, return values and request data
  (method, path, headers, body up to 64 KB). They are stored locally in
  `<project>/.profyle/profile.db`, a folder that git ignores automatically.
- `Authorization`, `Cookie`, API-key and CSRF headers are stored as `[redacted]` unless
  you set `PROFYLE_CAPTURE_SECRETS=true`. Response bodies are never stored, only a
  fingerprint.
- The trace viewer (`profyle start`) listens on `127.0.0.1` by default and has no
  authentication. Do not expose it on a public interface.
- `profyle replay` and the `replay_request` MCP tool only send requests to local hosts
  unless `PROFYLE_REPLAY_ALLOW_REMOTE=true`, and only replay POST, PUT, PATCH or DELETE
  requests when explicitly allowed.
- When you use the MCP server with an AI assistant, the assistant receives trace
  digests, function sources and argument samples from your traces.
