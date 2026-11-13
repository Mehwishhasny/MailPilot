# MailPilot Pro

A Streamlit portfolio app with owner login, self-registration, account-isolated data, campaign design, interactive charts, and simulated reports. The **public edition never sends real emails** and never asks for SMTP credentials.

## What visitors can do

1. Open the website and select **Create an account**.
2. Enter their name, email, and a unique password (minimum 12 characters), confirm it, and agree to the registration-data notice.
3. Sign in again later using the same credentials.
4. Create and save campaigns and HTML designs. Each account uses a **different SQLite database file**, so visitors cannot see another person's campaigns through the normal app interface.
5. Or click **Explore demo without an account** to use a separate, temporary fictional dataset.

## What the administrator can see

Sign in with the owner email/password and open **Admin • Users** in the sidebar. The administrator sees user ID, name, registered email, role, registration date, and last-login date. They can export that registration list. **Passwords and password hashes are never displayed by the admin page.** Passwords are salted and hashed using PBKDF2-SHA256 before being written to SQLite.

## Local setup on Windows

1. Extract this ZIP into a new folder, or back up your project first and copy `app.py`, `auth.py`, `core.py`, and `create_admin.py` into your existing *public demo* project. The project must have `requirements.txt` too.
2. Open that folder in VS Code.
3. Use Windows **Command Prompt** in the project folder:

```cmd
uv venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.venv\Scripts\python.exe create_admin.py
.venv\Scripts\python.exe -m streamlit run app.py --server.port 8502
```

If your `.venv` is already set up, you can skip the first two commands.

4. The setup script asks you to choose **your own owner login credentials**. These are for MailPilot Pro; do NOT enter your Gmail app password.
5. Open `http://localhost:8502`. Open an incognito browser window and **Create an account** as a visitor, then use your owner login in the ordinary browser to open **Admin • Users**.
6. Restart the app and confirm the visitor can still sign in. If that works locally, SQLite persistence is confirmed on your computer.

## Where SQLite saves everything

By default, alongside your `app.py`:

```text
mailpilot-data/
  accounts.sqlite3                  # Users (email, name, password digest, role, timestamps)
  account-data/
    account-1.db                   # First account's campaigns, designs, demo activity
    account-2.db                   # Second account's campaigns, designs, demo activity
    ...
```

Set the environment variable `MAILPILOT_DATA_DIR` to change the storage directory. **Do not commit this directory to GitHub**. `.gitignore` already excludes it. Back it up securely if you accept real registrations.

Existing `mailpilot.db` files from earlier releases are not overwritten. If the original public login was stored there, create your owner login again with `create_admin.py` for the new account store. If you already configured `MAILPILOT_ADMIN_EMAIL` and `MAILPILOT_ADMIN_PASSWORD` in Streamlit Secrets, the app can initialize the owner account with those values instead. Keep Secrets private.

## Deploying so user data actually persists

**DO NOT use this SQLite signup edition on free Streamlit Community Cloud for real accounts.** Streamlit Community Cloud does not guarantee the persistence of local files, so account data can disappear on restart. This project is ready for **local account testing**, not an unattended public production signup launch.

To keep SQLite for hosting, choose a web host with a **persistent mounted volume** (for example, a **paid Render web service with a persistent disk**), set `MAILPILOT_DATA_DIR=/var/data/mailpilot`, and mount the disk at `/var/data`. Keep the app and its database private to your account and never commit the database or SMTP secrets. Use this start command when deploying with Python:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
```


**Security checklist before a real public launch:** email ownership verification, password reset by verified email, signup abuse prevention/rate limiting, HTTPS, privacy notice and data deletion process, access monitoring, and encrypted backups. The current signup is an **MVP / local prototype**, not a fully audited production authentication service.

## Files

- `app.py` — Streamlit UI, login/signup, dashboard, and administrator page
- `auth.py` — SQLite authentication, password hashing, account registration
- `core.py` — account-isolated SQLite campaigns/contacts/simulations
- `create_admin.py` — interactive owner-account setup
- `requirements.txt` — Python dependencies
- `tests/` — automated checks

## Run tests

```cmd
.venv\Scripts\python.exe -m unittest discover -s tests -v
```
