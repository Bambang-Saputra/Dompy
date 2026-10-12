import os

MODEL_NAME = "gemini-flash-latest"  # alias Flash terbaru; bisa diganti mis. "gemini-3.6-flash"
MODEL_CADANGAN = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest"]  # dicoba berurutan kalau model utama sibuk (503/429)
TEMPERATURE = 0.4                   # rendah supaya pencatatan konsisten, tapi masih luwes saat ngobrol
THINKING_LEVEL = "low"              # "minimal", "low", "medium", "high", atau None; makin rendah makin cepat
MAX_TOOL_CALLS = 12                 # batas function call dalam satu pesan
RETRY_PERCOBAAN = 3                 # percobaan ulang otomatis per request saat Gemini sibuk
GAYA_BAHASA = "santai"              # "santai" atau "formal"
MODE_SARAN = "suportif"             # "suportif" atau "tegas"
ZONA_WAKTU = "Asia/Jakarta"         # dipakai untuk menentukan "hari ini" dan "kemarin"
RIWAYAT_CHAT_DIMUAT = 20            # jumlah pesan terakhir yang dimuat ulang saat aplikasi dibuka lagi
DATA_DIR = os.environ.get("DOMPY_DATA_DIR", "data")  # lokasi database
