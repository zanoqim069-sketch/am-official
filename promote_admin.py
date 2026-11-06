import sys
from app import db
if len(sys.argv)!=2: raise SystemExit("Uso: python promote_admin.py email@example.com")
c=db();c.execute("UPDATE users SET role='admin' WHERE email=?",(sys.argv[1].lower(),));c.commit();print("Utenti aggiornati:",c.total_changes);c.close()
