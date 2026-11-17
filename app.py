"""MailPilot Pro — portfolio dashboard with simulation and optional confirmed SMTP."""
from pathlib import Path
from datetime import datetime, timezone
from html import escape as safe_html
from io import BytesIO
from email.utils import formataddr
import base64
import math
from PIL import Image, ImageDraw
from urllib.parse import urlparse
import json
import os
from supabase_backend import SupabaseAuth, SupabaseStore, SupabaseError
import re
import streamlit.components.v1 as components
import sqlite3
import tempfile
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from core import Store, MAX_DAILY, today, personalize, csv_bytes, compose_message, valid_email
from smtp_providers import PROVIDERS, provider_config, validate_sender, test_smtp_login, send_via_user_smtp, friendly_error

st.set_page_config(page_title='MailPilot Pro | Email Automation',page_icon="mailpilot-icon.png",layout='wide',initial_sidebar_state='auto')
st.info("MAILPILOT NEW VERSION - 17 NOV 2026")
# Hide Streamlit's built-in developer toolbar (including the Deploy button) locally.
st.set_option('client.toolbarMode', 'viewer')
# Registered users use Supabase PostgreSQL; only guest demo writes a temporary SQLite file.

st.markdown('''<style>
/* MailPilot Pro — Sage & Lilac Edition: no red/pink/coral */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');
:root{
 --ink:#25283A;--muted:#66716C;--sage:#3C9E85;--mint:#E2F4EB;
 --lilac:#796AC2;--lavender:#EDE9FC;--gold:#C9A85A;--paper:#FAFBF7;
 --line:#E5E8E6;
}
html,body,.stApp{font-family:'DM Sans',system-ui,sans-serif;color:var(--ink)}
.stApp{
 background-color:#FAFBF7;
 background-image:
   radial-gradient(ellipse at 93% 8%,rgba(133,198,168,.19),transparent 33%),
   radial-gradient(ellipse at 8% 75%,rgba(157,145,214,.14),transparent 29%),
   radial-gradient(circle,rgba(105,140,123,.065) .8px,transparent .9px),
   linear-gradient(160deg,#FBFCF9 0%,#F5F7F3 56%,#F6F4FD 100%);
 background-size:auto,auto,27px 27px,auto;
}
/* Hide Streamlit toolbar */
[data-testid="stToolbar"] {
    display: none !important;
}

[data-testid="stDecoration"] {
    display: none !important;
}
.main,section.main,[data-testid="stAppViewContainer"]{min-width:0}
/* Streamlit's fixed header/toolbar is around 3.5rem high. Reserve sufficient vertical
   space so the first ribbon, title, and overview hero never sit underneath it. */
.block-container,[data-testid="stMainBlockContainer"]{
 box-sizing:border-box;
 max-width:1420px;
 width:100%;
 padding:5.75rem clamp(1.1rem,2.6vw,2.9rem) 4.3rem !important;
 margin-inline:auto;
}
/* Premium lavender logout button */
[data-testid="stSidebar"] .st-key-mailpilot_logout button {
    background: #796AC2 !important;
    color: white !important;
    border-radius: 12px !important;
    border: 1px solid #988BE0 !important;
    font-weight: 700 !important;
}

[data-testid="stSidebar"] .st-key-mailpilot_logout button:hover {
    background: #6253A8 !important;
    color: white !important;
}
[data-testid="stSidebarUserContent"]{padding-top:2.8rem!important;padding-bottom:2.2rem!important}
/* Keep mobile sidebar toggle and page titles above content rather than overlaying them. */
[data-testid="stHeader"]{background:rgba(250,251,247,.94);backdrop-filter:blur(8px)}
h1,h2,h3,h4,h5{font-family:Manrope,system-ui,sans-serif;letter-spacing:-.03em;color:#292C3A}
h1{font-size:clamp(1.55rem,2.7vw,2.12rem)!important;font-weight:800!important;line-height:1.26!important}
h3{font-size:1.13rem!important}
p,label{overflow-wrap:break-word}
/* Calm charcoal sidebar with subtle mint and lilac highlights. */
[data-testid="stSidebar"]{
 background:
  radial-gradient(circle at 5% 8%,rgba(151,138,214,.25),transparent 40%),
  radial-gradient(circle at 98% 88%,rgba(78,170,139,.16),transparent 35%),
  linear-gradient(157deg,#27283A 0%,#343346 48%,#283D40 100%);
 border-right:1px solid #45475A;
}
[data-testid="stSidebar"] *{color:#F3F5F1!important}
[data-testid="stSidebar"] [data-testid="stRadio"] label{padding:9px 12px;border-radius:12px;transition:background .16s}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover{background:#FFFFFF1D}
[data-testid="stSidebar"] hr{border-color:#FFFFFF24}
[data-testid="stSidebar"] [data-testid="stRadio"] [aria-checked="true"]{accent-color:#9AD8BF}
/* Neutral white cards; lilac and sage accent line. */
[data-testid="stMetric"]{
 background:linear-gradient(123deg,#FFFFFF 42%,#F0F8F3 100%);
 border:1px solid #E0EBE4;border-left:4px solid #6EBA9C;
 padding:16px 17px;border-radius:17px;min-width:0;
 box-shadow:0 8px 25px rgba(35,55,49,.065);
}
[data-testid="stMetricLabel"]{color:#62716D}
[data-testid="stMetricValue"]{color:#303449;font-weight:800}
[data-testid="stMetricDelta"]{color:#287D6A}
[data-testid="stVerticalBlockBorderWrapper"]>div{border-radius:17px}
.stButton>button,.stDownloadButton>button,.stFormSubmitButton>button{
 border-radius:12px;min-height:43px;font-weight:700;
 transition:transform .13s,box-shadow .13s;
}
.stButton>button:hover,.stDownloadButton>button:hover,.stFormSubmitButton>button:hover{
 transform:translateY(-1px);box-shadow:0 8px 18px rgba(65,95,83,.16);
}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{
 background:linear-gradient(115deg,#6859AB,#368E79);border-color:#568E8B;color:#FFFFFF;
}
.stButton>button[kind="primary"]:disabled,.stFormSubmitButton>button[kind="primary"]:disabled{opacity:.54}
.stTextInput input:focus,.stTextArea textarea:focus{border-color:#796AC2;box-shadow:0 0 0 1px #796AC2}
[data-testid="stDataFrame"]{border-radius:13px;overflow:hidden;border:1px solid #E3E8E5;max-width:100%}
[data-testid="stTabs"] button{font-weight:700}
[data-testid="stTabs"] [aria-selected="true"]{color:#6757AF!important;border-color:#6757AF!important}
[data-testid="stProgress"]>div>div>div>div{background:linear-gradient(90deg,#7465B9,#55AB94,#D0B773)}
[data-testid="stAlert"]{border-radius:13px}
[data-testid="stExpander"]{border:1px solid #E1E8E2;border-radius:14px;background:#FFFFFFD7}
.stSelectbox,.stMultiSelect,.stTextInput,.stTextArea{min-width:0}
/* Decorative hero: pattern stays behind readable text, with generous top clearance. */
.hero{
 position:relative;overflow:hidden;isolation:isolate;
 background:linear-gradient(112deg,#2B3040 0%,#4D5470 46%,#388F80 100%);
 color:#FFF;padding:clamp(24px,3.4vw,38px);border-radius:22px;margin:4px 0 24px;
 box-shadow:0 15px 36px rgba(35,69,68,.18);
}
.hero::before{
 content:"";position:absolute;right:-74px;top:-132px;width:420px;height:420px;z-index:-1;
 border:2px solid #FFFFFF31;border-radius:50%;
 box-shadow:0 0 0 39px #FFFFFF11,0 0 0 80px #FFFFFF0B;
}
.hero::after{
 content:"";position:absolute;right:7%;bottom:8%;width:155px;height:95px;z-index:-1;
 background-image:radial-gradient(#FFFFFF 1.55px,transparent 2px);
 background-size:16px 16px;opacity:.31;transform:rotate(-10deg);
}
.hero h2{color:#FFFFFF;margin:0;font-size:clamp(1.4rem,2.4vw,2.05rem);line-height:1.34;position:relative}
.hero p{color:#EEF9F3;margin:12px 0 0;max-width:790px;font-size:14px;line-height:1.75;position:relative}
.tag{display:inline-block;background:linear-gradient(110deg,#E5F7EC,#EAE7FA);color:#544995;border-radius:45px;padding:7px 14px;font-size:12px;font-weight:800}
.section-note{color:#68736F;font-size:13px;margin-top:-6px;margin-bottom:10px}
.eyebrow{font-size:12px;font-weight:800;letter-spacing:.13em;color:#C8F3DE;margin-bottom:9px}
.panel{
 background:linear-gradient(148deg,#FFFFFF 45%,#F1F5F9 100%);
 border:1px solid #E4E9E4;border-radius:17px;padding:18px 20px;margin:10px 0 16px;
 box-shadow:0 8px 22px rgba(35,68,62,.055);
}
.panel h4{margin:0 0 8px;color:#414765}.panel p{color:#697770;margin:0;font-size:13px;line-height:1.65}
.small-chip{display:inline-block;background:#FFFFFF14;border:1px solid #CFEBDE55;border-radius:20px;padding:6px 12px;color:#D7F5E8!important;font-size:11px;font-weight:800;letter-spacing:.05em}
.section-ribbon{
 display:flex;align-items:center;justify-content:space-between;gap:10px;
 border-radius:14px;margin:4px 0 24px;padding:13px 16px;color:#50507D;
 background:linear-gradient(106deg,#ECEAFB 0%,#E8F5EE 65%,#FFF9E9 100%);
 border:1px solid #DDE9E4;font-size:11px;font-weight:800;letter-spacing:.08em;
}
.section-ribbon span:first-child{min-width:0;overflow-wrap:anywhere}
.ribbon-mark{width:9px;height:9px;border-radius:50%;background:#3F9F87;box-shadow:0 0 0 5px #3F9F8727;flex-shrink:0}
.smtp-note{padding:14px 17px;border:1px solid #DCEAE1;background:linear-gradient(115deg,#E9F6EE,#EEEBFB);border-radius:13px;color:#4C5C61;font-size:13px;margin:10px 0 17px}
/* Responsive stacking and header safe space; do not hide controls or cut titles. */
@media (max-width:1100px){
 .block-container,[data-testid="stMainBlockContainer"]{padding:5.6rem 1.25rem 3.2rem!important}
 [data-testid="stHorizontalBlock"]{min-width:0;gap:.8rem}
 [data-testid="column"],[data-testid="stColumn"]{min-width:0}
}
@media (max-width:760px){
 .block-container,[data-testid="stMainBlockContainer"]{
   padding:5.35rem .88rem 2.9rem!important;
   max-width:100%;
 }
 [data-testid="stSidebarUserContent"]{padding-top:3.1rem!important}
 [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;align-items:stretch;gap:.7rem!important}
 [data-testid="column"],[data-testid="stColumn"]{flex:1 1 100%!important;width:100%!important;min-width:0!important}
 [data-testid="stMetric"]{padding:13px 15px;border-radius:14px}
 .hero{padding:24px 19px;border-radius:18px;margin-top:0;margin-bottom:17px}
 .hero h2{font-size:1.43rem!important}
 .hero::before{width:245px;height:245px;right:-133px;top:-65px}
 .hero::after{display:none}
 .panel{padding:15px 16px}
 .section-ribbon{padding:12px 13px;font-size:10px;letter-spacing:.04em;margin-top:0}
 [data-testid="stDataFrame"],.stPlotlyChart{width:100%!important;max-width:100%;overflow-x:auto}
 .js-plotly-plot,.plot-container{max-width:100%!important}
 .stButton>button,.stDownloadButton>button,.stFormSubmitButton>button{width:100%;white-space:normal}
}
@media (max-width:390px){
 .block-container,[data-testid="stMainBlockContainer"]{padding:5.2rem .7rem 2.5rem!important}
 .hero h2{font-size:1.26rem!important}
 .section-ribbon{font-size:9px}
}
@media (prefers-reduced-motion:reduce){
 .stButton>button,.stDownloadButton>button,.stFormSubmitButton>button{transition:none!important;transform:none!important}
}

/* MailPilot Pro — Mobile login improvements */
@media (max-width: 760px) {

  .block-container,
  [data-testid="stMainBlockContainer"] {
    padding-top: 4.5rem !important;
  }

  /* Readable input labels and tabs */
  [data-testid="stTextInput"] label,
  [data-testid="stCheckbox"] label,
  [data-testid="stTabs"] button {
    color: #303449 !important;
    opacity: 1 !important;
  }

  /* Input fields */
  [data-testid="stTextInput"] input {
    background: #FFFFFF !important;
    color: #303449 !important;
    border: 1px solid #CBD5D0 !important;
    border-radius: 11px !important;
  }

  [data-testid="stTextInput"] input::placeholder {
    color: #818B88 !important;
  }

  /* All regular buttons */
  .stButton > button,
  .stFormSubmitButton > button {
    background: #EDE9FC !important;
    color: #51458D !important;
    border: 1px solid #CFC7EC !important;
    border-radius: 12px !important;
  }

  /* Primary buttons */
  .stFormSubmitButton > button[kind="primary"],
  .stButton > button[kind="primary"] {
    background: linear-gradient(
      110deg, #796AC2, #3C9E85
    ) !important;
    color: #FFFFFF !important;
    border: none !important;
  }

  /* Reduce excess spacing */
  [data-testid="stForm"] {
    padding: 15px !important;
  }

  .stButton > button {
    min-height: 43px !important;
  }
}

</style>''',unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Supabase Auth + RLS-backed per-account data. Guest demo remains SQLite.
# Each session has its own user access token; no service-role credentials.
# -----------------------------------------------------------------------------
_config = dict(os.environ)
try:
    _config.update(dict(st.secrets))
except Exception:
    pass

if not _config.get('SUPABASE_URL') or not _config.get('SUPABASE_PUBLISHABLE_KEY'):
    st.error('Supabase configuration is missing. Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in Streamlit Secrets.')
    st.stop()

try:
    _auth = SupabaseAuth(_config['SUPABASE_URL'],_config['SUPABASE_PUBLISHABLE_KEY'])
except ValueError as exc:
    st.error(str(exc)); st.stop()

ENABLE_LIVE_SMTP = (
    str(_config.get('MAILPILOT_ENABLE_LIVE_SMTP', 'false')).lower() == 'true'
)

# Recovery links use a one-time token hash in the URL query parameters.
# Streamlit cannot read Supabase's default URL-fragment tokens server-side.
_reset_hash = st.query_params.get('reset_token')
if _reset_hash:
    st.title('Reset your MailPilot Pro password')
    if 'mailpilot_recovery_access' not in st.session_state:
        try:
            st.session_state['mailpilot_recovery_access'] = _auth.verify_recovery_token(_reset_hash)
        except (SupabaseError, ValueError):
            st.error('This reset link is invalid or has expired. Request a new one from the login page.')
            if st.button('Back to sign in', key='reset_back'):
                st.query_params.clear()
                st.rerun()
            st.stop()
        # Remove the one-time token from the browser address after verifying it.
        st.query_params.clear()
    with st.form('complete_password_reset'):
        _new_password = st.text_input('New password (12+ characters)', type='password')
        _confirm_password = st.text_input('Confirm new password', type='password')
        _save_password = st.form_submit_button('Update password', type='primary')
    if _save_password:
        if _new_password != _confirm_password:
            st.error('Passwords do not match.')
        else:
            try:
                _auth.update_password_with_recovery(st.session_state['mailpilot_recovery_access'], _new_password)
                st.session_state.pop('mailpilot_recovery_access', None)
                st.session_state.pop('mailpilot_supabase_tokens', None)
                st.session_state.pop('mailpilot_guest', None)
                st.session_state['mailpilot_reset_success'] = True
                st.rerun()
            except (SupabaseError, ValueError):
                st.error('Unable to reset the password. Request a fresh reset link and try again.')
    st.stop()

if 'mailpilot_recovery_access' in st.session_state:
    st.title('Reset your MailPilot Pro password')
    with st.form('complete_password_reset'):
        _new_password = st.text_input('New password (12+ characters)', type='password')
        _confirm_password = st.text_input('Confirm new password', type='password')
        _save_password = st.form_submit_button('Update password', type='primary')
    if _save_password:
        if _new_password != _confirm_password:
            st.error('Passwords do not match.')
        else:
            try:
                _auth.update_password_with_recovery(st.session_state['mailpilot_recovery_access'], _new_password)
                st.session_state.pop('mailpilot_recovery_access', None)
                st.session_state.pop('mailpilot_supabase_tokens', None)
                st.session_state.pop('mailpilot_guest', None)
                st.session_state['mailpilot_reset_success'] = True
                st.rerun()
            except (SupabaseError, ValueError):
                st.error('Unable to reset the password. Request a fresh reset link and try again.')
    st.stop()

if st.session_state.pop('mailpilot_reset_success', False):
    st.success('Password updated successfully. Please sign in with your new password.')

_identity=None
_tokens=st.session_state.get('mailpilot_supabase_tokens')
if _tokens:
    try:
        _user,_fresh_tokens=_auth.validate(_tokens)
        st.session_state['mailpilot_supabase_tokens']=_fresh_tokens
        _email=(_user.get('email') or '').strip().lower()
        _name=(_user.get('user_metadata') or {}).get('display_name','') or _email.split('@')[0]
        _owner_email=str(_config.get('MAILPILOT_ADMIN_EMAIL','')).strip().lower()
        _role='owner' if _owner_email and _email==_owner_email and _user.get('email_confirmed_at') else 'member'
        _identity={
            'id':_user['id'],
            'name':_name,
            'email':_email,
            'role':_role,
            'email_verified':bool(_user.get('email_confirmed_at')),
        }
        # Avoid carrying an SMTP App Password into another user's session.
        if st.session_state.get('mailpilot_active_user_id') != _identity['id']:
            for key in list(st.session_state.keys()):
                if key.startswith('smtp_'):
                    st.session_state.pop(key, None)
            st.session_state['mailpilot_active_user_id'] = _identity['id']
    except (SupabaseError,KeyError,ValueError):
        st.session_state.pop('mailpilot_supabase_tokens',None)
        st.session_state.pop('mailpilot_active_user_id', None)
        for key in list(st.session_state.keys()):
            if key.startswith('smtp_'):
                st.session_state.pop(key, None)

if not _identity and st.session_state.get('mailpilot_guest'):
    _identity={'id':None,'name':'Guest','email':'Demo visitor','role':'demo'}

if not _identity:
    st.markdown('<div class="hero"><div class="eyebrow">WELCOME TO MAILPILOT PRO</div>'
                '<h2>Build better campaigns, together.</h2>'
                '<p>Create an account, verify your email, and save your campaigns securely. '
                'Or try the guest demonstration.</p></div>',unsafe_allow_html=True)
    left,center,right=st.columns([1,1.7,1])
    with center:
        signin,signup=st.tabs(['Sign in','Create an account'])
        with signin:
            with st.form('mailpilot_login'):
                login_email=st.text_input('Email address',placeholder='you@yourcompany.com')
                login_password=st.text_input('Password',type='password')
                login_clicked=st.form_submit_button('Sign in',type='primary',use_container_width=True)
            if login_clicked:
                try:
                    with st.spinner('Verifying your account...'):
                        result=_auth.login(login_email,login_password)
                    if not result.get('access_token') or not result.get('refresh_token'):
                        raise SupabaseError('Email confirmation may still be required.')
                    st.session_state['mailpilot_supabase_tokens']={
                        'access_token':result['access_token'],
                        'refresh_token':result['refresh_token']}
                    st.session_state.pop('mailpilot_guest',None)
                    st.rerun()
                except (SupabaseError,KeyError):
                    st.error('Unable to sign in. Check your credentials and verify your email first.')
            if st.button('Forgot Password?', key='forgot_password'):
                st.session_state['show_password_reset'] = True

            if st.session_state.get('show_password_reset', False):
                with st.form('password_reset_request'):
                    reset_email = st.text_input('Your registered email address')
                    reset_clicked = st.form_submit_button('Send reset link')

                
                if reset_clicked:
                    try:
                        _auth.recover(reset_email)
                        st.success(
                            'If this email is registered, you will receive '
                            'a password reset link.'
                        )
                    except (SupabaseError, ValueError) as e:
                        print(
                            f"PASSWORD RESET ERROR: {type(e).__name__}: {e}",
                            flush=True
                        )
                        st.error(
                            "Password reset failed."
                        )

        with signup:
            with st.form('mailpilot_signup',clear_on_submit=True):
                full_name=st.text_input('Your name',max_chars=100)
                signup_email=st.text_input('Email address',max_chars=254)
                signup_password=st.text_input('Create password (12+ characters)',type='password')
                confirm_password=st.text_input('Confirm password',type='password')
                privacy_ack=st.checkbox('I agree to the account data notice: MailPilot Pro stores my name, email and campaign records.')
                registered=st.form_submit_button('Create account',type='primary',use_container_width=True)
            if registered:
                if signup_password != confirm_password:
                    st.error('The passwords do not match.')
                elif not privacy_ack:
                    st.error('Please agree to the account data notice.')
                else:
                    try:
                        _auth.signup(full_name,signup_email,signup_password)
                        st.success('Check your email for a Supabase verification link, then return here to sign in.')
                    except (SupabaseError,ValueError) as exc:
                        st.error(str(exc))
            st.caption('New accounts must verify email before signing in. Avoid uploading sensitive contact lists during testing.')
        st.divider()
        st.write('Or explore a fictional demo with no account:')
        if st.button('Explore demo without an account',use_container_width=True):
            st.session_state['mailpilot_guest']=True
            st.rerun()
        st.caption('Registered users save their data in Supabase PostgreSQL. Guest demo data is temporary.')
    st.stop()

st.session_state['mailpilot_identity']=_identity
if _identity['role']=='demo':
    if 'mailpilot_demo_tmp' not in st.session_state:
        st.session_state['mailpilot_demo_tmp']=tempfile.TemporaryDirectory(prefix='mailpilot-public-')
    store=Store(Path(st.session_state['mailpilot_demo_tmp'].name)/'demo.db')
    if not store.get_setting('portfolio_seeded',False):
        store.seed_demo()
        store.add_campaign('Welcome series','Welcome aboard, {name}!',
                           'Hi {name},\n\nThanks for joining the {company} community.')
        store.add_campaign('Monthly newsletter','Updates for {company}',
                           'Hello {name},\n\nHere are our latest updates.')
        store.set_setting('portfolio_seeded',True)
else:
    store=SupabaseStore(_auth,st.session_state['mailpilot_supabase_tokens']['access_token'],_identity['id'])
    try:
        store.ensure_profile(_identity['name'])
    except SupabaseError:
        st.error('Unable to access your personal Supabase data. Check table permissions and Row Level Security.')
        st.stop()

with st.sidebar:
    st.markdown('## ✉️ MailPilot **Pro**')
    st.caption('EMAIL MARKETING AUTOMATION')
    st.caption('SIGNED IN: ' + safe_html(_identity['email']))

    if st.button('Log out', key='mailpilot_logout'):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    if _identity['role'] != 'demo':
        st.markdown(
            '<span class="small-chip">● MAILPILOT WORKSPACE</span>',
            unsafe_allow_html=True
        )
    page=st.radio('WORKSPACE',['Overview','Contacts','Campaign Studio','Daily Automation','Live SMTP','Reports','Settings & Guide']
                  + (['Admin • Users'] if _identity['role']=='owner' else []),label_visibility='collapsed')
    st.divider()
    st.caption('Python · Streamlit · Supabase · Plotly')
    st.caption('Row Level Security · Own-account data')
    st.caption('MailPilot Pro · Email Marketing Platform')

# -----------------------------------------------------------------------------
# Branded HTML emails — safely previewed and optionally sent using the user's SMTP.
# Campaign text remains plain text and is escaped before insertion into HTML.
# The existing core.compose_message supplies the plain-text MIME fallback.
# -----------------------------------------------------------------------------
# Registered users save designs in Supabase. Guest data is temporary SQLite.

# One consistent premium look, not a palette picker.
EMAIL_COLORS = {
    'ink': '#2C3549',
    'muted': '#667583',
    'purple': '#796DC0',
    'sage': '#3F9A83',
    'champagne': '#BEA56B',
    'lavender_light': '#F0EFFA',
    'sage_light': '#E8F4EE',
    'body': '#FFFFFF',
    'border': '#DFE7E3',
}
PATTERN_OPTIONS = ['Waves', 'Soft curves', 'Minimal bands']
DEFAULT_EMAIL_DESIGN = {
    'brand': 'MailPilot Pro',
    'heading': '',
    'preheader': 'A thoughtfully designed message, just for you.',
    'hero_url': '',
    'button_label': '',
    'button_url': '',
    'footer': 'You are receiving this email because you subscribed to our updates.',
    'header_pattern': 'Waves',
    'footer_pattern': 'Waves',
}


def load_email_designs():
    return store.get_setting('email_designs',{})


def get_email_design(campaign_id=None):
    saved=load_email_designs().get(str(campaign_id),{}) if campaign_id is not None else {}
    if not isinstance(saved,dict): saved={}
    return {**DEFAULT_EMAIL_DESIGN, **{k:v for k,v in saved.items() if k in DEFAULT_EMAIL_DESIGN}}


def save_email_design(campaign_id, design):
    existing=load_email_designs()
    existing[str(campaign_id)]={
        key:str(design.get(key,DEFAULT_EMAIL_DESIGN[key]))
        for key in DEFAULT_EMAIL_DESIGN
    }
    store.set_setting('email_designs',existing)


def safe_https_url(value):
    if not value:
        return ''
    value=str(value).strip()
    try:
        p=urlparse(value)
        if (p.scheme.lower()=='https' and p.hostname and not p.username and not p.password
                and not re.search(r'\s',value)):
            return value
    except ValueError:
        pass
    return ''


def html_paragraphs(body):
    chunks=re.split(r'\n\s*\n',str(body).strip())
    if not any(chunks):
        return '<p style="margin:0;">&nbsp;</p>'
    return ''.join(
        '<p style="margin:0 0 19px;font-size:16px;line-height:1.8;color:#4B5861;">'
        +safe_html(chunk).replace('\n','<br>')+'</p>'
        for chunk in chunks
    )


def _wave_png(area='header', style='Waves'):
    """Generate email-safe embedded PNG artwork; no image hosting needed.

    Gmail can ignore inline SVG and some CSS gradients, so this produces PNGs
    attached to outgoing MIME messages with Content-ID (CID).
    """
    style=style if style in PATTERN_OPTIONS else 'Waves'
    width,height=1100,208
    bg=(241,239,250) if area=='header' else (255,255,255)
    image=Image.new('RGB',(width,height),bg)
    draw=ImageDraw.Draw(image)
    twopi=2*math.pi
    amps={'Waves':(22,20,18),'Soft curves':(13,12,11),'Minimal bands':(4,5,5)}
    a,b,c=amps[style]
    waves=1.38 if style=='Waves' else (0.82 if style=='Soft curves' else 1.0)
    def stripe(level,amp,phase,fill):
        upper=[(x, round(level+amp*math.sin(twopi*waves*x/(width-1)+phase))) for x in range(0,width,3)]
        upper.append((width-1,round(level+amp*math.sin(twopi*waves+phase))))
        draw.polygon(upper+[(width-1,height),(0,height)],fill=fill)
    if area=='header':
        # Pale lilac -> sage wave -> soft lilac -> pure white message area.
        stripe(75,a,0.0,(203,225,218))
        stripe(118,b,1.7,(228,221,245))
        stripe(159,c,0.7,(255,255,255))
        # Elegant dotted corner motif above the waves.
        for r in range(3):
            for j in range(16):
                x=70+j*25; y=13+r*19
                color=(193,186,225) if (j+r)%3 else (171,203,188)
                draw.ellipse((x,y,x+3,y+3),fill=color)
        for x,y,rad in [(850,30,5),(895,52,3),(965,28,7),(1010,60,3)]:
            draw.ellipse((x-rad,y-rad,x+rad,y+rad),outline=(188,184,222),width=2)
    else:
        # White message area -> pale lilac -> pale cream -> soft sage footer.
        stripe(48,a,0.9,(230,225,245))
        stripe(101,b,2.2,(246,240,226))
        stripe(151,c,1.1,(232,244,238))
        for r in range(2):
            for j in range(13):
                x=680+j*26; y=167+r*16
                color=(193,201,198) if (j+r)%2 else (191,185,221)
                draw.ellipse((x,y,x+3,y+3),fill=color)
    out=BytesIO()
    image.save(out,format='PNG',optimize=True)
    return out.getvalue()


def _wave_src(area,style,image_mode):
    if image_mode=='cid':
        return f'cid:mailpilot-{area}-wave@local'
    encoded=base64.b64encode(_wave_png(area,style)).decode('ascii')
    return 'data:image/png;base64,'+encoded


def render_branded_html(subject,body,design,sender='',unsubscribe='',image_mode='data'):
    """Full HTML preview with embedded images, or CID-based email HTML."""
    opts={**DEFAULT_EMAIL_DESIGN,**(design or {})}
    brand=safe_html(str(opts.get('brand') or 'Your Team').strip())
    title=safe_html(str(opts.get('heading') or subject).strip())
    preheader=safe_html(str(opts.get('preheader') or '').strip())
    footer=safe_html(str(opts.get('footer') or '').strip()).replace('\n','<br>')
    header_style=opts.get('header_pattern','Waves')
    footer_style=opts.get('footer_pattern','Waves')
    header_src=_wave_src('header',header_style,image_mode)
    footer_src=_wave_src('footer',footer_style,image_mode)
    hero=safe_https_url(opts.get('hero_url',''))
    cta_url=safe_https_url(opts.get('button_url',''))
    button_label=safe_html(str(opts.get('button_label') or '').strip())
    hero_html=(
        '<tr><td style="padding:0 30px 10px;">'
        f'<img src="{safe_html(hero,quote=True)}" alt="Campaign banner" width="580" '
        'style="display:block;width:100%;max-width:580px;height:auto;border:0;border-radius:14px;">'
        '</td></tr>'
    ) if hero else ''
    cta_html=(
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:24px;">'
        '<tr><td bgcolor="#3F9A83" style="background-color:#3F9A83;border-radius:8px;">'
        f'<a href="{safe_html(cta_url,quote=True)}" style="display:inline-block;padding:15px 26px;'
        f'font-size:15px;font-weight:700;color:#FFFFFF;text-decoration:none;">{button_label}</a>'
        '</td></tr></table>'
    ) if cta_url and button_label else ''
    unsub=safe_https_url(unsubscribe)
    unsub_html=(
        f'<a href="{safe_html(unsub,quote=True)}" style="color:#3F806E;text-decoration:underline;">Unsubscribe</a>'
        if unsub else 'To unsubscribe, reply to this email with UNSUBSCRIBE.'
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only">
<title>{safe_html(subject)}</title></head>
<body style="margin:0;padding:0;background-color:#F6F7F5;">
<div style="display:none!important;max-height:0;overflow:hidden;opacity:0;color:transparent;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F6F7F5;width:100%;border-collapse:collapse;">
<tr><td align="center" style="padding:24px 10px 34px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;width:100%;background-color:#FFFFFF;border:1px solid #DFE7E3;border-collapse:separate;border-radius:16px;overflow:hidden;">
<tr><td bgcolor="#F0EFFA" style="background-color:#F0EFFA;padding:29px 34px 0;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
<td style="font:700 15px Arial,Helvetica,sans-serif;color:#3F4A58;letter-spacing:1px;">✦ &nbsp;{brand}</td>
<td align="right" style="font:700 10px Arial,Helvetica,sans-serif;color:#796DC0;letter-spacing:1.5px;">A NOTE FOR YOU</td>
</tr></table>
<h1 style="font:700 30px/1.28 Arial,Helvetica,sans-serif;letter-spacing:-.6px;color:#2C3549;margin:24px 0 0;">{title}</h1>
</td></tr>
<tr><td bgcolor="#FFFFFF" style="padding:0;margin:0;line-height:0;font-size:0;">
<img src="{header_src}" width="640" alt="" style="width:100%;max-width:640px;display:block;height:auto;border:0;">
</td></tr>
{hero_html}
<tr><td bgcolor="#FFFFFF" style="padding:24px 34px 35px;font-family:Arial,Helvetica,sans-serif;">
<p style="margin:0 0 24px;color:#796DC0;font-size:12px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;">A little something from our team</p>
{html_paragraphs(body)}
{cta_html}
</td></tr>
<tr><td bgcolor="#FFFFFF" style="padding:0;line-height:0;font-size:0;">
<img src="{footer_src}" width="640" alt="" style="width:100%;max-width:640px;display:block;height:auto;border:0;">
</td></tr>
<tr><td bgcolor="#E8F4EE" style="background-color:#E8F4EE;padding:4px 34px 30px;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="font:700 15px Arial,Helvetica,sans-serif;color:#34483F;">✦ &nbsp;{brand}</td>
<td align="right" style="font:12px Arial,Helvetica,sans-serif;color:#517A6B;">Thank you for reading</td>
</tr></table>
<p style="font:13px/1.75 Arial,Helvetica,sans-serif;color:#5D6D66;margin:18px 0 12px;">{footer}</p>
<p style="font:12px/1.65 Arial,Helvetica,sans-serif;color:#52685D;margin:0 0 12px;">{unsub_html}</p>
<p style="font:11px Arial,Helvetica,sans-serif;color:#71877B;margin:0;">Made with care · {brand}</p>
</td></tr>
</table></td></tr></table></body></html>"""


def compose_branded_message(sender,recipient,subject,body,reply_to='',unsubscribe='',design=None,sender_display_name=''):
    """Preserve core.py MIME plain text, add safe HTML and inline wave images."""
    opts={**DEFAULT_EMAIL_DESIGN,**(design or {})}
    msg=compose_message(sender,recipient,subject,body,reply_to,unsubscribe)
    # The From header can show a brand name while retaining the verified sender email.
    # Header names are plain text; strip CR/LF to prevent header injection.
    visible_name=(sender_display_name or '').replace('\r',' ').replace('\n',' ').strip()[:100]
    if visible_name:
        msg.replace_header('From',formataddr((visible_name,sender)))
    html_part=msg.get_body(preferencelist=('html',))
    if html_part is None:
        raise ValueError('Could not build the HTML alternative.')
    html_part.set_content(render_branded_html(subject,body,opts,sender,unsubscribe,image_mode='cid'),subtype='html')
    html_part.add_related(_wave_png('header',opts.get('header_pattern','Waves')),
        maintype='image',subtype='png',cid='<mailpilot-header-wave@local>',
        filename='mailpilot-header-wave.png',disposition='inline')
    html_part.add_related(_wave_png('footer',opts.get('footer_pattern','Waves')),
        maintype='image',subtype='png',cid='<mailpilot-footer-wave@local>',
        filename='mailpilot-footer-wave.png',disposition='inline')
    return msg


def personalized_design(design,contact):
    result=dict(design)
    for key in ('brand','heading','preheader','footer','button_label'):
        result[key]=personalize(str(result.get(key,'')),contact)
    return result

contacts=store.contacts();campaigns=store.campaigns();events=store.events();deliveries=store.deliveries()
segments=sorted({c['segment'] for c in contacts})
used=store.daily_used()

# Warm accent strip for each page.
if page!='Overview':
    section_names={
        'Contacts':'AUDIENCE / CONTACTS',
        'Campaign Studio':'CREATE / CAMPAIGNS',
        'Daily Automation':'WORKFLOWS / SIMULATION',
        'Live SMTP':'DELIVERY / LIVE SMTP',
        'Reports':'INSIGHTS / REPORTS',
        'Settings & Guide':'SYSTEM / SETTINGS',
    }
    st.markdown(
        f'<div class="section-ribbon"><span>✦ MAILPILOT PRO &nbsp; / &nbsp; {section_names.get(page, "WORKSPACE")}</span><span class="ribbon-mark"></span></div>',
        unsafe_allow_html=True,
    )

def table(data,columns=None):
    st.dataframe(pd.DataFrame(data)[columns] if data and columns else pd.DataFrame(data),hide_index=True,use_container_width=True)

def campaign_select(label='Choose campaign',key='campaign_choice'):
    if not campaigns:
        st.info('Create a campaign in Campaign Studio first.')
        return None
    ids=[c['id'] for c in campaigns]
    return st.selectbox(label,ids,format_func=lambda i:next(f"{c['title']} · #{i}" for c in campaigns if c['id']==i),key=key)

if _identity.get('role')=='demo':
    st.caption('🌐 GUEST DEMO — fictional data and simulated activity. No real sending in guest mode.')
else:
    st.caption('🔐 ACCOUNT MODE — your data is private under Supabase Row Level Security.')

if page=='Overview':
    st.markdown('<div class="hero"><div class="eyebrow">CAMPAIGN OPERATIONS CENTER</div><h2>Good to see you — welcome to MailPilot Pro</h2><p>Explore your campaigns and design professional messages. Signed-in users can connect their own SMTP accounts; demo simulation remains separate.</p></div>',unsafe_allow_html=True)
    subscribed=sum(bool(c['subscribed']) for c in contacts)
    simulated=len(events)
    accepted=sum(d['status']=='sent' for d in deliveries)
    a,b,c,d,e=st.columns(5)
    a.metric('Total contacts',len(contacts),help='All locally stored contacts')
    b.metric('Subscribed',subscribed,help='Contacts marked as subscribed')
    c.metric('Campaigns',len(campaigns))
    d.metric('Simulated activity',simulated,help='Demo events, not real deliveries')
    e.metric('Live sending','Guest demo' if _identity.get('role')=='demo' else 'Own SMTP',help='Each signed-in person supplies their own SMTP credentials')
    st.write('')
    left,right=st.columns([1.65,1],gap='large')
    with left:
        st.subheader('Activity overview')
        st.markdown('<div class="section-note">Daily simulation and subscriber status — interactive circular charts. No real emails are sent in Demo Mode.</div>', unsafe_allow_html=True)

        # Daily simulation slots are independent of real SMTP attempts.
        slots_used = min(max(int(used), 0), MAX_DAILY)
        slots_remaining = max(0, MAX_DAILY - slots_used)
        subscribers = sum(bool(c['subscribed']) for c in contacts)
        non_subscribers = len(contacts) - subscribers

        chart_a, chart_b = st.columns(2, gap='small')
        with chart_a:
            fig_slots = go.Figure(go.Pie(
                labels=['Used today', 'Remaining'],
                values=[slots_used, slots_remaining],
                hole=0.73,
                sort=False,
                marker=dict(
                    colors=['#796AC2', '#DCEDE4'],
                    line=dict(color='#FFFFFF', width=3),
                ),
                textinfo='none',
                hovertemplate='%{label}: %{value} slots<extra></extra>',
            ))
            fig_slots.update_layout(
                title=dict(text='Daily demo slots', x=0.5, xanchor='center', font=dict(size=15, color='#303449')),
                annotations=[dict(text=f'<b>{slots_used} / {MAX_DAILY}</b><br><span style="font-size:11px">used today</span>',
                                  x=0.5, y=0.5, showarrow=False, align='center',
                                  font=dict(size=19, color='#303449'))],
                legend=dict(orientation='h', yanchor='bottom', y=-0.20, xanchor='center', x=0.5, font=dict(size=11)),
                margin=dict(l=8, r=8, t=45, b=60),
                height=290, paper_bgcolor='rgba(0,0,0,0)',
                font=dict(family='DM Sans', color='#525B60'),
            )
            st.plotly_chart(fig_slots, use_container_width=True, config={'displayModeBar': False})

        with chart_b:
            # Show a neutral ring rather than implying a 100% audience when no contacts exist.
            has_contacts = bool(contacts)
            fig_audience = go.Figure(go.Pie(
                labels=['Subscribed', 'Not subscribed'] if has_contacts else ['No contacts yet'],
                values=[subscribers, non_subscribers] if has_contacts else [1],
                hole=0.73, sort=False,
                marker=dict(
                    colors=['#4BA78D', '#E8E4F4'] if has_contacts else ['#E5E9E7'],
                    line=dict(color='#FFFFFF', width=3),
                ),
                textinfo='none',
                hovertemplate='%{label}: %{value} contacts<extra></extra>' if has_contacts else 'Add contacts to see this chart<extra></extra>',
            ))
            fig_audience.update_layout(
                title=dict(text='Subscriber status', x=0.5, xanchor='center', font=dict(size=15, color='#303449')),
                annotations=[dict(text=f'<b>{subscribers}</b><br><span style="font-size:11px">of {len(contacts)} subscribed</span>' if has_contacts else '<b>0</b><br><span style="font-size:11px">contacts</span>',
                                  x=0.5, y=0.5, showarrow=False, align='center',
                                  font=dict(size=19, color='#303449'))],
                showlegend=has_contacts,
                legend=dict(orientation='h', yanchor='bottom', y=-0.20, xanchor='center', x=0.5, font=dict(size=11)),
                margin=dict(l=8, r=8, t=45, b=60),
                height=290, paper_bgcolor='rgba(0,0,0,0)',
                font=dict(family='DM Sans', color='#525B60'),
            )
            st.plotly_chart(fig_audience, use_container_width=True, config={'displayModeBar': False})

        # Circular gauge: shows the proportion of today's demo capacity used.
        utilization = round(100 * slots_used / MAX_DAILY) if MAX_DAILY else 0
        fig_gauge = go.Figure(go.Indicator(
            mode='gauge+number', value=utilization,
            number=dict(suffix='%', font=dict(size=29, color='#303449')),
            title=dict(text='Daily automation usage', font=dict(size=15, color='#303449')),
            gauge=dict(
                axis=dict(range=[0, 100], tickvals=[0, 25, 50, 75, 100], ticksuffix='%',
                          tickcolor='#89958F', tickfont=dict(size=10)),
                bar=dict(color='#796AC2', thickness=0.36),
                bgcolor='#EFF3F0', borderwidth=0,
                steps=[dict(range=[0, 50], color='#E9E5F6'),
                       dict(range=[50, 100], color='#DDECE4')],
                threshold=dict(line=dict(color='#4BA78D', width=3), thickness=0.7, value=100),
            ),
        ))
        fig_gauge.update_layout(
            margin=dict(l=38, r=38, t=52, b=10),
            height=255,
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(family='DM Sans', color='#525B60'),
        )
        st.plotly_chart(fig_gauge, use_container_width=True, config={'displayModeBar': False})
        st.caption('These charts show fictional simulated activity only; no messages are sent.')
        st.subheader('Audience by segment')
        if contacts:
            segdf=pd.DataFrame(contacts).groupby('segment',as_index=False).size().rename(columns={'size':'Contacts'})
            fig=px.bar(segdf,x='segment',y='Contacts',color='segment',color_discrete_sequence=['#7063B9','#4BA78D','#D0B66E','#9AB88F','#8F88C5'])
            fig.update_layout(showlegend=False,height=275,margin=dict(l=5,r=5,t=8,b=10),plot_bgcolor='white',paper_bgcolor='white',xaxis_title='',yaxis=dict(gridcolor='#E5ECE8'))
            st.plotly_chart(fig,use_container_width=True)
        else:st.caption('Audience segments will appear after contacts are added.')
    with right:
        st.subheader('Daily automation capacity')
        st.metric('Demo slots remaining',max(0,MAX_DAILY-used),f'{used} used today')
        st.progress(min(used/MAX_DAILY,1.0))
        st.caption('Resets at midnight UTC · 10 simulated recipients per day')
        st.markdown('<div class="panel"><h4>✦ Recommended workflow</h4><p>1. Add opted-in contacts<br>2. Build your campaign<br>3. Preview the HTML design<br>4. Test your own SMTP<br>5. Send or simulate, then review reports</p></div>',unsafe_allow_html=True)
        st.subheader('Campaign portfolio')
        if campaigns:
            for campaign in campaigns[:4]:
                count=sum(e['campaign_id']==campaign['id'] for e in events) if events and 'campaign_id' in events[0] else sum(e['campaign']==campaign['title'] for e in events)
                st.markdown(f'<div class="panel"><h4>{safe_html(campaign["title"])}</h4><p>{count} simulated sends · Campaign #{campaign["id"]}</p></div>',unsafe_allow_html=True)
        else:st.caption('Your saved campaigns will appear here.')
    st.subheader('Recent activity')
    if events:table(events[:8],['day','campaign','recipient_name','email'])
    else:st.caption('No simulated activity recorded yet.')
    with st.expander('About these metrics'):
        st.write('Simulation counts are generated from demo activity, not real delivery or engagement. Live SMTP attempts are reported separately. No tracking pixels are installed.')

elif page=='Contacts':
    st.title('Contact Management')
    if _identity.get('role')=='demo':
        st.info('Guest mode uses fictional contacts only. Sign in to add your own contacts.')
    else:
        st.warning('Add only people who have explicitly agreed to receive your emails. Never upload purchased or scraped lists.')
    ca,cb,cc=st.columns(3)
    ca.metric('Total contacts',len(contacts))
    cb.metric('Subscribed',sum(bool(c['subscribed']) for c in contacts))
    cc.metric('Segments',len(segments))
    tab1,tab2=st.tabs(['Contact list','Add or import contacts'])
    with tab1:
        q=st.text_input('Search contacts',placeholder='Search name, email or company')
        filt=st.selectbox('Subscription status',['All','Subscribed','Unsubscribed'])
        visible=[c for c in contacts if q.lower() in (' '.join(str(v) for v in c.values())).lower()
                 and (filt=='All' or bool(c['subscribed'])==(filt=='Subscribed'))]
        table([{'Name':c['name'],'Email':c['email'],'Company':c['company'],'Segment':c['segment'],
               'Subscribed':'Yes' if c['subscribed'] else 'No'} for c in visible])
        if _identity.get('role')!='demo' and contacts:
            target=st.selectbox('Manage a contact',[c['email'] for c in contacts])
            row=next(c for c in contacts if c['email']==target)
            a,b=st.columns(2)
            subscribed=a.checkbox('Explicitly subscribed',value=bool(row['subscribed']),key='contact_subscribed')
            segment=b.text_input('Segment',value=row['segment'],key='contact_segment')
            if st.button('Save contact',key='save_contact'):
                store.update_contact(target,subscribed,segment)
                st.success('Contact updated.');st.rerun()
            with st.expander('Remove contact'):
                if st.button('Delete this contact',key='delete_contact'):
                    store.delete_contact(target);st.rerun()
    with tab2:
        if _identity.get('role')=='demo':
            st.info('Sign in or create your own account to manage real opted-in contacts.')
        else:
            with st.form('contact_add',clear_on_submit=True):
                a,b=st.columns(2)
                name=a.text_input('Full name')
                email=b.text_input('Email address')
                c,d=st.columns(2)
                company=c.text_input('Company (optional)')
                segment=d.text_input('Segment',value='General')
                opted=st.checkbox('I confirm this person explicitly opted in to receive emails.')
                add=st.form_submit_button('Add contact',type='primary')
            if add:
                if not opted:
                    st.error('Explicit permission is required to add a subscribed contact.')
                else:
                    try:
                        store.add_contact(name,email,company,segment,subscribed=True)
                        st.success('Subscribed contact saved to your Supabase account.');st.rerun()
                    except (ValueError,sqlite3.IntegrityError,SupabaseError) as exc:
                        st.error('Could not add contact: '+str(exc))
            st.divider()
            st.caption('CSV columns: name,email,subscribed,company,segment. Import only permission-based contacts.')
            uploaded=st.file_uploader('Import opted-in contacts (CSV, max 2MB)',type='csv',key='contact_csv')
            verified=st.checkbox('The uploaded contacts provided permission for marketing emails.',key='import_permission')
            if st.button('Import CSV',disabled=not bool(uploaded) or not verified):
                try:
                    n,skipped=store.import_csv(uploaded.getvalue())
                    st.success(f'Imported {n} contacts; skipped {skipped}.');st.rerun()
                except (ValueError,UnicodeDecodeError) as exc:
                    st.error('CSV import failed: '+str(exc))
            st.download_button('Export contacts CSV',csv_bytes(contacts,['name','email','company','segment','subscribed','created_at']),
                               'mailpilot-contacts.csv','text/csv')

elif page=='Campaign Studio':
    st.title('Campaign Studio')
    st.caption('Write your message, then design a premium email with a wavy header and footer, optional banner and website button.')
    create,manage,designer=st.tabs(['Create campaign','Edit & preview','HTML email designer'])
    with create:
        st.info('Create the campaign first, then personalize its HTML design. Demo mode never sends real messages.')
        template=st.selectbox('Start from a template',['Welcome message','Product update','Newsletter','Event invitation','Blank'])
        examples={
                'Welcome message':('Welcome to our community, {name}!','Hi {name},\n\nThank you for subscribing to our updates. We are glad to have you with us.\n\nBest regards,\nThe Team'),
                'Product update':('A new update for {company}','Hi {name},\n\nWe have a new update to share with you.\n\nBest regards,\nThe Team'),
                'Newsletter':('Your monthly newsletter','Hello {name},\n\nHere are this month\'s highlights.\n\nBest regards,\nThe Team'),
                'Event invitation':('You are invited, {name}','Hi {name},\n\nWe would love to invite you to our upcoming event.\n\nBest regards,\nThe Team'),
                'Blank':('','')
            }
        sample_subject,sample_body=examples[template]
        with st.form('new_campaign',clear_on_submit=True):
            title=st.text_input('Campaign name',placeholder='November Welcome Series')
            subject=st.text_input('Email subject',value=sample_subject,placeholder='Hello {name}, a quick update')
            body=st.text_area('Email body',value=sample_body,height=230)
            submitted=st.form_submit_button('Save campaign',type='primary')
        if submitted:
            try:store.add_campaign(title,subject,body);st.success('Campaign created.');st.rerun()
            except ValueError as e:st.error(str(e))
    with manage:
        cid=campaign_select(key='studio')
        if cid is not None:
            c=next(x for x in campaigns if x['id']==cid)
            with st.form('edit_campaign'):
                title=st.text_input('Campaign name',value=c['title']);subject=st.text_input('Subject',value=c['subject'])
                body=st.text_area('Message',value=c['body'],height=230)
                save=st.form_submit_button('Save changes',type='primary')
            if save:
                try:store.update_campaign(cid,title,subject,body);st.success('Saved.');st.rerun()
                except ValueError as e:st.error(str(e))
            st.subheader('Personalization preview')
            example=contacts[0] if contacts else {'name':'Alex','email':'alex@example.com','company':'Example Co'}
            st.text_input('Preview recipient',value=example['email'],disabled=True)
            st.markdown('**Subject:** '+personalize(c['subject'],example))
            st.text_area('Message preview',personalize(c['body'],example),height=220,disabled=True)
            with st.expander('Delete this campaign'):
                st.warning('Deleting a campaign also deletes its simulated activity records.')
                if st.button('Confirm delete campaign'):
                    store.delete_campaign(cid);st.rerun()
    with designer:
        st.markdown('**Premium email designer — wavy header and footer, without a color palette.**')
        st.caption('No color palette: one refined Sage & Lilac style. Choose wavy header and footer patterns. The waves are embedded into sent emails, not hosted elsewhere. Optional banner pictures need a public HTTPS URL.')
        design_cid = campaign_select('Choose a campaign to design',key='html_design_campaign')
        if design_cid is not None:
            design_campaign = next(c for c in campaigns if c['id'] == design_cid)
            current_design = get_email_design(design_cid)
            with st.form(f'email_design_form_{design_cid}'):
                pat_a,pat_b=st.columns(2)
                header_pattern=pat_a.selectbox('Header pattern',PATTERN_OPTIONS,
                    index=PATTERN_OPTIONS.index(current_design['header_pattern']) if current_design['header_pattern'] in PATTERN_OPTIONS else 0)
                footer_pattern=pat_b.selectbox('Footer pattern',PATTERN_OPTIONS,
                    index=PATTERN_OPTIONS.index(current_design['footer_pattern']) if current_design['footer_pattern'] in PATTERN_OPTIONS else 0)
                col1,col2 = st.columns(2)
                brand = col1.text_input('Brand name in email header',value=current_design['brand'],max_chars=80)
                heading = col2.text_input('Main header headline (optional)',value=current_design['heading'],
                                          placeholder='Defaults to your campaign subject',max_chars=160)
                preheader = st.text_input('Preview line shown by some inboxes',value=current_design['preheader'],max_chars=180)
                hero_url = st.text_input('Optional banner picture URL (HTTPS only)',value=current_design['hero_url'],
                                         placeholder='https://yourdomain.com/banner.jpg')
                btn1,btn2 = st.columns(2)
                button_label = btn1.text_input('Optional button label',value=current_design['button_label'],placeholder='Visit our website',max_chars=80)
                button_url = btn2.text_input('Optional button link (HTTPS only)',value=current_design['button_url'],placeholder='https://example.com')
                footer = st.text_area('Footer description',value=current_design['footer'],height=100,max_chars=500)
                save_design = st.form_submit_button('Save HTML email design',type='primary')
            draft_design = dict(brand=brand,heading=heading,preheader=preheader,
                                hero_url=hero_url,button_label=button_label,button_url=button_url,
                                footer=footer,header_pattern=header_pattern,footer_pattern=footer_pattern)
            if save_design:
                bad_urls = [name for name, value in (('banner picture', hero_url),('button link', button_url))
                            if value and not safe_https_url(value)]
                if bad_urls:
                    st.error('Please use a valid public HTTPS URL for: '+', '.join(bad_urls))
                else:
                    try:
                        save_email_design(design_cid,draft_design)
                        st.success('Design saved in your account (Supabase for members; temporary storage for guests).')
                    except OSError as exc:
                        st.error(f'Could not save design: {exc}')
            example={'name':'Alex','email':'alex@example.com','company':'Example Co'}
            st.subheader('Inbox-style preview')
            st.caption('This is a visual preview. Email clients may display HTML differently. Live SMTP uses this saved design.')
            sample_subject=personalize(design_campaign['subject'],example)
            sample_body=personalize(design_campaign['body'],example)
            sample_design=personalized_design(draft_design,example)
            sample_html=render_branded_html(sample_subject,sample_body,sample_design,unsubscribe='')
            components.html(sample_html,height=740,scrolling=True)
            st.download_button('Download preview as HTML',sample_html.encode('utf-8'),
                               file_name=f'campaign-{design_cid}-email-preview.html',mime='text/html')

elif page=='Daily Automation':
    st.title('Daily Automation Simulator')
    st.markdown('<span class="tag">SIMULATION ONLY · ZERO EMAILS SENT</span>',unsafe_allow_html=True)
    st.write('Demonstrate a controlled daily batch of up to 10 subscribed recipients. The demo records simulated activity locally.')
    cid=campaign_select(key='auto')
    if cid is not None:
        segment=st.selectbox('Audience segment',['All']+segments)
        eligible=store.preview(cid,segment)
        a,b,c=st.columns(3)
        a.metric('Eligible for this campaign',len(eligible));b.metric('Daily capacity remaining',max(0,MAX_DAILY-used));c.metric('Will simulate now',min(len(eligible),MAX_DAILY-used))
        st.subheader('Next recipients')
        if eligible and used < MAX_DAILY:
            table(eligible[:max(0, MAX_DAILY-used)], ['name', 'email', 'company', 'segment'])
        else:
            st.info('No eligible contacts or the daily limit has been reached.')
        confirm=st.checkbox('I understand this is a demo and no real messages will be sent.')
        if st.button('Run daily simulation',type='primary',disabled=not confirm or not eligible or used>=MAX_DAILY):
            with st.spinner('Processing demo recipients — no real emails will be sent...'):
                people=store.simulate(cid,segment)
            st.success(f'Simulated {len(people)} emails. No network requests or real emails were sent.');st.rerun()
        st.caption('Each contact is simulated at most once per campaign. The global 10/day cap resets at midnight UTC. There is no background scheduler in this demo.')

elif page=='Live SMTP':
    if _identity.get('role') != 'demo' and not ENABLE_LIVE_SMTP:
        st.title('SMTP Email Delivery')
        st.warning('SMTP connections are temporarily unavailable. Please try again later.')
        st.stop()
    st.title('SMTP Email Delivery')
    st.caption("Connect your own email provider. This application never uses the owner's Gmail account to send another user's email.")
    if _identity.get('role')=='demo':
        st.info('Preview mode: SMTP actions are simulated.')
        provider=st.selectbox('SMTP provider (demo)',list(PROVIDERS),key='guest_smtp_provider')
        relay=provider_config(provider)
        st.text_input('SMTP server',value=relay.host,disabled=True)
        a,b=st.columns(2)
        a.text_input('Port',value=str(relay.port),disabled=True)
        b.text_input('Encryption',value=relay.security,disabled=True)
        if st.button('Simulate Test Connection'):
            with st.spinner('Simulating secure connection...'):
                st.success('Demo: connection simulated. No network request was made.')
        if st.button('Simulate Send Test Email'):
            with st.spinner('Simulating email sending...'):
                st.success('Demo: test email simulated. No real email was sent.')
        cid=campaign_select('Choose a demo campaign',key='demo_live_preview')
        if cid is not None:
            campaign=next(c for c in campaigns if c['id']==cid)
            person=contacts[0] if contacts else {
                'name':'Alex',
                'email':'demo@example.com',
                'company':'Sample Co'
            }

            st.subheader('Preview your designed email')
            preview_html=render_branded_html(
                personalize(campaign['subject'],person),
                personalize(campaign['body'],person),
                personalized_design(get_email_design(cid),person)
            )
            components.html(preview_html,height=640,scrolling=True)

    else:
        st.warning('Use only your own SMTP account. Its app password/key is sent securely to the Streamlit server for sending, held in that server session, and not saved to SQLite. Only use trusted hosting.')
        config=store.get_setting('smtp_preferences',{})
        if not isinstance(config,dict):
            config={}
        options=list(PROVIDERS)
        old_provider=config.get('provider','Titan Email')
        if old_provider not in options: old_provider='Titan Email'
        provider=st.selectbox('Your email provider',options,index=options.index(old_provider),key='smtp_provider')
        relay=provider_config(provider)
        with st.expander('SMTP connection settings',expanded=True):
            a,b,c=st.columns(3)
            a.text_input('SMTP host',value=relay.host,disabled=True)
            b.text_input('Port',value=str(relay.port),disabled=True)
            c.text_input('Security',value=relay.security,disabled=True)
            username=st.text_input('Your SMTP username / email',value=config.get('username',''),key='smtp_login_name')
            password=st.text_input('Your SMTP app password / SMTP key',type='password',key='smtp_user_secret',
                                   help='Different from your MailPilot Pro login password. Never share it with anyone.')
            sender=st.text_input('Your verified From email address',value=config.get('sender',''),key='smtp_from_email')
            display_name=st.text_input('Sender display / brand name',value=config.get('display_name',''),key='smtp_display_name')
            reply_to=st.text_input('Reply-to (optional)',value=config.get('reply_to',''),key='smtp_reply')
            unsubscribe=st.text_input('Unsubscribe HTTPS URL (optional)',value=config.get('unsubscribe',''),key='smtp_unsubscribe')
            if st.button('Save SMTP preferences (not password)',key='smtp_save_preferences'):
                try:
                    validate_sender(provider,username.strip(),sender.strip())
                    if reply_to and not valid_email(reply_to):
                        raise ValueError('Enter a valid Reply-to address.')
                    if unsubscribe and not safe_https_url(unsubscribe):
                        raise ValueError('Unsubscribe URL must start with https://')
                    store.set_setting('smtp_preferences',{
                        'provider':provider,'username':username.strip(),'sender':sender.strip(),
                        'display_name':display_name.strip(),'reply_to':reply_to.strip(),
                        'unsubscribe':unsubscribe.strip()})
                    st.success('Non-secret preferences saved in your personal Supabase database. Password was not saved.')
                except ValueError as exc:
                    st.error(str(exc))
            if provider=='Brevo':
                st.caption('Brevo uses a separate SMTP login and key. Your From email must be verified in Brevo.')
            else:
                st.caption('The From address must match your SMTP login. Gmail/Titan may require app passwords.')

        try:
            validate_sender(provider,username.strip(),sender.strip())
            ready=bool(password.strip())
            validation_error=''
        except ValueError as exc:
            ready=False
            validation_error=str(exc)
        if validation_error:
            st.info(validation_error)
        elif not ready:
            st.info('Enter the SMTP app password or key to enable tests and real sending.')

        st.subheader('1. Test connection')
        if st.button('Test Connection',disabled=not ready,key='test_own_smtp'):
            with st.spinner('Connecting securely to your SMTP provider...'):
                try:
                    test_smtp_login(provider,username.strip(),password)
                    st.success('SMTP authentication succeeded. No email was sent.')
                except Exception as exc:
                    st.error(friendly_error(exc))

        # All authenticated, email-verified members may use their own SMTP
        # account. Guest visitors remain simulation-only. The configured
        # server-wide switch and existing daily caps still apply.
        if not _identity.get('email_verified', False):
            st.warning('Verify your MailPilot Pro account email before live sending.')
            st.stop()
        st.subheader('2. Send a real test to your own address')
        st.caption('To prevent abuse, test messages go only to your verified From email. Maximum 3 test attempts per UTC day.')
        remaining_tests=max(0,3-store.smtp_tests_used())
        st.metric('Test emails remaining (UTC)',remaining_tests)
        test_cid=campaign_select('Optional campaign design for test',key='smtp_test_design')
        test_campaign=next((c for c in campaigns if c['id']==test_cid),None)
        if st.button('Send Test Email',disabled=not ready or remaining_tests==0,key='send_own_test'):
            test_id=None
            try:
                test_id=store.reserve_smtp_test(sender.strip())
                if test_campaign:
                    person={'name':_identity.get('name') or 'Subscriber','email':sender.strip(),'company':'My Company'}
                    subject=personalize(test_campaign['subject'],person)
                    body=personalize(test_campaign['body'],person)
                    design=personalized_design(get_email_design(test_cid),person)
                else:
                    subject='MailPilot Pro · SMTP test'
                    body='Your own SMTP account is connected. This is a real test from MailPilot Pro.'
                    design=DEFAULT_EMAIL_DESIGN
                msg=compose_branded_message(sender.strip(),sender.strip(),subject,body,
                    reply_to.strip(),unsubscribe.strip(),design,display_name.strip())
                with st.spinner('Sending your test email...'):
                    send_via_user_smtp(provider,username.strip(),password,msg)
                store.finish_smtp_test(test_id,True)
                st.success('SMTP server accepted the test. Check your inbox and spam folder.')
            except Exception as exc:
                if test_id is not None:
                    store.finish_smtp_test(test_id,False,type(exc).__name__)
                st.error(friendly_error(exc))

        st.divider()
        st.subheader('3. Send an approved campaign')
        st.caption('Maximum 10 live campaign attempts per UTC day per account. Contacts must be explicitly subscribed. No automatic/background sending.')
        send_cid=campaign_select('Campaign to send',key='smtp_live_campaign')
        chosen=[]
        if send_cid is not None:
            campaign=next(c for c in campaigns if c['id']==send_cid)
            prior={d['email'].lower() for d in deliveries if d['campaign_id']==send_cid}
            options=[c for c in contacts if c['subscribed'] and c['email'].lower() not in prior
                     and not c['email'].lower().endswith(('@example.com','@example.org','@example.net'))]
            chosen_emails=st.multiselect('Select opted-in recipients',[c['email'] for c in options],
               format_func=lambda email:next(f"{p['name']} — {p['email']}" for p in options if p['email']==email))
            chosen=[c for c in options if c['email'] in chosen_emails]
            if chosen:
                person=chosen[0]
                st.markdown('**Personalized subject:** '+personalize(campaign['subject'],person))
                st.text_area('Email preview (first recipient)',personalize(campaign['body'],person),height=150,disabled=True)
        remaining=max(0,MAX_DAILY-store.live_used())
        st.metric('Live campaign attempts remaining (UTC)',remaining)
        consent=st.checkbox('Each selected person explicitly opted in, and I can process unsubscribe requests.',key='smtp_consent')
        confirmation=st.text_input('Type SEND to confirm real campaign sending',key='smtp_confirmation')
        can_send=bool(ready and send_cid is not None and chosen and remaining>0 and consent and confirmation=='SEND')
        if st.button('Send Campaign',type='primary',disabled=not can_send,key='smtp_send_campaign'):
            successes=failures=0
            progress=st.progress(0,text=f'Sending 0 of {min(len(chosen),remaining)}')
            for idx,candidate in enumerate(chosen[:remaining],1):
                message_error=''
             
                try:
                    person = store.reserve_live(
                        send_cid, candidate['email']
                    )
                except SupabaseError as exc:
                    print(
                        f"LIVE SMTP RESERVE ERROR: {exc}",
                        flush=True
                    )
                    st.error(
                        "Unable to prepare recipient. "
                        "Check Streamlit logs."
                    )
                    continue
                except ValueError as exc:
                    st.warning(f"Recipient skipped: {exc}")
                    continue

                try:
                    message=compose_branded_message(sender.strip(),person['email'],
                        personalize(campaign['subject'],person),personalize(campaign['body'],person),
                        reply_to.strip(),unsubscribe.strip(),personalized_design(get_email_design(send_cid),person),
                        display_name.strip())
                    send_via_user_smtp(provider,username.strip(),password,message)
                    store.finish_live(send_cid,person['email'],True)
                    successes+=1
                except Exception as exc:
                    message_error=type(exc).__name__
                    store.finish_live(send_cid,person['email'],False,message_error)
                    failures+=1
                    st.warning(f"{person['email']}: {friendly_error(exc)}")
                progress.progress(idx/min(len(chosen),remaining),text=f'Sending {idx} of {min(len(chosen),remaining)}')
            st.session_state['smtp_last_result']=f'SMTP accepted {successes} message(s). Failed: {failures}. See delivery log.'
            # st.rerun()
        if not can_send:
            st.caption('To send: enter your own SMTP login/key, create a campaign, select real opted-in contacts, confirm permission, and type SEND.')
        if st.session_state.get('smtp_last_result'):
            st.success(st.session_state.pop('smtp_last_result'))
        st.subheader('SMTP delivery log')
        if deliveries:
            table(deliveries,['created_at','campaign','recipient_name','email','status','error'])
        else:
            st.caption('No live campaign attempts yet.')
        st.caption('SMTP acceptance does not guarantee inbox delivery. The app does not claim opens or clicks.')


elif page=='Reports':
    st.title('Campaign Reports')
    st.caption('Simulated activity is separate from live SMTP attempts. Server acceptance is not proof of inbox delivery.')
    a,b,c=st.columns(3)
    a.metric('Simulated emails',len(events));b.metric('Campaigns',len(campaigns));c.metric('Unique simulated recipients',len({e['email'] for e in events}))
    if events:
        df=pd.DataFrame(events)
        left,right=st.columns(2)
        with left:
            counts=df.groupby('campaign',as_index=False).size().rename(columns={'size':'Simulated emails'})
            fig=px.bar(counts,x='campaign',y='Simulated emails',color_discrete_sequence=['#6E61B8'])
            fig.update_layout(height=320,margin=dict(l=10,r=10,t=20,b=10));st.plotly_chart(fig,use_container_width=True)
        with right:
            days=df.groupby('day',as_index=False).size().rename(columns={'size':'Simulated emails'})
            fig=px.line(days,x='day',y='Simulated emails',markers=True,color_discrete_sequence=['#6E61B8'])
            fig.update_layout(height=320,margin=dict(l=10,r=10,t=20,b=10));st.plotly_chart(fig,use_container_width=True)
        st.subheader('Event log');table(events,['day','campaign','recipient_name','email','simulated_at'])
        st.download_button('Download activity report (CSV)',csv_bytes(events,['day','campaign','recipient_name','email','simulated_at']),'mailpilot-demo-report.csv','text/csv',type='primary')
    else:st.info('Run a simulation to generate campaign reports.')
    st.subheader('SMTP attempt summary')
    if deliveries:
        st.dataframe(pd.DataFrame(deliveries),use_container_width=True,hide_index=True)
        st.download_button('Export SMTP attempt log',csv_bytes(deliveries,['created_at','campaign','recipient_name','email','status','error']),'mailpilot-smtp-attempts.csv','text/csv')
    else:st.caption('No live SMTP attempts yet, or you are using guest demo mode.')


elif page=='Admin • Users':
    if _identity.get('role')!='owner':
        st.error('Administrator access only.');st.stop()
    st.title('Administrator — Account Management')
    st.info('Supabase Auth now manages verified registration securely. To view users, open your Supabase Dashboard → Authentication → Users.')
    st.caption('The public application uses user-scoped access tokens and cannot list all other users, by design. We do not include an elevated service-role key in Streamlit.')
    st.caption('Your owner role is linked to a verified Supabase account matching MAILPILOT_ADMIN_EMAIL in Streamlit Secrets.')

else:
    st.title('Settings & Project Guide')
    st.info('Verified accounts save to Supabase PostgreSQL with Row Level Security. Guest demo data is temporary.')
    st.info('Registered users have private Supabase data; real SMTP is disabled during the initial public security preview. Guest preview is simulation only.')
    st.subheader('How the project works')
    st.markdown('''- **Contacts:** Guests see fictional contacts; signed-in members add opted-in contacts.\n- **Campaign Studio:** Each member saves their own campaigns and wave email designs.\n- **Daily Automation:** Optional 10/day simulation; no email is sent in simulation mode.\n- **Reports:** Simulation and live SMTP delivery attempts are separate.\n- **Storage:** Verified accounts use Supabase PostgreSQL and RLS; guests use temporary SQLite.\n- **Accounts:** The owner manages users in Supabase Dashboard → Authentication → Users.\n- **Live SMTP:** Users will connect their own provider after abuse controls are completed; passwords are never stored.''')
    st.subheader('Portfolio presentation')
    st.markdown('Describe the app as a Python email campaign dashboard with personal SMTP connection and an isolated guest demo. Simulation is not real delivery or engagement.')
    st.subheader('Data management')
    st.download_button('Export all contacts',csv_bytes(contacts,['name','email','company','segment','subscribed','created_at']),'contacts-backup.csv','text/csv',disabled=not contacts)
    st.caption('Guest data is temporary. Member data is stored in Supabase. Only import consent-based contacts. Live SMTP is paused during this public security preview.')
