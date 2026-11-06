"""Run locally after you have obtained the original am.db backup.
Usage: python migrate_sqlite.py /path/to/am.db
Set DATABASE_URL in your terminal, never in source code or GitHub.
"""
import os, sqlite3, sys
from psycopg import connect
from psycopg import sql

TABLES = {
    'users': ['id','email','password','name','role'],
    'products': ['id','title','description','price','stock','image','active'],
    'tasks': ['id','title','description','reward','active'],
    'orders': ['id','user_id','product_id','quantity','unit_price','status','created_at'],
    'submissions': ['id','user_id','task_id','note','status','created_at'],
}

def main():
    if len(sys.argv)!=2: raise SystemExit('Usage: python migrate_sqlite.py /path/to/am.db')
    url=os.environ.get('DATABASE_URL')
    if not url: raise SystemExit('Set DATABASE_URL first')
    src=sqlite3.connect(f'file:{os.path.abspath(sys.argv[1])}?mode=ro',uri=True)
    src.row_factory=sqlite3.Row
    # Check target before writing: migration should only run on an empty database.
    with connect(url) as target:
        for table in TABLES:
            exists=target.execute('SELECT to_regclass(%s) AS t',(f'public.{table}',)).fetchone()[0]
            if not exists: raise SystemExit(f'Missing target table {table}. Run init_schema.py first.')
            count=target.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]
            if count: raise SystemExit(f'Target {table} has {count} rows. Refusing to overwrite or duplicate data.')
        for table, cols in TABLES.items():
            source_rows=src.execute(f'SELECT {", ".join(cols)} FROM {table} ORDER BY id').fetchall()
            statement=sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,cols)),sql.SQL(',').join(sql.Placeholder()*len(cols)))
            for row in source_rows: target.execute(statement,tuple(row[col] for col in cols))
            target.execute('SELECT setval(pg_get_serial_sequence(%s,%s), COALESCE((SELECT MAX(id) FROM '+table+'),1), (SELECT COUNT(*)>0 FROM '+table+'))',(table,'id'))
            print(f'{table}: {len(source_rows)} rows imported')
    src.close()
    print('Migration committed. Keep the original am.db backup securely.')

if __name__=='__main__': main()
