import os

ALLOWED_ORIGINS = ['https://filipwisniewski.pl', 'https://www.filipwisniewski.pl']

# Extra origins for local development, e.g. EXTRA_ALLOWED_ORIGINS=http://localhost:4200
ALLOWED_ORIGINS += [o.strip() for o in os.environ.get('EXTRA_ALLOWED_ORIGINS', '').split(',') if o.strip()]
