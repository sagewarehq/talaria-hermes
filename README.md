# hermes-talaria

The Hermes plugin for [Talaria](https://github.com/sagewarehq), the iPhone app for Hermes.

- **Inbox:** records every session's attention state (running, waiting on an approval or question, needs you)
  across all Hermes backends, served to the app via `/talaria inbox --json`.
- **Skills:** `/talaria:canvas` (build canvases, small web apps Talaria opens full screen) and
  `/talaria:routine` (set up routines that read well in Talaria).

Install from Talaria (Canvas or Inbox → Install), or on the server:

```bash
hermes plugins install sagewarehq/hermes-talaria --enable --yes-deps
```

Source of truth: `server/hermes-plugin-talaria` in the Talaria repo.
