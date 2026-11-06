import os, sqlite3, secrets
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY",secrets.token_hex(32))
DB=os.environ.get("DATABASE_PATH","am.db")
def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
def init():
    c=db()
    c.executescript("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'user');
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,price REAL NOT NULL CHECK(price>=0),stock INTEGER NOT NULL DEFAULT 0 CHECK(stock>=0),image TEXT DEFAULT '',active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,reward TEXT NOT NULL DEFAULT 'Nessun compenso',active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS submissions(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,task_id INTEGER NOT NULL,note TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id),FOREIGN KEY(task_id) REFERENCES tasks(id));
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,product_id INTEGER NOT NULL,quantity INTEGER NOT NULL,unit_price REAL NOT NULL,status TEXT NOT NULL DEFAULT 'requested',created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id),FOREIGN KEY(product_id) REFERENCES products(id));""")
    if not c.execute("SELECT 1 FROM products").fetchone():
        c.executemany("INSERT INTO products(title,description,price,stock,image) VALUES(?,?,?,?,?)",[
        ("Ceramica artigianale","Un oggetto decorativo lavorato a mano, ispirato alle tradizioni italiane.",49,12,""),
        ("Borsa in pelle","Accessori artigianali dal design essenziale e materiali selezionati.",129,7,""),
        ("Candela naturale","Una creazione profumata per ambienti eleganti.",24,18,"")])
    if not c.execute("SELECT 1 FROM tasks").fetchone():
        c.executemany("INSERT INTO tasks(title,description,reward) VALUES(?,?,?)",[
        ("Recensione di prodotto","Scrivi una recensione autentica di un prodotto che hai effettivamente utilizzato.","Badge community"),
        ("Fotografia artigianale","Invia una fotografia originale di un manufatto di tua proprietà.","Riconoscimento editoriale")])
    c.commit(); c.close()
init()
def login_required(f):
    @wraps(f)
    def wrapper(*a,**kw):
        if not session.get('uid'): return redirect(url_for('login'))
        return f(*a,**kw)
    return wrapper
def admin_required(f):
    @wraps(f)
    def wrapper(*a,**kw):
        if session.get('role')!='admin': abort(403)
        return f(*a,**kw)
    return wrapper
@app.context_processor
def globals_():
    return dict(current_user=session.get('name'),is_admin=session.get('role')=='admin')
@app.route('/')
def home():
    c=db(); products=c.execute("SELECT * FROM products WHERE active=1 LIMIT 6").fetchall(); tasks=c.execute("SELECT * FROM tasks WHERE active=1 LIMIT 3").fetchall();c.close()
    return render_template('home.html',products=products,tasks=tasks)
@app.route('/products')
def products():
    c=db();rows=c.execute("SELECT * FROM products WHERE active=1 ORDER BY id DESC").fetchall();c.close()
    return render_template('products.html',products=rows)
@app.route('/tasks')
def tasks():
    c=db();rows=c.execute("SELECT * FROM tasks WHERE active=1 ORDER BY id DESC").fetchall();c.close()
    return render_template('tasks.html',tasks=rows)
@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); name=request.form.get('name','').strip();password=request.form.get('password','')
        if not name or '@' not in email or len(password)<10: flash('Inserisci dati validi e una password di almeno 10 caratteri.');return redirect(url_for('register'))
        c=db()
        try:
            c.execute("INSERT INTO users(email,password,name) VALUES(?,?,?)",(email,generate_password_hash(password),name));c.commit()
        except sqlite3.IntegrityError: flash('Email già registrata.');return redirect(url_for('register'))
        finally:c.close()
        flash('Registrazione completata. Accedi al tuo account.');return redirect(url_for('login'))
    return render_template('auth.html',mode='register')
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        c=db();u=c.execute("SELECT * FROM users WHERE email=?",(request.form.get('email','').strip().lower(),)).fetchone();c.close()
        if u and check_password_hash(u['password'],request.form.get('password','')):
            session.clear();session.update(uid=u['id'],name=u['name'],role=u['role']);return redirect(url_for('admin') if u['role']=='admin' else url_for('account'))
        flash('Credenziali non valide.')
    return render_template('auth.html',mode='login')
@app.route('/logout',methods=['POST'])
@login_required
def logout(): session.clear();return redirect(url_for('home'))
@app.route('/account')
@login_required
def account():
    c=db();orders=c.execute("SELECT o.*,p.title FROM orders o JOIN products p ON p.id=o.product_id WHERE o.user_id=? ORDER BY o.id DESC",(session['uid'],)).fetchall()
    subs=c.execute("SELECT s.*,t.title FROM submissions s JOIN tasks t ON t.id=s.task_id WHERE s.user_id=? ORDER BY s.id DESC",(session['uid'],)).fetchall();c.close()
    return render_template('account.html',orders=orders,subs=subs)
@app.route('/orders/create/<int:pid>',methods=['POST'])
@login_required
def order_create(pid):
    c=db();p=c.execute("SELECT * FROM products WHERE id=? AND active=1",(pid,)).fetchone()
    if not p or p['stock']<1: c.close();abort(404)
    c.execute("INSERT INTO orders(user_id,product_id,quantity,unit_price,created_at) VALUES(?,?,?,?,?)",(session['uid'],pid,1,p['price'],datetime.utcnow().isoformat()))
    c.commit();c.close();flash('Richiesta d’ordine registrata. Nessun pagamento è stato addebitato.');return redirect(url_for('account'))
@app.route('/tasks/submit/<int:tid>',methods=['POST'])
@login_required
def task_submit(tid):
    note=request.form.get('note','').strip()
    if len(note)<10 or len(note)>2000: flash('Inserisci una descrizione tra 10 e 2000 caratteri.');return redirect(url_for('tasks'))
    c=db();t=c.execute("SELECT id FROM tasks WHERE id=? AND active=1",(tid,)).fetchone()
    if not t:c.close();abort(404)
    c.execute("INSERT INTO submissions(user_id,task_id,note,created_at) VALUES(?,?,?,?)",(session['uid'],tid,note,datetime.utcnow().isoformat()));c.commit();c.close()
    flash('Attività inviata per revisione.');return redirect(url_for('account'))
@app.route('/admin')
@admin_required
def admin():
    c=db()
    users=c.execute("SELECT id,email,name,role FROM users ORDER BY id DESC").fetchall()
    products=c.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    tasks=c.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    orders=c.execute("SELECT o.*,u.email,p.title FROM orders o JOIN users u ON u.id=o.user_id JOIN products p ON p.id=o.product_id ORDER BY o.id DESC").fetchall()
    subs=c.execute("SELECT s.*,u.email,t.title FROM submissions s JOIN users u ON u.id=s.user_id JOIN tasks t ON t.id=s.task_id ORDER BY s.id DESC").fetchall()
    c.close();return render_template('admin.html',users=users,products=products,tasks=tasks,orders=orders,subs=subs)
@app.route('/admin/products',methods=['POST'])
@admin_required
def add_product():
    try:price=float(request.form['price']);stock=int(request.form['stock'])
    except(ValueError,KeyError):abort(400)
    if price<0 or stock<0:abort(400)
    c=db();c.execute("INSERT INTO products(title,description,price,stock) VALUES(?,?,?,?)",(request.form['title'][:150],request.form['description'][:2000],price,stock));c.commit();c.close();return redirect(url_for('admin'))
@app.route('/admin/tasks',methods=['POST'])
@admin_required
def add_task():
    c=db();c.execute("INSERT INTO tasks(title,description,reward) VALUES(?,?,?)",(request.form['title'][:150],request.form['description'][:2000],request.form['reward'][:100]));c.commit();c.close();return redirect(url_for('admin'))
@app.route('/admin/submissions/<int:sid>',methods=['POST'])
@admin_required
def review(sid):
    status=request.form.get('status')
    if status not in ('approved','rejected'):abort(400)
    c=db();c.execute("UPDATE submissions SET status=? WHERE id=?",(status,sid));c.commit();c.close();return redirect(url_for('admin'))
@app.route('/admin/orders/<int:oid>',methods=['POST'])
@admin_required
def order_status(oid):
    status=request.form.get('status')
    if status not in ('requested','confirmed','fulfilled','cancelled'):abort(400)
    c=db();c.execute("UPDATE orders SET status=? WHERE id=?",(status,oid));c.commit();c.close();return redirect(url_for('admin'))
@app.route('/health')
def health():return {'status':'ok'}
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))
