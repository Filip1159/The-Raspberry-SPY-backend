import os

from app.config import HARDWARE_MODE

ALLOWED_ORIGINS = ['https://filipwisniewski.pl', 'https://www.filipwisniewski.pl']

# The local Angular dev server talks to the simulated backend
if HARDWARE_MODE == 'fake':
    ALLOWED_ORIGINS += ['http://localhost:4200', 'http://127.0.0.1:4200']

# Extra origins for local development, e.g. EXTRA_ALLOWED_ORIGINS=http://localhost:4200
ALLOWED_ORIGINS += [o.strip() for o in os.environ.get('EXTRA_ALLOWED_ORIGINS', '').split(',') if o.strip()]
