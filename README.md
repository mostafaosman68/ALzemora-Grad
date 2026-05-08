# ALzemora Grad

Run the backend and frontend from two separate terminals.

## Prerequisites

- Python 3.11 or 3.12 recommended
- Node.js 18+
- MongoDB connection string
- Android Studio / Android emulator, or a connected Android device

## Backend

1. Create and activate a Python virtual environment from the project root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install Python dependencies:

```powershell
.\scripts\install_backend.ps1
```

If `py -3.12` is not found, install Python 3.12 from python.org, then recreate the virtual environment. Avoid Python 3.14 for this project because some pinned ML/scientific packages may not have compatible Windows wheels yet.

3. Create `Backend\.env`:

```env
MONGODB_URL=your_mongodb_connection_string
MONGODB_DB_NAME=elder_assist
```

4. Start the FastAPI server:

```powershell
cd Backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. Check that it is running:

- API root: `http://localhost:8000/`
- API docs: `http://localhost:8000/docs`

## Frontend

1. Open a new terminal and install dependencies:

```powershell
cd frontend
npm install
```

2. Update the backend URL in `frontend\src\config.js`.

Use one of these values:

```js
// Android emulator
export const BASE_URL = "http://10.0.2.2:8000";

// Physical phone on the same Wi-Fi network
export const BASE_URL = "http://YOUR_COMPUTER_IP:8000";
```

To find your computer IP on Windows:

```powershell
ipconfig
```

Look for the IPv4 address of your active Wi-Fi or Ethernet adapter.

3. Start Metro:

```powershell
npm start
```

4. Open another terminal and run the app:

```powershell
cd frontend
npm run android
```

For a specific connected Android device, the project also includes:

```powershell
npm run android:device
```

## Typical Run Order

1. Start MongoDB or make sure your MongoDB Atlas connection is available.
2. Start the backend with `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
3. Set `frontend\src\config.js` to the correct backend URL.
4. Start Metro with `npm start`.
5. Run the React Native app with `npm run android`.

## Troubleshooting

- If the app cannot reach the backend, make sure the phone/emulator and computer are on the same network.
- For Android emulator, use `http://10.0.2.2:8000`, not `localhost`.
- For a physical device, use your computer's local IPv4 address and keep the backend running with `--host 0.0.0.0`.
- If PowerShell blocks virtual environment activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

- If installing requirements fails while building `numpy`, check your Python version:

```powershell
python --version
```

If it shows Python 3.14, delete the current environment and recreate it with Python 3.12:

```powershell
deactivate
Remove-Item -Recurse -Force .venv
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
.\scripts\install_backend.ps1
```
