@echo off
rem Klik dua kali file ini untuk menjalankan Dompy di PC. Tutup jendela hitamnya untuk menghentikan.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Menyiapkan environment pertama kali, tunggu sebentar...
    py -3 -m venv .venv || python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)

if not exist ".env" (
    echo File .env belum ada. Salin .env.example menjadi .env lalu isi GEMINI_API_KEY.
    pause
    exit /b 1
)

echo.
echo Dompy berjalan. Buka di PC: http://localhost:8501
echo Dari HP (satu WiFi): lihat "Network URL" di bawah.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless false
