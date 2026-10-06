# SSAMS Installation Guide — Windows 11 CMD

Open Command Prompt (CMD) and run these commands one by one.

### 1. Go to the project folder

```cmd
cd /d G:\AMS
```

### 2. Install dependencies

```cmd
powershell -ExecutionPolicy Bypass -File "scripts\setup_windows.ps1"
```

### 3. Generate secret keys

```cmd
cd backend
.venv\Scripts\python.exe -m app.cli generate-secrets
```

Copy the generated keys into `G:\AMS\.env` under `SESSION_SECRET` and `BIOMETRIC_ENCRYPTION_KEY`. Keep these values private.

### 4. Install frontend dependencies

```cmd
cd /d G:\AMS\frontend
npm ci
```

If `package-lock.json` does not exist, use `npm install` instead.

### 5. Start the application

```cmd
cd /d G:\AMS
powershell -ExecutionPolicy Bypass -File "scripts\run_windows.ps1"
```

### 6. Create the admin account

Open a second CMD window:

```cmd
cd /d G:\AMS\backend
.venv\Scripts\python.exe -m app.cli create-admin
```

### 7. Open the website

Open your browser and visit:

**http://localhost:5173**

Keep the backend and frontend terminals open while using the application.