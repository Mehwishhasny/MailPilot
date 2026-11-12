"""MailPilot Pro core: SQLite demo/recipient storage and optional private SMTP tools."""
from __future__ import annotations
import csv
from contextlib import contextmanager
import io
import json
import re
import sqlite3
import smtplib
import ssl
from email.message import EmailMessage
from html import escape
from datetime import datetime, timezone
from pathlib import Path

MAX_DAILY = 10
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today():
    return datetime.now(timezone.utc).date().isoformat()


def valid_email(value):
    return bool(EMAIL_RE.fullmatch(value.strip())) and len(value.strip()) <= 254


class Store:
    def __init__(self, path="mailpilot.db"):
        self.path = str(path)
        self.init()

    @contextmanager
    def db(self):
        """Open a transaction and close the SQLite connection deterministically."""
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init(self):
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS contacts(
              email TEXT PRIMARY KEY COLLATE NOCASE,
              name TEXT NOT NULL,
              company TEXT NOT NULL DEFAULT '',
              segment TEXT NOT NULL DEFAULT 'General',
              subscribed INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS campaigns(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL, subject TEXT NOT NULL,
              body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Draft',
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
              email TEXT NOT NULL,
              recipient_name TEXT NOT NULL,
              simulated_at TEXT NOT NULL,
              day TEXT NOT NULL,
              UNIQUE(campaign_id,email)
            );
            CREATE INDEX IF NOT EXISTS idx_events_day ON events(day);
            CREATE TABLE IF NOT EXISTS deliveries(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
              email TEXT NOT NULL, recipient_name TEXT NOT NULL,
              status TEXT NOT NULL CHECK(status IN ('reserved','sent','failed')),
              created_at TEXT NOT NULL, day TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
              UNIQUE(campaign_id,email)
            );
            CREATE INDEX IF NOT EXISTS idx_deliveries_day ON deliveries(day);
            CREATE TABLE IF NOT EXISTS smtp_test_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                recipient TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('reserved','sent','failed')),
                created_at TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_smtp_test_day ON smtp_test_attempts(day);
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            );
            """)

    def query(self, sql, args=()):
        with self.db() as db:
            return [dict(r) for r in db.execute(sql, args).fetchall()]

    def get_setting(self, key, default=None):
        with self.db() as db:
            row=db.execute('SELECT value_json FROM app_settings WHERE key=?',(key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row['value_json'])
        except (TypeError, ValueError):
            return default

    def set_setting(self, key, value):
        # Only non-secret app preferences and email designs belong here.
        serialized=json.dumps(value,ensure_ascii=False)
        with self.db() as db:
            db.execute("""INSERT INTO app_settings(key,value_json) VALUES(?,?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json""",(key,serialized))

    def contacts(self):
        return self.query("SELECT * FROM contacts ORDER BY created_at DESC,email")

    def campaigns(self):
        return self.query("SELECT * FROM campaigns ORDER BY id DESC")

    def events(self):
        return self.query("SELECT e.*,c.title AS campaign FROM events e JOIN campaigns c ON c.id=e.campaign_id ORDER BY e.id DESC")

    def add_contact(self, name, email, company="", segment="General", subscribed=False):
        email = email.strip().lower()
        if not name.strip() or not valid_email(email):
            raise ValueError("Enter a name and valid email address.")
        with self.db() as db:
            db.execute("INSERT INTO contacts VALUES(?,?,?,?,?,?)", (email,name.strip(),company.strip(),segment.strip() or 'General',int(bool(subscribed)),now()))

    def update_contact(self, email, subscribed=None, segment=None):
        with self.db() as db:
            if subscribed is not None:
                db.execute("UPDATE contacts SET subscribed=? WHERE email=?",(int(bool(subscribed)),email))
            if segment is not None:
                db.execute("UPDATE contacts SET segment=? WHERE email=?",(segment.strip() or 'General',email))

    def delete_contact(self,email):
        with self.db() as db:
            db.execute("DELETE FROM contacts WHERE email=?",(email,))

    def import_csv(self, data):
        if len(data)>2_000_000:
            raise ValueError("CSV must be smaller than 2 MB.")
        reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
        if not reader.fieldnames or not {'name','email','subscribed'}.issubset(set(reader.fieldnames)):
            raise ValueError("CSV needs name,email,subscribed columns.")
        count=skipped=0
        for row in reader:
            if not row.get('name') or not valid_email(row.get('email') or ''):
                skipped+=1;continue
            opt=str(row.get('subscribed','')).strip().lower() in ('1','true','yes','y')
            try:
                self.add_contact(row['name'],row['email'],row.get('company',''),row.get('segment','General'),opt)
                count+=1
            except sqlite3.IntegrityError:
                skipped+=1
        return count,skipped

    def add_campaign(self,title,subject,body):
        if not all(x.strip() for x in (title,subject,body)):
            raise ValueError("Campaign title, subject and message are required.")
        with self.db() as db:
            cur=db.execute("INSERT INTO campaigns(title,subject,body,created_at) VALUES(?,?,?,?)",(title.strip(),subject.strip(),body.strip(),now()))
            return cur.lastrowid

    def update_campaign(self,cid,title,subject,body):
        if not all(x.strip() for x in (title,subject,body)):
            raise ValueError("All campaign fields are required.")
        with self.db() as db:
            db.execute("UPDATE campaigns SET title=?,subject=?,body=? WHERE id=?",(title.strip(),subject.strip(),body.strip(),cid))

    def delete_campaign(self,cid):
        with self.db() as db:
            db.execute("DELETE FROM campaigns WHERE id=?",(cid,))

    def preview(self,cid,segment='All'):
        sql="""SELECT c.* FROM contacts c WHERE c.subscribed=1 AND NOT EXISTS
        (SELECT 1 FROM events e WHERE e.campaign_id=? AND e.email=c.email)"""
        args=[cid]
        if segment!='All':
            sql+=' AND c.segment=?';args.append(segment)
        sql+=' ORDER BY c.created_at,c.email'
        return self.query(sql,args)

    def deliveries(self):
        return self.query("SELECT d.*,c.title AS campaign FROM deliveries d JOIN campaigns c ON c.id=d.campaign_id ORDER BY d.id DESC")

    def smtp_tests_used(self, day=None):
        # Count every attempted test, including failures, to prevent unlimited sends.
        return self.query("SELECT COUNT(*) AS n FROM smtp_test_attempts WHERE day=?",
                          (day or today(),))[0]['n']

    def reserve_smtp_test(self, recipient, day=None):
        if not valid_email(recipient) or recipient.lower().endswith(('@example.com','@example.org','@example.net')):
            raise ValueError('Use your real verified sender email for the test.')
        day=day or today()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            used=db.execute('SELECT COUNT(*) FROM smtp_test_attempts WHERE day=?',(day,)).fetchone()[0]
            if used >= 3:
                raise ValueError('Daily test email limit (3) reached.')
            cur=db.execute("INSERT INTO smtp_test_attempts(day,recipient,status,created_at) VALUES(?,?,'reserved',?)",
                           (day,recipient,now()))
            return cur.lastrowid

    def finish_smtp_test(self, test_id, success, error=''):
        with self.db() as db:
            db.execute("UPDATE smtp_test_attempts SET status=?,error=? WHERE id=? AND status='reserved'",
                       ('sent' if success else 'failed',error[:250],test_id))

    def live_used(self, day=None):
        return self.query("SELECT COUNT(*) AS n FROM deliveries WHERE day=?", (day or today(),))[0]['n']

    def reserve_live(self, cid, email, day=None):
        """Reserve one recipient transactionally before sending; no retry of uncertain sends."""
        day = day or today()
        if email.lower().endswith(('@example.com','@example.org','@example.net')):
            raise ValueError('Fictional demo addresses cannot receive live emails.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT COUNT(*) FROM deliveries WHERE day=?", (day,)).fetchone()[0] >= MAX_DAILY:
                raise ValueError('Daily live limit of 10 reached.')
            person = db.execute("""SELECT c.email,c.name,c.company,c.segment FROM contacts c
                WHERE c.email=? AND c.subscribed=1 AND NOT EXISTS
                (SELECT 1 FROM deliveries d WHERE d.campaign_id=? AND d.email=c.email)""",(email,cid)).fetchone()
            if not person:
                raise ValueError('Recipient is not subscribed, was already attempted, or is missing.')
            db.execute("INSERT INTO deliveries(campaign_id,email,recipient_name,status,created_at,day) VALUES(?,?,?,'reserved',?,?)",
                       (cid,person['email'],person['name'],now(),day))
            return dict(person)

    def finish_live(self,cid,email,success,error=''):
        with self.db() as db:
            db.execute("UPDATE deliveries SET status=?,error=? WHERE campaign_id=? AND email=? AND status='reserved'",
                       ('sent' if success else 'failed',error[:250],cid,email))

    def seed_demo(self):
        """Fictional example.com addresses; never eligible for live delivery."""
        samples=[('Alex Morgan','Northstar Labs','Technology'),('Samira Khan','Bluebird Studio','Creative'),
                 ('Daniel Lee','Summit Partners','Consulting'),('Priya Shah','Willow Group','Retail'),
                 ('Omar Hassan','Atlas Ventures','Technology'),('Emma Wilson','Harbor Co','Retail'),
                 ('Noah Chen','Brightpath','Consulting'),('Sara Ali','Cedar Digital','Creative'),
                 ('Liam Patel','Nimbus Works','Technology'),('Maya Brown','Horizon Co','Retail'),
                 ('Zara Ahmed','Orion Studio','Creative'),('Ethan Brooks','Vertex Labs','Technology'),
                 ('Nina Kapoor','Lighthouse Co','Consulting'),('Leo Garcia','Cloudline','Technology'),
                 ('Ava Robinson','Maple Media','Creative'),('Amir Yusuf','Coastal Group','Retail'),
                 ('Ella White','Fable Design','Creative'),('Rayan Malik','Evergreen','Consulting'),
                 ('Sofia Martin','Nova Digital','Technology'),('Adam Clark','Bridgewell','Retail')]
        count=0
        for i,(name,company,segment) in enumerate(samples,1):
            try:
                self.add_contact(name,f'demo{i:02d}@example.com',company,segment,True)
                count+=1
            except sqlite3.IntegrityError: pass
        return count

    def daily_used(self,day=None):
        return self.query("SELECT COUNT(*) AS n FROM events WHERE day=?",(day or today(),))[0]['n']

    def simulate(self,cid,segment='All',day=None):
        """Atomically record at most 10 *simulated* emails per UTC day, never send."""
        day=day or today()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            campaign=db.execute('SELECT id FROM campaigns WHERE id=?',(cid,)).fetchone()
            if campaign is None:
                raise ValueError('Campaign not found.')
            used=db.execute('SELECT COUNT(*) FROM events WHERE day=?',(day,)).fetchone()[0]
            remaining=max(0,MAX_DAILY-used)
            if remaining==0:
                return []
            sql="""SELECT c.email,c.name FROM contacts c WHERE c.subscribed=1
              AND NOT EXISTS (SELECT 1 FROM events e WHERE e.campaign_id=? AND e.email=c.email)"""
            args=[cid]
            if segment!='All':
                sql+=' AND c.segment=?';args.append(segment)
            sql+=' ORDER BY c.created_at,c.email LIMIT ?';args.append(remaining)
            people=db.execute(sql,args).fetchall()
            stamp=now()
            for person in people:
                db.execute('INSERT INTO events(campaign_id,email,recipient_name,simulated_at,day) VALUES(?,?,?,?,?)',
                           (cid,person['email'],person['name'],stamp,day))
            if people:
                db.execute("UPDATE campaigns SET status='Simulated' WHERE id=?",(cid,))
            return [dict(p) for p in people]


def personalize(text, contact):
    for key in ('name','email','company'):
        text=text.replace('{'+key+'}',str(contact.get(key,'') or ''))
    return text


def csv_bytes(records,fields):
    output=io.StringIO()
    writer=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore')
    writer.writeheader();writer.writerows(records)
    return output.getvalue().encode('utf-8-sig')


def compose_message(sender,recipient,subject,body,reply_to='',unsubscribe=''):
    """Text + safe HTML alternative; avoid treating user text as HTML."""
    msg=EmailMessage()
    msg['From']=sender
    msg['To']=recipient
    msg['Subject']=subject
    if reply_to: msg['Reply-To']=reply_to
    footer='\n\nTo unsubscribe, reply with UNSUBSCRIBE.'
    if unsubscribe: footer='\n\nUnsubscribe: '+unsubscribe
    msg.set_content(body+footer)
    html='<html><body style="font-family:Arial,sans-serif;line-height:1.7;color:#24324b;max-width:620px;margin:auto;padding:28px">'+escape(body).replace('\n','<br>')+'<hr><small>'+escape(footer.strip())+'</small></body></html>'
    msg.add_alternative(html,subtype='html')
    return msg


def smtp_send(host,port,security,username,password,message,timeout=15):
    if not host.strip() or not 1<=int(port)<=65535 or not username or not password:
        raise ValueError('Complete all SMTP settings first.')
    context=ssl.create_default_context()
    if security=='SSL/TLS':
        with smtplib.SMTP_SSL(host,int(port),timeout=timeout,context=context) as client:
            client.login(username,password)
            client.send_message(message)
    elif security=='STARTTLS':
        with smtplib.SMTP(host,int(port),timeout=timeout) as client:
            client.ehlo();client.starttls(context=context);client.ehlo()
            client.login(username,password);client.send_message(message)
    else:
        raise ValueError('Encrypted SMTP is required.')
