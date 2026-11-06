@AGENTS.md

## Claude Code notes

- The app runs on any machine in fake mode: verify changes with `python -m pytest` and `ruff check . && ruff format --check .` (create a venv from `requirements-dev.txt` outside the repo or in `.venv`). Code that touches real hardware lives only in `app/hardware/raspberry.py` and cannot be tested here – say so and hand deployment steps to the user.
- Do not commit or push unless asked. The Pi pulls from `master`.
- Changing CORS origins, nginx or MediaMTX config means the user must also apply the config on the Pi – say so explicitly in your summary.
- Cross-repo work (API contract, CORS, socket events) must keep the frontend (`../The-Raspberry-SPY-frontend`) working, including its mock server (`mock-server/server.js`), which mirrors this API; update both and note it in `BACKLOG.md` if something is left half-done.
- API changes must be made in **both** the FastAPI (`app/api/`, the default) and the Flask fallback implementation until the Flask code is deleted (`app/controller/` + `app/server.py` and `app/api/`); shared validation goes into `app/validation.py`. See the FastAPI section in `AGENTS.md`.
