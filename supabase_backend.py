"""Per-session Supabase Auth and user-scoped PostgREST storage for MailPilot Pro.

Uses only the Supabase publishable key. Every data request uses the signed-in
user's short-lived access token, so Postgres Row Level Security is enforced.
Never put a service-role or secret API key in this application.
"""
from __future__ import annotations
import csv
import io
import re
from datetime import datetime, timezone
from uuid import UUID
from urllib.parse import urlparse

import requests
from core import MAX_DAILY, today, now, valid_email


class SupabaseError(ValueError):
    """Safe, short error to show in the app without leaking API credentials."""


def _safe_request(method, url, *, headers, params=None, payload=None, timeout=20):
    try:
        r = requests.request(method, url, headers=headers, params=params, json=payload, timeout=timeout)
        if r.status_code >= 400:
            try:
                body = r.json()
                explanation = body.get('msg') or body.get('message') or body.get('error_description') or body.get('error') or ''
            except ValueError:
                explanation = ''
            # Avoid writing arbitrary server responses (which could include user data) to logs.
            brief = re.sub(r'[\r\n\t]+', ' ', str(explanation))[:180]
            raise SupabaseError(f'Supabase request failed ({r.status_code}). {brief}')
        return r.json() if r.content else None
    except requests.RequestException as exc:
        raise SupabaseError('Could not contact Supabase. Check your connection or try again.') from exc


class SupabaseAuth:
    def __init__(self, url, publishable_key):
        url = (url or '').rstrip('/')
        parts = urlparse(url)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
            raise ValueError('SUPABASE_URL must be a valid HTTPS project URL.')
        if not publishable_key:
            raise ValueError('SUPABASE_PUBLISHABLE_KEY is missing in Streamlit Secrets.')
        self.url = url
        self.key = publishable_key

    def _headers(self, jwt=None):
        headers={'apikey':self.key,'Content-Type':'application/json'}
        if jwt:
            headers['Authorization']=f'Bearer {jwt}'
        return headers

    def signup(self, name, email, password, redirect_to=None):
        name=(name or '').strip()
        email=(email or '').strip().lower()
        if not (2 <= len(name) <= 100):
            raise ValueError('Enter a name between 2 and 100 characters.')
        if not valid_email(email):
            raise ValueError('Enter a valid email address.')
        if len(password or '') < 12:
            raise ValueError('Use at least 12 characters for your password.')
        data={'email':email, 'password':password, 'data':{'display_name':name}}
        if redirect_to: data['email_redirect_to']=redirect_to
        return _safe_request('POST',f'{self.url}/auth/v1/signup',headers=self._headers(),payload=data)

    def login(self,email,password):
        email=(email or '').strip().lower()
        return _safe_request('POST',f'{self.url}/auth/v1/token',headers=self._headers(),
                             params={'grant_type':'password'},payload={'email':email,'password':password})

    def validate(self, tokens):
        """Verify identity against Auth server, refresh expired access token once."""
        if not tokens or not tokens.get('access_token'):
            raise SupabaseError('Please sign in again.')
        try:
            verified=_safe_request('GET',f'{self.url}/auth/v1/user',
                                   headers=self._headers(tokens['access_token']))
            return verified, tokens
        except SupabaseError as exc:
            # Refresh on 401; invalid/expired refresh tokens fail closed.
            if '(401)' not in str(exc) or not tokens.get('refresh_token'):
                raise
        session=_safe_request('POST',f'{self.url}/auth/v1/token',
                              headers=self._headers(),params={'grant_type':'refresh_token'},
                              payload={'refresh_token':tokens['refresh_token']})
        newtokens={'access_token':session['access_token'],
                   'refresh_token':session['refresh_token']}
        verified=_safe_request('GET',f'{self.url}/auth/v1/user',
                               headers=self._headers(newtokens['access_token']))
        return verified,newtokens

    def recover(self,email):
        email=(email or '').strip().lower()
        if not valid_email(email): raise ValueError('Enter a valid email address.')
        _safe_request('POST',f'{self.url}/auth/v1/recover',headers=self._headers(),payload={'email':email})


class SupabaseStore:
    """Matches the small subset of core.Store methods used by the Streamlit UI."""
    def __init__(self, auth:SupabaseAuth, access_token, user_id):
        self.auth=auth
        self.access_token=access_token
        try:
            self.user_id=str(UUID(str(user_id)))
        except (ValueError,TypeError,AttributeError) as exc:
            raise SupabaseError('Your account ID is invalid. Please sign in again.') from exc

    def _call(self,method,table,params=None,payload=None,prefer='return=representation'):
        allowed={'profiles','contacts','campaigns','email_designs','events','deliveries','app_settings','smtp_test_attempts'}
        if table not in allowed: raise ValueError('Unsupported table.')
        options={}
        if method in ('GET','PATCH','DELETE'):
            options['user_id']=f'eq.{self.user_id}'
        if params: options.update(params)
        headers=self.auth._headers(self.access_token)
        headers['Prefer']=prefer
        data=_safe_request(method,f'{self.auth.url}/rest/v1/{table}',headers=headers,
                           params=options,payload=payload)
        return data or []

    def _list(self,table,params=None):
        return self._call('GET',table,params={'select':'*','limit':'1000',**(params or {})})

    def ensure_profile(self,name=''):
        row=self._list('profiles',{'limit':'1'})
        if not row:
            self._call('POST','profiles',payload={
                'user_id':self.user_id,'display_name':(name or '')[:100]})

    def get_setting(self,key,default=None):
        data=self._list('app_settings',{'setting_key':f'eq.{key}','limit':'1'})
        return data[0]['value_json'] if data else default

    def set_setting(self,key,value):
        if key not in {'email_designs','portfolio_seeded','smtp_preferences'}:
            raise ValueError('Unsupported setting key.')
        if key=='smtp_preferences':
            safe={k:v for k,v in (value or {}).items()
                  if k in {'provider','username','sender','display_name','reply_to','unsubscribe'}}
            value=safe
        self._call('POST','app_settings',{'on_conflict':'user_id,setting_key'},
                   {'user_id':self.user_id,'setting_key':key,'value_json':value},
                   'resolution=merge-duplicates,return=minimal')

    def contacts(self):
        return self._list('contacts',{'order':'created_at.desc,email.asc'})

    def campaigns(self):
        return self._list('campaigns',{'order':'id.desc'})

    def events(self):
        rows=self._list('events',{'order':'id.desc'})
        titles={x['id']:x['title'] for x in self.campaigns()}
        return [{**x,'campaign':titles.get(x['campaign_id'],'Unknown campaign')} for x in rows]

    def deliveries(self):
        rows=self._list('deliveries',{'order':'id.desc'})
        titles={x['id']:x['title'] for x in self.campaigns()}
        return [{**x,'campaign':titles.get(x['campaign_id'],'Unknown campaign')} for x in rows]

    def add_contact(self,name,email,company='',segment='General',subscribed=False):
        name=(name or '').strip(); email=(email or '').strip().lower()
        if not name or not valid_email(email):
            raise ValueError('Enter a name and valid email address.')
        return self._call('POST','contacts',payload={
            'user_id':self.user_id,'email':email,'name':name,'company':(company or '').strip(),
            'segment':(segment or '').strip() or 'General','subscribed':bool(subscribed)})

    def update_contact(self,email,subscribed=None,segment=None):
        changes={}
        if subscribed is not None: changes['subscribed']=bool(subscribed)
        if segment is not None: changes['segment']=(segment or '').strip() or 'General'
        if changes:
            self._call('PATCH','contacts',{'email':f'eq.{email.strip().lower()}'},changes,'return=minimal')

    def delete_contact(self,email):
        self._call('DELETE','contacts',{'email':f'eq.{email.strip().lower()}'},prefer='return=minimal')

    def import_csv(self,data):
        if len(data)>2_000_000: raise ValueError('CSV must be smaller than 2 MB.')
        reader=csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
        if not reader.fieldnames or not {'name','email','subscribed'}.issubset(reader.fieldnames):
            raise ValueError('CSV must include name,email,subscribed columns.')
        count=skipped=0
        for row in reader:
            try:
                self.add_contact(row.get('name',''),row.get('email',''),row.get('company',''),
                                 row.get('segment','General'),
                                 str(row.get('subscribed','')).strip().lower() in ('1','true','yes','y'))
                count+=1
            except (SupabaseError,ValueError): skipped+=1
        return count,skipped

    def add_campaign(self,title,subject,body):
        if not all(str(x).strip() for x in (title,subject,body)):
            raise ValueError('Campaign name, subject, and body are required.')
        rows=self._call('POST','campaigns',payload={'user_id':self.user_id,'title':title.strip(),
                                  'subject':subject.strip(),'body':body.strip()})
        return rows[0]['id']

    def update_campaign(self,cid,title,subject,body):
        if not all(str(x).strip() for x in (title,subject,body)):
            raise ValueError('Campaign name, subject, and body are required.')
        self._call('PATCH','campaigns',{'id':f'eq.{int(cid)}'},
                   {'title':title.strip(),'subject':subject.strip(),'body':body.strip()},
                   prefer='return=minimal')

    def delete_campaign(self,cid):
        self._call('DELETE','campaigns',{'id':f'eq.{int(cid)}'},prefer='return=minimal')

    def preview(self,cid,segment='All'):
        prior={e['email'] for e in self._list('events',{'campaign_id':f'eq.{int(cid)}'})}
        return [c for c in reversed(self.contacts()) if c['subscribed'] and c['email'] not in prior
                and (segment=='All' or c['segment']==segment)]

    def daily_used(self,day=None):
        return len(self._list('events',{'day':f'eq.{day or today()}'}))

    def simulate(self,cid,segment='All',day=None):
        day=day or today()
        if int(cid) not in {x['id'] for x in self.campaigns()}:
            raise ValueError('Campaign not found.')
        remaining=max(0,MAX_DAILY-self.daily_used(day))
        if not remaining: return []
        people=self.preview(cid,segment)[:remaining]
        for p in people:
            self._call('POST','events',payload={'user_id':self.user_id,'campaign_id':int(cid),
                                               'email':p['email'],'recipient_name':p['name'],
                                               'simulated_at':now(),'day':day},prefer='return=minimal')
        if people:
            self._call('PATCH','campaigns',{'id':f'eq.{int(cid)}'},
                       {'status':'Simulated'},prefer='return=minimal')
        return [{'email':p['email'],'name':p['name']} for p in people]

    def smtp_tests_used(self,day=None):
        return len(self._list('smtp_test_attempts',{'day':f'eq.{day or today()}'}))

    def reserve_smtp_test(self,recipient,day=None):
        if not valid_email(recipient) or recipient.lower().endswith(('@example.com','@example.org','@example.net')):
            raise ValueError('Enter your real verified sender email for testing.')
        day=day or today()
        if self.smtp_tests_used(day)>=3:
            raise ValueError('Daily test limit reached.')
        rows=self._call('POST','smtp_test_attempts',payload={
             'user_id':self.user_id,'day':day,'recipient':recipient,
             'status':'reserved','created_at':now()})
        return rows[0]['id']

    def finish_smtp_test(self,test_id,success,error=''):
        self._call('PATCH','smtp_test_attempts',{'id':f'eq.{int(test_id)}','status':'eq.reserved'},
                   {'status':'sent' if success else 'failed','error':str(error)[:200]},prefer='return=minimal')

    def live_used(self,day=None):
        return len(self._list('deliveries',{'day':f'eq.{day or today()}'}))

    def reserve_live(self,cid,email,day=None):
        day=day or today(); email=(email or '').strip().lower()
        if not valid_email(email) or email.endswith(('@example.com','@example.org','@example.net')):
            raise ValueError('Fictional or invalid recipients cannot receive real email.')
        if self.live_used(day)>=MAX_DAILY:
            raise ValueError('Daily live sending limit reached.')
        people=[c for c in self.contacts() if c['email']==email and c['subscribed']]
        if not people: raise ValueError('Recipient is missing or not subscribed.')
        if self._list('deliveries',{'campaign_id':f'eq.{int(cid)}','email':f'eq.{email}' }):
            raise ValueError('This recipient was already attempted for the campaign.')
        self._call('POST','deliveries',payload={'user_id':self.user_id,'campaign_id':int(cid),
                                               'email':email,'recipient_name':people[0]['name'],
                                               'status':'reserved','day':day,'created_at':now()},
                   prefer='return=minimal')
        return {k:people[0][k] for k in ('email','name','company','segment')}

    def finish_live(self,cid,email,success,error=''):
        self._call('PATCH','deliveries',{'campaign_id':f'eq.{int(cid)}','email':f'eq.{email}',
                                       'status':'eq.reserved'},
                   {'status':'sent' if success else 'failed','error':str(error)[:200]},
                   prefer='return=minimal')

    def seed_demo(self):
        raise ValueError('Demo contacts are not added to permanent user databases.')
