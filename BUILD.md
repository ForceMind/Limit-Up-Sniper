# Build Instructions

## 1. Windows Standalone (.exe)

To build a standalone Windows executable that users can run without installing Python:

1.  **Install PyInstaller**:
    ```bash
    pip install pyinstaller
    ```

2.  **Build the Executable**:
    Run the following command in the project root:
    ```bash
    pyinstaller build_windows.spec
    ```

3.  **Locate the Output**:
    The executable will be in `dist/LimitUpSniper/LimitUpSniper.exe`.
    You can zip the entire `dist/LimitUpSniper` folder and distribute it.

4.  **Usage**:
    -   Run `LimitUpSniper.exe`.
    -   It will automatically start the server and open your default web browser.
    -   Go to **Settings** (gear icon) -> **API Settings** to enter your DeepSeek API Key.

## 2. Android (PWA)

Since the application requires a Python backend (FastAPI, Pandas, etc.), running it natively on Android requires a Python environment.

### Option A: Progressive Web App (Recommended)
This is the easiest way. You host the server on your PC or Cloud, and access it from your phone.

1.  **Host the Server**:
    Run the server on your PC or a cloud server (e.g., `python run_desktop.py` or `uvicorn app.main:app --host 0.0.0.0`).
    *   Ensure your PC and Phone are on the same Wi-Fi.
    *   Find your PC's IP address (e.g., `ipconfig` on Windows).

2.  **Access on Android**:
    -   Open Chrome on your Android device.
    -   Navigate to `http://<YOUR_PC_IP>:8000` (e.g., `http://192.168.1.5:8000`).
    -   Tap the browser menu (three dots) -> **"Add to Home Screen"** (or "Install App").

3.  **Experience**:
    -   An icon will appear on your home screen.
    -   When opened, it will look and feel like a native app (full screen, no address bar).
    -   You can input your API Key in the Settings menu, just like on desktop.

### Option B: Run Locally on Android (Advanced)
If you truly want "local computation" on Android (no PC required), you can use **Termux**.

1.  **Install Termux** from F-Droid or Google Play.
2.  **Install Python & Git**:
    ```bash
    pkg install python git
    ```
3.  **Clone & Install**:
    ```bash
    git clone https://github.com/ForceMind/Limit-Up-Sniper.git
    cd Limit-Up-Sniper
    pip install -r requirements.txt
    ```
4.  **Run**:
    ```bash
    python run_desktop.py
    ```
5.  **Access**:
    Open Chrome and go to `http://localhost:8000`.

## Note on API Keys
-   **Server Version**: Uses the `DEEPSEEK_API_KEY` environment variable.
-   **Standalone/Client Version**: Users can manually enter their API Key in the Settings menu. This key is stored in the browser's local storage and sent with analysis requests.
