@AGENTS.md

## Claude Code notes

- This code cannot be executed on the dev laptop (Raspberry Pi GPIO). Check changes with `bin/ruff check .` / `bin/ruff format --check .` and careful reading; hand deployment steps to the user instead of trying to run the server.
- Do not commit or push unless asked. The Pi pulls from `master`.
- Changing CORS origins, nginx or MediaMTX config means the user must also apply the config on the Pi – say so explicitly in your summary.
- Cross-repo work (API contract, CORS, socket events) must keep the frontend (`../The-Raspberry-SPY-frontend`) working; update both and note it in `BACKLOG.md` if something is left half-done.
