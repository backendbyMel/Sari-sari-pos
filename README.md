# Sari-Sari Store POS

Django + DRF backend, React (Vite) frontend. Built phase by phase from the specification.

## First-time setup
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser      # this account is the OWNER
cd ..\frontend
npm install
```

## Every work session (two terminals)
| Terminal | Folder | Command |
|---|---|---|
| 1 | backend (venv active) | `python manage.py runserver` |
| 2 | frontend | `npm run dev` |

Open http://localhost:5173

## Tests
```powershell
cd backend
python manage.py test
```

## Rules to remember
- Stock changes only through Restock, Sales, and Stock Adjustments.
- Accounts and products are disabled, never deleted.
- Back up `backend/db.sqlite3` regularly (automatic backups arrive in Phase 5).
- Before real use: PostgreSQL, HTTPS, and `DJANGO_DEBUG=0` with `DJANGO_SECRET_KEY` set.