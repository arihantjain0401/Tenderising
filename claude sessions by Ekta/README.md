# Tenderising Claude session archive

This private repository stores redacted summaries of Claude Code sessions from terminal and VS Code.
Raw transcripts remain in `~/.claude/projects` and are never added to Git.

The exporter records the session request, final outcome, referenced or changed files, tool counts, and errors.
It removes common API keys, tokens, passwords, authorization headers, private keys, and the local home-directory path.

The macOS LaunchAgent runs `scripts/sync_claude_sessions.sh` every day at 8:00 PM in the Mac's current timezone.
It creates or updates files under `session-summaries/YYYY-MM-DD/`, commits changes, rebases on `origin/main`, and pushes.

Run manually:

```sh
./scripts/sync_claude_sessions.sh
```

Logs are written to `~/Library/Logs/claude-session-sync/`.
