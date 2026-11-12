"""Create or change a MailPilot Pro owner login on your own computer."""
from pathlib import Path
import os
from getpass import getpass
from auth import AuthStore

root=Path(__file__).resolve().parent
data_dir=Path(os.environ.get('MAILPILOT_DATA_DIR',str(root/'mailpilot-data'))).resolve()
store=AuthStore(data_dir/'accounts.sqlite3')
print('\nMAILPILOT PRO — OWNER ACCOUNT')
print('Database:',data_dir/'accounts.sqlite3')
print('Your password will not appear while you type.\n')
if not store.has_owner():
    email=input('Enter your login email: ').strip()
    first=getpass('Create a password (at least 12 characters): ')
    second=getpass('Repeat the password: ')
    if first!=second:
        print('Passwords did not match. Nothing changed.')
    else:
        try:
            store.create_owner(email,first)
        except ValueError as exc:
            print('Setup failed:',exc)
        else:
            print('Owner account created! Now start MailPilot Pro and sign in.')
else:
    print('An owner account already exists.')
    email=input('Enter your login email: ').strip()
    current=getpass('Current password: ')
    first=getpass('New password (at least 12 characters): ')
    second=getpass('Repeat the new password: ')
    if first!=second:
        print('Passwords did not match. Nothing changed.')
    else:
        try:
            changed=store.change_password(email,current,first)
            print('Password changed.' if changed else 'Current credentials were incorrect.')
        except ValueError as exc:
            print('Setup failed:',exc)
