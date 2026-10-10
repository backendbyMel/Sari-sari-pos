# Sari-Sari Store POS

Django + DRF backend, React (Vite) frontend. Built phase by phase from the specification.

## First-time setup
1. Install PostgreSQL. In psql create the user and database:
   `CREATE ROLE pos_user WITH LOGIN PASSWORD '...';  CREATE DATABASE pos_db OWNER pos_user ENCODING 'UTF8' TEMPLATE template0;`
2. `cd backend`, copy `.env.example` to `.env`, and fill in the password.
```powershell
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
## Integrity check (run after restoring a backup, or any time you doubt the numbers)
```powershell
cd backend
python manage.py check_integrity
```
It only reads. `OK` means stock, sales, receipts and shift cash all add up.

## Rules to remember
- Stock changes only through Restock, Sales, and Stock Adjustments.
- Accounts and products are disabled, never deleted.
- Back up `backend/db.sqlite3` regularly (automatic backups arrive in Phase 5).
- Before real use: PostgreSQL, HTTPS, and `DJANGO_DEBUG=0` with `DJANGO_SECRET_KEY` set.
- Money moves only through recorded entries (sales, payments, loads, GCash, pay-outs, wallet entries).
  Nothing is edited or deleted. Mistakes are corrected by a new, owner-approved record.
- A new API route is locked to the owner by default. To let cashiers use it, add it to
  `CASHIER_OK` in `backend/config/test_route_security.py` ON PURPOSE.
- Run `python manage.py test` and `python manage.py check_integrity` before and after any change to money code.