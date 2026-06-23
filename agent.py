#!/usr/bin/env python3
"""
Mini Coding Agent CLI - kaya Claude Code tapi pake model apapun via OpenRouter.

Cara pake:
    export OPENROUTER_API_KEY="sk-or-xxxx"
    python agent.py

Ganti model di config.py atau lewat env var OPENROUTER_MODEL.
"""

import os
import sys
import json
import re
import subprocess
import difflib
from datetime import datetime
from pathlib import Path

import requests
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

# ====== KONFIGURASI ======
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "qwen/qwen3-coder:free")
REVIEWER_MODEL = os.environ.get("OPENROUTER_REVIEWER_MODEL", "deepseek/deepseek-chat")

# Daftar model gratis untuk auto-fallback kalau model utama kena rate limit (429).
# Urutan = urutan coba. Daftar ini bisa berubah seiring waktu di OpenRouter,
# jadi cek openrouter.ai/models (filter Free) kalau mau update.
FALLBACK_FREE_MODELS = [
    "qwen/qwen3-coder:free",
    "openai/gpt-oss-120b:free",
    "nvidia/nemotron-3-ultra:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
]
MAX_FALLBACK_RETRIES = len(FALLBACK_FREE_MODELS)

# Model yang dipakai khusus kalau user kirim gambar (model utama/fallback di atas
# kebanyakan text-only, gak bisa "lihat" gambar). Daftar ini urutan coba, model
# pertama yang sukses dipakai. Semua gratis & support vision lewat OpenRouter.
VISION_FALLBACK_MODELS = [
    "google/gemini-2.0-flash-exp:free",
    "qwen/qwen2.5-vl-32b-instruct:free",
    "meta-llama/llama-3.2-11b-vision-instruct:free",
    "google/gemma-3-27b-it:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "qwen/qwen2.5-vl-72b-instruct:free",
]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_TOOL_ITERATIONS = 15  # batas loop biar gak infinite
HISTORY_DIR = Path.home() / ".mini_coding_agent" / "history"
MAX_HISTORY_FILES = 30  # simpan max sekian sesi terakhir

# Command yang dianggap aman (read-only / gak ngubah apapun), auto-approve.
# Dicocokkan dengan kata pertama command (case-insensitive).
SAFE_COMMANDS = {
    "ls", "pwd", "git status", "git log", "git diff", "git branch",
    "cat", "echo", "whoami", "date", "python --version", "python3 --version",
    "node --version", "java -version", "which", "find", "wc",
}

SYSTEM_PROMPT = """Kamu adalah Nexa Agent — AI assistant canggih yang berjalan di komputer user.
Kamu punya akses ke tools untuk membaca/menulis file, menjalankan command shell, browsing internet, dan mencari video YouTube.

Tanggal hari ini: 2026. Kamu WAJIB selalu mengutamakan informasi terbaru tahun 2025-2026.

ATURAN BROWSING & PENCARIAN:
- SELALU gunakan web_search untuk mencari informasi terkini. Jangan mengandalkan pengetahuan lama.
- Setelah web_search, gunakan fetch_url untuk membuka salah satu link hasil pencarian dan baca isinya secara lengkap — jangan cuma andalkan snippet.
- Jika web_search gagal, coba bing_search, lalu google_search sebagai cadangan.
- Untuk info harga, berita, teknologi terbaru — WAJIB search dulu, baru jawab.
- Saat memberikan jawaban dari hasil browsing: sebutkan sumbernya, tulis penjelasan lengkap dan akurat, dan pastikan info yang diberikan adalah yang terbaru (2025-2026).
- Jangan pernah menjawab "saya tidak tahu" tanpa mencoba web_search terlebih dahulu.

ATURAN CODING:
- Selalu baca file dulu sebelum mengedit, jangan menebak isinya.
- Gunakan search_files untuk mencari kode/teks tertentu di banyak file sebelum mengedit.
- Untuk perubahan kecil gunakan edit_file, untuk file baru gunakan write_file.
- Jalankan run_command untuk install dependency, test, compile, dsb. PENTING: selalu tambahkan flag non-interaktif (-y, --yes) agar command tidak menunggu input.

ATURAN UMUM (PENTING — JAWABAN HARUS SINGKAT):
- Default-nya SINGKAT. Jawab langsung ke intinya, tanpa basa-basi, tanpa pembukaan
  panjang, tanpa mengulang pertanyaan user.
- Sebelum memanggil tool, jelaskan dalam SATU kalimat pendek (atau langsung panggil
  tool tanpa penjelasan kalau sudah jelas konteksnya) apa yang akan kamu lakukan.
- Untuk pertanyaan simpel/perintah simpel (sapaan, cek status, satu fakta, satu
  command): jawab 1-3 kalimat saja. JANGAN bikin daftar panjang atau struktur
  proyek lengkap kecuali user benar-benar minta detail itu.
- Hanya berikan jawaban panjang/terstruktur (poin-poin, breakdown lengkap) KALAU
  user secara eksplisit minta penjelasan detail/lengkap, atau topiknya memang
  butuh banyak langkah (misal setup multi-step).
- Jangan ulangi informasi yang sudah jelas dari konteks atau hasil tool sebelumnya.
- Berhati-hati dengan command destruktif (rm -rf, dsb) — sebutkan risikonya singkat.

ATURAN GAMBAR:
- Kalau user mengirim gambar (foto), kamu otomatis dialihkan ke model vision yang
  bisa "melihat" gambar tersebut — jawab langsung berdasarkan apa yang terlihat,
  jangan bilang "saya tidak bisa melihat gambar".
- Jelaskan/jawab soal gambar secara ringkas dan langsung relevan dengan yang
  ditanya user, jangan mendeskripsikan seluruh gambar kalau user cuma tanya hal
  spesifik.

ATURAN GMAIL:
- gmail_read untuk membaca/mencari email (read-only, otomatis diizinkan).
- gmail_send untuk mengirim email — SELALU tunjukkan draft lengkap (penerima, subjek,
  isi) ke user dalam jawabanmu SEBELUM memanggil tool ini, walaupun user akan tetap
  diminta approval terpisah. Jangan pernah mengarang alamat email penerima; tanya
  ke user kalau tidak yakin alamatnya.

ATURAN CALENDAR:
- calendar_create_event dijalankan otomatis TANPA approval user (auto-approved),
  jadi kamu sendiri yang harus memastikan datanya benar sebelum memanggil tool ini.
- Kalau user minta memasukkan sesuatu yang tanggal/jamnya belum pasti (misal "jadwal
  Argentina di Piala Dunia 2026"), WAJIB web_search dulu untuk memastikan tanggal,
  jam, dan timezone yang benar — jangan pernah menebak atau pakai pengetahuan lama,
  karena hasilnya langsung masuk ke kalender asli user tanpa dicek ulang.
- Sebutkan ke user tanggal/jam yang kamu temukan SEBELUM atau SAAT memanggil tool
  ini (di kalimat penjelasanmu), supaya user tetap tahu apa yang baru saja masuk ke
  kalendernya meskipun tidak diminta approval.
- Kalau jam pasti tidak ketemu, gunakan estimasi wajar (event 2 jam) dan sebutkan
  ke user bahwa jamnya adalah estimasi, bukan jam pasti.
- Kalau timezone sumber berbeda dari timezone user dan tidak yakin cara konversinya,
  lebih baik sertakan offset timezone asli pertandingan/acara di start_time/end_time
  (contoh '-03:00' untuk Argentina) daripada menebak konversi manual yang berisiko salah.

ATURAN GOOGLE DRIVE:
- drive_list_files dan drive_read_file otomatis diizinkan (read-only, tidak bisa
  upload/edit/hapus apapun di Drive user).
- Kalau user minta "baca dokumen X" atau "cari file Y" tanpa kasih file_id,
  panggil drive_list_files dulu untuk menemukan file_id-nya, baru drive_read_file.
- Kalau ada beberapa file dengan nama serupa, tampilkan daftarnya ke user dan
  tanya mana yang dimaksud daripada menebak salah satu secara sepihak.
- drive_read_file hanya mendukung Google Docs/Sheets/Slides (lewat export
  otomatis) dan file teks biasa — kalau usernya minta baca file gambar/PDF/video,
  jelaskan bahwa tool ini belum mendukung tipe file tersebut.

ATURAN MARKETPLACE (Shopee/Tokopedia):
- marketplace_search otomatis diizinkan (read-only, cuma search, tidak ada
  aksi beli/checkout apapun — agent TIDAK BISA membeli apapun atas nama user).
- Tool ini BUKAN API resmi marketplace, cuma web search yang difilter ke
  domain Shopee/Tokopedia. WAJIB selalu sebutkan ke user bahwa harga yang
  ditampilkan adalah perkiraan dari hasil pencarian dan bisa sudah tidak
  akurat/update — user harus cek harga final di link sebelum memutuskan beli.
- Tool ini TIDAK mengembalikan gambar produk. Jangan mengarang/berpura-pura
  menampilkan gambar produk yang tidak benar-benar ada.
- Kalau hasil pencarian kosong/sedikit, coba kata kunci yang lebih umum,
  jangan mengarang produk yang tidak muncul di hasil.

ATURAN SPOTIFY:
- spotify_search otomatis diizinkan (read-only, cuma search publik, tidak
  perlu/tidak bisa akses akun Spotify user manapun).
- Tool ini TIDAK BISA mengontrol playback (play/pause/skip/dst). Kalau user
  minta "putar lagu X" atau "pause musik", jelaskan dengan jelas bahwa fitur
  ini belum tersedia (butuh Spotify Premium + login OAuth user, di luar
  cakupan tool saat ini) — cukup kasih link Spotify hasil pencarian supaya
  user bisa buka & putar manual sendiri.
- search_type default 'track' kalau user tidak spesifik mau cari lagu, artist,
  album, atau playlist.
"""

REVIEWER_SYSTEM_PROMPT = """Kamu adalah code reviewer senior. Kamu TIDAK memiliki akses ke tools apapun —
tugasmu murni membaca dan mengkritik, bukan mengeksekusi atau mengubah apapun.

Kamu akan diberi ringkasan percakapan antara user dan AI coding assistant lain (worker),
termasuk apa yang diminta user, tool apa saja yang dipanggil worker (tulis file, edit
file, jalankan command, dst beserta hasilnya), dan jawaban akhir worker ke user.

Tugasmu:
- Berikan review singkat dan tajam (maksimal 5-7 kalimat) terhadap pekerjaan worker.
- Soroti potensi bug, edge case yang terlewat, masalah keamanan, atau pendekatan yang
  kurang optimal — JANGAN hanya memuji jika memang ada yang bisa diperbaiki.
- Jika pekerjaan worker sudah baik dan tidak ada masalah berarti, katakan itu secara
  singkat dan jujur, tidak perlu mengada-ada kritik.
- Jangan mengulang apa yang sudah dikatakan worker, fokus pada hal yang BELUM disebut.
- Jawab dalam Bahasa Indonesia, gaya santai tapi tetap teknis dan to the point.
"""

# ====== DEFINISI TOOLS ======
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Membaca isi sebuah file dari disk. Gunakan ini sebelum mengedit file apapun.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relatif atau absolut ke file"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Menulis (membuat baru atau menimpa total) sebuah file dengan konten tertentu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path file yang akan ditulis"},
                    "content": {"type": "string", "description": "Konten lengkap yang akan ditulis ke file"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Mengedit file dengan cara mencari sebuah string unik dan menggantinya dengan string baru (find & replace). Lebih aman daripada menulis ulang seluruh file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path file yang akan diedit"},
                    "old_str": {"type": "string", "description": "String yang ingin dicari (harus unik & exact match di file)"},
                    "new_str": {"type": "string", "description": "String pengganti"},
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Melihat daftar file & folder di suatu direktori.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path direktori, default ke direktori saat ini"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Mencari sebuah teks/pattern di banyak file sekaligus (seperti grep). Gunakan ini untuk menemukan dimana sebuah fungsi/variabel/teks dipakai di project sebelum mengedit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Teks atau regex yang ingin dicari"},
                    "path": {"type": "string", "description": "Direktori awal pencarian, default direktori saat ini"},
                    "file_extension": {"type": "string", "description": "Filter ekstensi file, misal 'py' atau 'js'. Kosongkan untuk cari di semua file teks."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Mencari informasi di internet dengan auto-fallback: DuckDuckGo → Brave → Bing → Google. Kalau satu engine gagal/diblokir otomatis lanjut ke engine berikutnya. Gunakan ini untuk info terkini, versi library, dokumentasi API, dsb.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Kata kunci pencarian, singkat dan spesifik"},
                    "max_results": {"type": "integer", "description": "Jumlah hasil maksimal (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wikipedia_lookup",
            "description": "Mencari ringkasan/definisi sebuah konsep, istilah, teknologi, atau topik umum dari Wikipedia. Cocok untuk konsep yang relatif stabil (bukan berita/update terkini).",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topik atau istilah yang ingin dicari di Wikipedia"},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bing_search",
            "description": "Mencari di internet lewat Bing (alternatif dari web_search/DuckDuckGo). Gunakan ini sebagai cadangan jika web_search gagal atau hasilnya kurang relevan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Kata kunci pencarian, singkat dan spesifik"},
                    "max_results": {"type": "integer", "description": "Jumlah hasil maksimal (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Mengambil dan membaca isi teks lengkap dari SATU URL/halaman web spesifik (bukan hasil pencarian). Gunakan ini setelah web_search/bing_search untuk membaca isi penuh salah satu link hasil pencarian, atau jika user memberikan URL langsung.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL lengkap halaman yang ingin dibaca, contoh: https://example.com/artikel"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Menjalankan command shell (misal: jalankan compiler, test, install package) dan mengembalikan output-nya.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command shell yang akan dijalankan"}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_search",
            "description": "Mencari video di YouTube tanpa API key. Mengembalikan judul, URL, durasi, channel, dan jumlah view. Gunakan untuk menemukan video, tutorial, musik, dsb di YouTube.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Kata kunci pencarian video YouTube"},
                    "max_results": {"type": "integer", "description": "Jumlah hasil maksimal (default 5, max 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_info",
            "description": "Mengambil informasi detail sebuah video YouTube dari URL-nya: judul, deskripsi, channel, durasi, jumlah view, tanggal upload, dan thumbnail. Gunakan ini jika user memberikan URL video YouTube spesifik.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL video YouTube, contoh: https://www.youtube.com/watch?v=xxxxx"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "google_search",
            "description": "Mencari di Google (via scraping, tanpa API key). Gunakan ini sebagai alternatif web_search/bing_search untuk mendapatkan hasil Google yang lebih relevan. Kembalikan judul, URL, dan snippet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Kata kunci pencarian Google"},
                    "max_results": {"type": "integer", "description": "Jumlah hasil maksimal (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_read",
            "description": "Membaca/mencari email dari Gmail user (read-only, tidak bisa menghapus/mengubah). Gunakan untuk melihat email terbaru, mencari email dari pengirim tertentu, atau membaca isi email spesifik berdasarkan query pencarian Gmail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Query pencarian Gmail, contoh: 'from:boss@company.com', 'is:unread', 'subject:invoice'. Kosongkan untuk inbox terbaru."},
                    "max_results": {"type": "integer", "description": "Jumlah email maksimal (default 5, max 20)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_send",
            "description": "Mengirim email lewat akun Gmail user. SELALU minta izin eksplisit ke user dan tunjukkan draft lengkap (penerima, subjek, isi) sebelum memanggil tool ini — jangan pernah kirim email tanpa user tahu isinya secara jelas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Alamat email penerima"},
                    "subject": {"type": "string", "description": "Subjek email"},
                    "body": {"type": "string", "description": "Isi email (plain text)"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create_event",
            "description": (
                "Membuat event baru di Google Calendar user. Gunakan ini setelah user minta "
                "memasukkan sesuatu ke kalender (misal jadwal pertandingan, meeting, deadline) "
                "— cari tanggal/jamnya dulu pakai web_search kalau user belum kasih tanggal pasti, "
                "baru panggil tool ini. Tool ini otomatis dijalankan tanpa konfirmasi tambahan "
                "(read-only secara sosial: hanya menambah event ke kalender user sendiri, tidak "
                "mengirim apapun ke pihak luar), jadi pastikan tanggal/jam yang kamu masukkan benar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Judul/nama event, contoh: 'Argentina vs Prancis - Piala Dunia 2026'"},
                    "start_time": {"type": "string", "description": "Waktu mulai dalam format ISO 8601, contoh: '2026-06-25T19:00:00'. Sertakan offset timezone kalau diketahui, contoh '2026-06-25T19:00:00-03:00'; kalau tidak ada offset, dianggap waktu lokal timezone default kalender user."},
                    "end_time": {"type": "string", "description": "Waktu selesai dalam format ISO 8601. Kalau tidak diketahui durasinya, gunakan start_time + 2 jam sebagai estimasi wajar (misal untuk pertandingan olahraga)."},
                    "description": {"type": "string", "description": "Deskripsi/catatan tambahan untuk event ini, misal sumber info atau link berita yang dipakai. Opsional."},
                    "location": {"type": "string", "description": "Lokasi event (opsional), misal nama stadion/kota."},
                },
                "required": ["title", "start_time", "end_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drive_list_files",
            "description": (
                "Mencari/list file & folder di Google Drive user (read-only, tidak bisa "
                "mengubah/menghapus/upload apapun). Gunakan untuk menemukan file berdasarkan "
                "nama, tipe, atau yang baru-baru diubah, sebelum membaca isinya dengan "
                "drive_read_file. Hasil berisi file_id yang dipakai untuk drive_read_file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Kata kunci nama file yang dicari (kosongkan untuk list file terbaru). Pencarian berdasarkan nama file, tidak case-sensitive."},
                    "max_results": {"type": "integer", "description": "Jumlah file maksimal (default 10, max 30)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drive_read_file",
            "description": (
                "Membaca isi sebuah file di Google Drive user berdasarkan file_id (read-only). "
                "Mendukung Google Docs, Google Sheets (diekspor jadi text/CSV), dan file teks "
                "biasa (.txt, .md, .csv, dst). File biner non-teks (gambar, video, PDF kompleks) "
                "tidak didukung dan akan mengembalikan error. Cari file_id dulu lewat "
                "drive_list_files kalau belum tahu."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string", "description": "ID file Google Drive, didapat dari hasil drive_list_files."},
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "marketplace_search",
            "description": (
                "Mencari produk di marketplace Indonesia (Shopee & Tokopedia) lewat web search "
                "biasa (BUKAN API resmi, jadi hasil harga bisa kurang akurat/update — selalu "
                "sebutkan ke user bahwa harga final harus dicek lagi di link sebelum beli). "
                "Cocok untuk permintaan seperti 'rekomendasi PC 5 jutaan', 'cari sepatu running "
                "murah', dll. Mengembalikan judul produk, harga (kalau muncul di snippet "
                "pencarian), dan link ke halaman produk Shopee/Tokopedia. Tool ini TIDAK bisa "
                "mengambil gambar produk."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Kata kunci produk yang dicari, contoh: 'PC rakitan 5 jutaan', 'sepatu lari pria'"},
                    "platform": {"type": "string", "description": "Filter platform: 'shopee', 'tokopedia', atau 'semua' (default, cari di keduanya)", "enum": ["shopee", "tokopedia", "semua"]},
                    "max_results": {"type": "integer", "description": "Jumlah hasil maksimal (default 6, max 15)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_search",
            "description": (
                "Mencari lagu, artist, album, atau playlist di Spotify (search publik, tidak "
                "perlu login akun Spotify user). Mengembalikan judul, nama artist, album, dan "
                "link Spotify untuk dibuka/diputar. Tool ini TIDAK bisa mengontrol playback "
                "(play/pause/skip) — Spotify Web API mensyaratkan akun Premium dan login OAuth "
                "user untuk itu, di luar cakupan tool ini."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Kata kunci pencarian, contoh: 'Bohemian Rhapsody Queen', 'Tulus', 'lo-fi study playlist'"},
                    "search_type": {"type": "string", "description": "Tipe hasil yang dicari: 'track' (lagu), 'artist', 'album', atau 'playlist'. Default 'track'.", "enum": ["track", "artist", "album", "playlist"]},
                    "max_results": {"type": "integer", "description": "Jumlah hasil maksimal (default 5, max 20)"},
                },
                "required": ["query"],
            },
        },
    },
]


# ====== IMPLEMENTASI TOOLS ======
def tool_read_file(path: str) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return f"ERROR: file '{path}' tidak ditemukan."
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"


def tool_write_file(path: str, content: str) -> str:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK: file '{path}' berhasil ditulis ({len(content)} karakter)."
    except Exception as e:
        return f"ERROR: {e}"


def tool_edit_file(path: str, old_str: str, new_str: str) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return f"ERROR: file '{path}' tidak ditemukan."
        text = p.read_text(encoding="utf-8")
        count = text.count(old_str)
        if count == 0:
            return "ERROR: old_str tidak ditemukan di file. Cek lagi isi file dengan read_file."
        if count > 1:
            return f"ERROR: old_str muncul {count} kali, harus unik. Perbesar konteks old_str."
        new_text = text.replace(old_str, new_str)
        p.write_text(new_text, encoding="utf-8")
        return f"OK: file '{path}' berhasil diedit."
    except Exception as e:
        return f"ERROR: {e}"


def load_gitignore_patterns(base_path: Path) -> list:
    """Baca .gitignore (kalau ada) di base_path, return list pattern fnmatch sederhana."""
    gitignore_file = base_path / ".gitignore"
    patterns = []
    if gitignore_file.exists():
        try:
            for line in gitignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line.rstrip("/"))
        except Exception:
            pass
    return patterns


def is_gitignored(name: str, patterns: list) -> bool:
    """Cek nama file/folder cocok dengan salah satu pattern .gitignore (pakai fnmatch sederhana)."""
    import fnmatch
    for pat in patterns:
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(name, f"*/{pat}") or name == pat:
            return True
    return False


def tool_list_dir(path: str = ".") -> str:
    try:
        p = Path(path)
        gitignore_patterns = load_gitignore_patterns(p)
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        lines = []
        skipped = 0
        for item in items:
            if item.name in SKIP_DIRS or is_gitignored(item.name, gitignore_patterns):
                skipped += 1
                continue
            marker = "/" if item.is_dir() else ""
            lines.append(f"{item.name}{marker}")
        result = "\n".join(lines) if lines else "(direktori kosong / semua di-skip)"
        if skipped:
            result += f"\n\n({skipped} item di-skip karena ada di .gitignore atau folder umum seperti node_modules/.git)"
        return result
    except Exception as e:
        return f"ERROR: {e}"


SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", ".mini_coding_agent"}


def tool_search_files(pattern: str, path: str = ".", file_extension: str = "") -> str:
    try:
        base = Path(path)
        if not base.exists():
            return f"ERROR: direktori '{path}' tidak ditemukan."

        try:
            regex = re.compile(pattern)
        except re.error:
            regex = re.compile(re.escape(pattern))  # fallback: treat sebagai literal text

        ext = file_extension.lstrip(".").lower() if file_extension else None
        gitignore_patterns = load_gitignore_patterns(base)
        matches = []
        files_scanned = 0
        files_skipped = 0

        for root, dirs, files in os.walk(base):
            dirs[:] = [
                d for d in dirs
                if d not in SKIP_DIRS and not d.startswith(".")
                and not is_gitignored(d, gitignore_patterns)
            ]
            for fname in files:
                if ext and not fname.lower().endswith(f".{ext}"):
                    continue
                if is_gitignored(fname, gitignore_patterns):
                    files_skipped += 1
                    continue
                fpath = Path(root) / fname
                try:
                    text = fpath.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                files_scanned += 1
                for i, line in enumerate(text.splitlines(), start=1):
                    if regex.search(line):
                        matches.append(f"{fpath}:{i}: {line.strip()[:150]}")
                        if len(matches) >= 200:
                            break
                if len(matches) >= 200:
                    break
            if len(matches) >= 200:
                break

        if not matches:
            return f"Tidak ditemukan match untuk '{pattern}' ({files_scanned} file di-scan, {files_skipped} di-skip karena .gitignore)."
        header = f"Ditemukan {len(matches)} match (di {files_scanned} file di-scan, {files_skipped} di-skip karena .gitignore):\n"
        return header + "\n".join(matches)
    except Exception as e:
        return f"ERROR: {e}"


def make_diff(old_text: str, new_text: str, path: str) -> str:
    """Bikin unified diff yang manusiawi buat ditampilkan di permission prompt."""
    diff = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"{path} (sebelum)",
        tofile=f"{path} (sesudah)",
        n=2,
    )
    return "".join(diff)


def _search_tavily(query: str, max_results: int) -> list:
    """Cari via Tavily API — paling akurat, dirancang buat AI agent."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        raise Exception("TAVILY_API_KEY belum diset")
    resp = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": query, "max_results": max_results, "search_depth": "basic"},
        timeout=15
    )
    if resp.status_code != 200:
        raise Exception(f"Status {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    results = data.get("results", [])
    if not results:
        raise Exception("Tidak ada hasil")
    return [(r.get("title",""), r.get("url",""), (r.get("content","") or "")[:400]) for r in results]


def _search_searchapi(query: str, max_results: int) -> list:
    """Cari via SearchAPI.io — Google Search results."""
    api_key = os.environ.get("SEARCHAPI_KEY", "")
    if not api_key:
        raise Exception("SEARCHAPI_KEY belum diset")
    resp = requests.get(
        "https://www.searchapi.io/api/v1/search",
        params={"engine": "google", "q": query, "api_key": api_key, "num": max_results},
        timeout=15
    )
    if resp.status_code != 200:
        raise Exception(f"Status {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    results = data.get("organic_results", [])
    if not results:
        raise Exception("Tidak ada hasil")
    return [(r.get("title",""), r.get("link",""), (r.get("snippet","") or "")[:400]) for r in results[:max_results]]


def _search_duckduckgo(query: str, max_results: int) -> list:
    """Cari via DuckDuckGo."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        raise Exception("duckduckgo-search belum terinstall")
    ddgs = DDGS()
    results = list(ddgs.text(query, max_results=max_results))
    if not results:
        raise Exception("Tidak ada hasil")
    return [(r.get("title",""), r.get("href",""), (r.get("body","") or "")[:300]) for r in results]


def _search_brave(query: str, max_results: int) -> list:
    """Cari via Brave Search (scraping, tanpa API key)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
    }
    q = requests.utils.quote(query)
    resp = requests.get(f"https://search.brave.com/search?q={q}&count={max_results}",
                        headers=headers, timeout=15)
    if resp.status_code != 200:
        raise Exception(f"Status {resp.status_code}")
    html = resp.text
    # Ekstrak hasil dari Brave
    blocks = re.findall(r'<div class="snippet[^"]*".*?</div>\s*</div>', html, re.DOTALL)
    if not blocks:
        # fallback pattern
        titles = re.findall(r'<span class="snippet-title[^"]*">(.*?)</span>', html, re.DOTALL)
        urls = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*class="[^"]*result[^"]*"', html)
        snippets = re.findall(r'<p class="snippet-description[^"]*">(.*?)</p>', html, re.DOTALL)
        if not titles:
            raise Exception("Tidak bisa parse hasil Brave")
        def clean(t): return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', t)).strip()
        results = []
        for i in range(min(len(titles), max_results)):
            results.append((clean(titles[i]), urls[i] if i < len(urls) else "", clean(snippets[i]) if i < len(snippets) else ""))
        return results
    def clean(t): return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', t)).strip()
    results = []
    for block in blocks[:max_results]:
        title_m = re.search(r'<span[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        url_m = re.search(r'href="(https?://[^"]+)"', block)
        snippet_m = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        title = clean(title_m.group(1)) if title_m else "(tanpa judul)"
        url = url_m.group(1) if url_m else ""
        snippet = clean(snippet_m.group(1))[:300] if snippet_m else ""
        if url:
            results.append((title, url, snippet))
    if not results:
        raise Exception("Tidak ada hasil dari Brave")
    return results


def _search_bing(query: str, max_results: int) -> list:
    """Cari via Bing scraping."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    q = requests.utils.quote(query)
    resp = requests.get(f"https://www.bing.com/search?q={q}", headers=headers, timeout=15)
    if resp.status_code != 200:
        raise Exception(f"Status {resp.status_code}")
    blocks = re.findall(r'<li class="b_algo".*?</li>', resp.text, re.DOTALL)
    if not blocks:
        raise Exception("Tidak ada hasil Bing")
    def clean(t): return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', t or '')).strip()
    results = []
    for block in blocks[:max_results]:
        title_m = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        snippet_m = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        href = title_m.group(1) if title_m else ""
        title = clean(title_m.group(2)) if title_m else "(tanpa judul)"
        snippet = clean(snippet_m.group(1))[:300] if snippet_m else ""
        if href:
            results.append((title, href, snippet))
    if not results:
        raise Exception("Gagal parse Bing")
    return results


def _search_google(query: str, max_results: int) -> list:
    """Cari via Google scraping."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "id-ID,id;q=0.9",
    }
    q = requests.utils.quote(query)
    resp = requests.get(f"https://www.google.com/search?q={q}&num={max_results}&hl=id",
                        headers=headers, timeout=15)
    if resp.status_code != 200:
        raise Exception(f"Status {resp.status_code}")
    def clean(t): return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', t or '')).strip()
    results = []
    title_urls = re.findall(r'<h3[^>]*>(.*?)</h3>.*?<a[^>]+href="([^"&]+)"', resp.text, re.DOTALL)
    snippets = re.findall(r'<div[^>]*class="[^"]*VwiC3b[^"]*"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
    for i, (title, url) in enumerate(title_urls[:max_results]):
        snippet = clean(snippets[i]) if i < len(snippets) else ""
        decoded_url = requests.utils.unquote(url.split("&")[0])
        if decoded_url.startswith("http"):
            results.append((clean(title), decoded_url, snippet[:300]))
    if not results:
        raise Exception("Gagal parse Google")
    return results


def tool_web_search(query: str, max_results: int = 5) -> str:
    """
    Web search dengan auto-fallback: Tavily → SearchAPI → DuckDuckGo → Brave → Bing → Google.
    Kalau satu gagal/diblokir, otomatis coba yang berikutnya.
    """
    max_results = max(1, min(int(max_results), 10))
    engines = [
        ("Tavily",      _search_tavily),
        ("SearchAPI",   _search_searchapi),
        ("DuckDuckGo",  _search_duckduckgo),
        ("Brave",       _search_brave),
        ("Bing",        _search_bing),
        ("Google",      _search_google),
    ]
    last_error = ""
    for name, fn in engines:
        try:
            results = fn(query, max_results)
            lines = [f"Hasil pencarian {name} untuk '{query}':\n"]
            for i, (title, href, snippet) in enumerate(results, 1):
                lines.append(f"{i}. {title}\n   URL: {href}\n   {snippet}\n")
            return "\n".join(lines)
        except Exception as e:
            last_error = f"{name}: {e}"
            continue
    return (f"ERROR: semua search engine gagal untuk '{query}'.\n"
            f"Error terakhir: {last_error}")


def tool_wikipedia_lookup(topic: str) -> str:
    """Ambil ringkasan topik dari Wikipedia REST API (bahasa Indonesia, fallback ke Inggris)."""
    headers = {"User-Agent": "MiniCodingAgentCLI/1.0"}

    def fetch(lang: str):
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(topic)}"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return None

    try:
        data = fetch("id")
        lang_used = "id"
        if not data or data.get("type") == "disambiguation":
            data = fetch("en")
            lang_used = "en"

        if not data:
            return f"Tidak ditemukan artikel Wikipedia untuk '{topic}'."

        extract = data.get("extract", "")
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        if not extract:
            return f"Artikel ditemukan tapi tidak ada ringkasan untuk '{topic}'. URL: {page_url}"

        return f"[Wikipedia-{lang_used}] {data.get('title', topic)}\n\n{extract}\n\nSumber: {page_url}"
    except requests.RequestException as e:
        return f"ERROR: gagal mengakses Wikipedia ({e})."
    except Exception as e:
        return f"ERROR: {e}"


def tool_bing_search(query: str, max_results: int = 5) -> str:
    """
    Web search via Bing, TANPA API key (scraping HTML langsung).
    Fallback kalau web_search (DuckDuckGo) gagal/limit. Bisa berhenti bekerja
    sewaktu-waktu kalau Bing mengubah struktur HTML mereka atau memblokir request.
    """
    try:
        max_results = max(1, min(int(max_results), 10))
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        url = "https://www.bing.com/search"
        resp = requests.get(url, headers=headers, params={"q": query}, timeout=15)

        if resp.status_code != 200:
            return f"ERROR: Bing mengembalikan status {resp.status_code} (mungkin diblokir/rate-limited). Coba web_search (DuckDuckGo) sebagai alternatif."

        html = resp.text

        # Pola sederhana: tiap hasil organik Bing ada di blok <li class="b_algo">...</li>
        blocks = re.findall(r'<li class="b_algo".*?</li>', html, re.DOTALL)
        if not blocks:
            return f"Tidak ditemukan hasil dari Bing untuk '{query}' (kemungkinan struktur halaman berubah atau diblokir). Coba web_search (DuckDuckGo) sebagai alternatif."

        results = []
        for block in blocks[:max_results]:
            title_match = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)

            def clean(text):
                text = re.sub(r'<[^>]+>', '', text or '')
                return re.sub(r'\s+', ' ', text).strip()

            href = title_match.group(1) if title_match else ""
            title = clean(title_match.group(2)) if title_match else "(tanpa judul)"
            snippet = clean(snippet_match.group(1))[:300] if snippet_match else ""
            results.append((title, href, snippet))

        if not results:
            return f"Hasil ditemukan tapi gagal di-parse untuk '{query}'. Coba web_search (DuckDuckGo) sebagai alternatif."

        lines = [f"Hasil pencarian Bing untuk '{query}':\n"]
        for i, (title, href, snippet) in enumerate(results, start=1):
            lines.append(f"{i}. {title}\n   URL: {href}\n   {snippet}\n")
        return "\n".join(lines)
    except requests.RequestException as e:
        return f"ERROR: gagal mengakses Bing ({e}). Coba web_search (DuckDuckGo) sebagai alternatif."
    except Exception as e:
        return f"ERROR: {e}"


MAX_FETCH_URL_CHARS = 5000


def tool_fetch_url(url: str) -> str:
    """
    Ambil isi teks dari satu URL spesifik (bukan hasil pencarian, tapi 1 halaman utuh).
    HTML di-strip jadi teks polos pakai regex sederhana (tanpa render JS, tanpa BeautifulSoup).
    """
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200:
            return f"ERROR: gagal mengambil URL, status {resp.status_code}."

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type and "text" not in content_type:
            return f"ERROR: konten bukan halaman teks/HTML (Content-Type: {content_type}), tidak bisa diekstrak."

        html = resp.text

        # Hapus script, style, dan comment dulu biar gak ikut keluar sebagai "teks"
        html = re.sub(r'<script.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<!--.*?-->', ' ', html, flags=re.DOTALL)

        # Ambil judul kalau ada
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
        title = re.sub(r'\s+', ' ', title_match.group(1)).strip() if title_match else "(tanpa judul)"

        # Strip semua tag HTML sisanya jadi teks polos
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&quot;', '"', text)
        text = re.sub(r'&#39;', "'", text)
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text).strip()

        truncated_note = ""
        if len(text) > MAX_FETCH_URL_CHARS:
            text = text[:MAX_FETCH_URL_CHARS]
            truncated_note = f"\n\n...(dipotong, halaman lebih panjang dari {MAX_FETCH_URL_CHARS} karakter)"

        return f"Judul: {title}\nURL: {url}\n\n{text}{truncated_note}"
    except requests.RequestException as e:
        return f"ERROR: gagal mengakses URL ({e})."
    except Exception as e:
        return f"ERROR: {e}"


RUN_COMMAND_TIMEOUT_SECONDS = 1200  # 20 menit, untuk command panjang seperti pkg/apt install, build, compile


def tool_run_command(command: str) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=RUN_COMMAND_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,  # stdin ditutup -> command yang nanya input interaktif
                                       # akan langsung gagal/exit, bukan nyangkut diam2 sampai timeout
        )
        output = f"exit_code: {result.returncode}\n"
        if result.stdout:
            output += f"stdout:\n{result.stdout[-3000:]}\n"
        if result.stderr:
            output += f"stderr:\n{result.stderr[-3000:]}\n"
        return output
    except subprocess.TimeoutExpired as e:
        partial_out = (e.stdout or "")[-1500:] if e.stdout else ""
        partial_err = (e.stderr or "")[-1500:] if e.stderr else ""
        minutes = RUN_COMMAND_TIMEOUT_SECONDS // 60
        msg = (
            f"ERROR: command timeout setelah {minutes} menit (belum selesai juga). "
            f"Kemungkinan command butuh waktu sangat lama, atau (jika ini command interaktif "
            f"seperti instalasi yang menunggu konfirmasi 'Y/n') sudah otomatis dijawab tidak "
            f"karena stdin ditutup. Coba tambahkan flag non-interaktif seperti -y atau "
            f"--yes pada command (contoh: 'apt install -y nama_paket')."
        )
        if partial_out:
            msg += f"\n\nOutput sejauh ini (stdout):\n{partial_out}"
        if partial_err:
            msg += f"\n\nOutput sejauh ini (stderr):\n{partial_err}"
        return msg
    except Exception as e:
        return f"ERROR: {e}"


def tool_youtube_search(query: str, max_results: int = 5) -> str:
    """
    Cari video YouTube tanpa API key, pakai yt-dlp (kalau ada) atau scraping HTML.
    Fallback ke scraping kalau yt-dlp belum diinstall.
    """
    max_results = max(1, min(int(max_results), 10))

    # Coba pakai yt-dlp dulu (lebih reliable)
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlist_items": f"1:{max_results}",
        }
        search_url = f"ytsearch{max_results}:{query}"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_url, download=False)
        entries = info.get("entries", [])
        if not entries:
            return f"Tidak ada hasil YouTube untuk '{query}'."
        lines = [f"Hasil pencarian YouTube untuk '{query}':\n"]
        for i, e in enumerate(entries, 1):
            title = e.get("title", "(tanpa judul)")
            url = f"https://www.youtube.com/watch?v={e.get('id', '')}"
            channel = e.get("uploader") or e.get("channel") or "Unknown"
            duration = e.get("duration")
            dur_str = f"{int(duration) // 60}:{int(duration) % 60:02d}" if duration else "?"
            views = e.get("view_count")
            view_str = f"{int(views):,}" if views else "?"
            lines.append(f"{i}. {title}\n   URL: {url}\n   Channel: {channel} | Durasi: {dur_str} | Views: {view_str}\n")
        return "\n".join(lines)
    except ImportError:
        pass  # yt-dlp belum ada, coba scraping
    except Exception as e:
        return f"ERROR yt-dlp: {e}\nCoba install: pip install yt-dlp"

    # Fallback: scraping YouTube search page
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        }
        q = requests.utils.quote(query)
        resp = requests.get(f"https://www.youtube.com/results?search_query={q}", headers=headers, timeout=15)
        if resp.status_code != 200:
            return f"ERROR: YouTube mengembalikan status {resp.status_code}."

        # Ekstrak data dari ytInitialData JSON yang ada di dalam HTML
        match = re.search(r'var ytInitialData\s*=\s*(\{.*?\});</script>', resp.text, re.DOTALL)
        if not match:
            return ("ERROR: Tidak bisa parse hasil YouTube (struktur HTML berubah). "
                    "Install yt-dlp untuk hasil lebih stabil: pip install yt-dlp")

        data = json.loads(match.group(1))
        contents = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        results = []
        for section in contents:
            items = section.get("itemSectionRenderer", {}).get("contents", [])
            for item in items:
                vr = item.get("videoRenderer")
                if not vr:
                    continue
                vid_id = vr.get("videoId", "")
                title = "".join(
                    t.get("text", "") for t in
                    vr.get("title", {}).get("runs", [])
                )
                channel = "".join(
                    t.get("text", "") for t in
                    vr.get("ownerText", {}).get("runs", [])
                )
                duration = vr.get("lengthText", {}).get("simpleText", "?")
                views = vr.get("viewCountText", {}).get("simpleText", "?")
                results.append({
                    "title": title, "id": vid_id,
                    "channel": channel, "duration": duration, "views": views
                })
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break

        if not results:
            return f"Tidak ada hasil YouTube untuk '{query}'."

        lines = [f"Hasil pencarian YouTube untuk '{query}':\n"]
        for i, r in enumerate(results, 1):
            url = f"https://www.youtube.com/watch?v={r['id']}"
            lines.append(
                f"{i}. {r['title']}\n"
                f"   URL: {url}\n"
                f"   Channel: {r['channel']} | Durasi: {r['duration']} | Views: {r['views']}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return (f"ERROR: gagal scraping YouTube ({e}). "
                f"Install yt-dlp untuk hasil lebih reliable: pip install yt-dlp")


def tool_youtube_info(url: str) -> str:
    """
    Ambil info detail satu video YouTube dari URL-nya.
    Pakai yt-dlp kalau ada, fallback ke scraping oEmbed API.
    """
    # Normalisasi URL
    if "youtu.be/" in url:
        vid_id = url.split("youtu.be/")[-1].split("?")[0]
        url = f"https://www.youtube.com/watch?v={vid_id}"

    # Coba yt-dlp dulu
    try:
        import yt_dlp
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        duration = info.get("duration", 0)
        dur_str = f"{duration // 60}:{duration % 60:02d}" if duration else "?"
        views = info.get("view_count")
        likes = info.get("like_count")
        desc = (info.get("description") or "")[:500]
        if len(info.get("description") or "") > 500:
            desc += "\n...(dipotong)"
        return (
            f"Judul: {info.get('title')}\n"
            f"Channel: {info.get('uploader')} ({info.get('channel_url', '')})\n"
            f"Durasi: {dur_str}\n"
            f"Views: {views:,}\n" if views else f"Views: ?\n"
            f"Likes: {likes:,}\n" if likes else f"Likes: ?\n"
            f"Upload: {info.get('upload_date', '?')}\n"
            f"URL: {url}\n"
            f"Thumbnail: {info.get('thumbnail', '?')}\n\n"
            f"Deskripsi:\n{desc}"
        )
    except ImportError:
        pass
    except Exception as e:
        return f"ERROR yt-dlp: {e}"

    # Fallback: YouTube oEmbed API (info terbatas tapi tanpa API key)
    try:
        oembed_url = f"https://www.youtube.com/oembed?url={requests.utils.quote(url)}&format=json"
        resp = requests.get(oembed_url, timeout=10)
        if resp.status_code != 200:
            return f"ERROR: Tidak bisa ambil info video (status {resp.status_code}). URL mungkin salah atau video private."
        d = resp.json()
        return (
            f"Judul: {d.get('title')}\n"
            f"Channel: {d.get('author_name')} ({d.get('author_url', '')})\n"
            f"Thumbnail: {d.get('thumbnail_url', '?')}\n"
            f"URL: {url}\n\n"
            f"(Info terbatas — install yt-dlp untuk detail lengkap: pip install yt-dlp)"
        )
    except Exception as e:
        return f"ERROR: gagal ambil info video YouTube ({e})."


def _gmail_extract_header(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _gmail_extract_body(payload: dict) -> str:
    """Ambil bagian text/plain dari payload Gmail (handle nested multipart)."""
    import base64

    def decode(data: str) -> str:
        try:
            return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")
        except Exception:
            return ""

    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return decode(payload["body"]["data"])

    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return decode(part["body"]["data"])
    # Fallback: cari rekursif kalau ada nested multipart
    for part in payload.get("parts", []) or []:
        result = _gmail_extract_body(part)
        if result:
            return result
    return "(tidak ada isi text/plain, mungkin email HTML-only)"


def tool_gmail_read(query: str = "", max_results: int = 5) -> str:
    """
    Baca/cari email dari Gmail user (read-only, scope gmail.readonly saja).
    query pakai sintaks pencarian Gmail biasa (kosong = inbox terbaru).
    """
    try:
        import gmail_auth
    except ImportError:
        return "ERROR: modul gmail_auth.py tidak ditemukan di folder project."

    try:
        service = gmail_auth.get_gmail_service()
    except gmail_auth.GmailNotConfigured as e:
        return f"ERROR: Gmail belum di-setup. {e}"
    except Exception as e:
        return f"ERROR: gagal autentikasi Gmail ({e})."

    max_results = min(max(1, max_results), 20)
    try:
        list_resp = service.users().messages().list(
            userId="me", q=query or "", maxResults=max_results
        ).execute()
        msg_refs = list_resp.get("messages", [])
        if not msg_refs:
            return f"Tidak ada email yang cocok dengan query '{query}'." if query else "Inbox kosong."

        lines = [f"Email terbaru{f' (query: {query})' if query else ''}:\n"]
        for i, ref in enumerate(msg_refs, 1):
            full = service.users().messages().get(
                userId="me", id=ref["id"], format="full"
            ).execute()
            headers = full.get("payload", {}).get("headers", [])
            subject = _gmail_extract_header(headers, "Subject") or "(tanpa subjek)"
            sender = _gmail_extract_header(headers, "From")
            date = _gmail_extract_header(headers, "Date")
            snippet = full.get("snippet", "")
            lines.append(
                f"{i}. Dari: {sender}\n"
                f"   Subjek: {subject}\n"
                f"   Tanggal: {date}\n"
                f"   Cuplikan: {snippet}\n"
                f"   (message_id: {ref['id']})\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: gagal membaca Gmail ({e})."


def tool_gmail_send(to: str, subject: str, body: str) -> str:
    """
    Kirim email lewat akun Gmail user (scope gmail.send saja, tidak bisa baca/hapus).
    Tool ini SELALU melewati ask_permission terlebih dahulu di run_agent_turn,
    tidak pernah masuk SAFE_TOOLS — lihat definisi SAFE_TOOLS di bawah.
    """
    try:
        import gmail_auth
    except ImportError:
        return "ERROR: modul gmail_auth.py tidak ditemukan di folder project."

    try:
        service = gmail_auth.get_gmail_service()
    except gmail_auth.GmailNotConfigured as e:
        return f"ERROR: Gmail belum di-setup. {e}"
    except Exception as e:
        return f"ERROR: gagal autentikasi Gmail ({e})."

    import base64
    from email.mime.text import MIMEText

    try:
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Email berhasil dikirim ke {to}. Subjek: '{subject}'. (message_id: {sent.get('id')})"
    except Exception as e:
        return f"ERROR: gagal mengirim email ({e})."


def tool_calendar_create_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
) -> str:
    """
    Bikin event baru di Google Calendar user (scope calendar.events saja,
    tidak bisa menghapus kalender atau ubah setting kalender lain).
    Tool ini masuk SAFE_TOOLS (auto-approve) — lihat catatan di SAFE_TOOLS
    kenapa ini dianggap beda risikonya dari gmail_send.
    """
    try:
        import gmail_auth
    except ImportError:
        return "ERROR: modul gmail_auth.py tidak ditemukan di folder project."

    try:
        service = gmail_auth.get_calendar_service()
    except gmail_auth.GmailNotConfigured as e:
        return f"ERROR: Google Calendar belum di-setup. {e}"
    except Exception as e:
        return f"ERROR: gagal autentikasi Google Calendar ({e})."

    event_body = {
        "summary": title,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
    }
    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location

    try:
        created = service.events().insert(calendarId="primary", body=event_body).execute()
        link = created.get("htmlLink", "")
        return (
            f"Event berhasil dibuat: '{title}'\n"
            f"Mulai: {start_time}\n"
            f"Selesai: {end_time}\n"
            f"Link: {link}"
        )
    except Exception as e:
        return f"ERROR: gagal membuat event kalender ({e}). Pastikan format start_time/end_time ISO 8601 valid."



def tool_drive_list_files(query: str = "", max_results: int = 10) -> str:
    """
    List/cari file di Google Drive user (scope drive.readonly saja, tidak bisa
    upload/edit/hapus apapun).
    """
    try:
        import gmail_auth
    except ImportError:
        return "ERROR: modul gmail_auth.py tidak ditemukan di folder project."

    try:
        service = gmail_auth.get_drive_service()
    except gmail_auth.GmailNotConfigured as e:
        return f"ERROR: Google Drive belum di-setup. {e}"
    except Exception as e:
        return f"ERROR: gagal autentikasi Google Drive ({e})."

    max_results = min(max(1, max_results), 30)
    try:
        params = {
            "pageSize": max_results,
            "fields": "files(id, name, mimeType, modifiedTime, size, webViewLink)",
            "orderBy": "modifiedTime desc",
        }
        if query:
            # escape single quote biar gak rusak query Drive API
            safe_query = query.replace("'", "\\'")
            params["q"] = f"name contains '{safe_query}' and trashed = false"
        else:
            params["q"] = "trashed = false"

        results = service.files().list(**params).execute()
        files = results.get("files", [])
        if not files:
            return f"Tidak ada file yang cocok dengan '{query}'." if query else "Drive kosong atau tidak ada file."

        header_label = f" (cari: '{query}')" if query else " (terbaru)"
        lines = [f"File di Drive{header_label}:\n"]
        for i, f in enumerate(files, 1):
            size = f.get("size")
            size_str = f"{int(size):,} bytes".replace(",", ".") if size else "(folder/Google Doc, tanpa ukuran file biasa)"
            lines.append(
                f"{i}. {f.get('name')}\n"
                f"   Tipe: {f.get('mimeType')}\n"
                f"   Diubah: {f.get('modifiedTime')}\n"
                f"   Ukuran: {size_str}\n"
                f"   file_id: {f.get('id')}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: gagal mengambil daftar file Drive ({e})."


# Mapping mimeType Google Workspace -> mimeType ekspor teks yang didukung Drive API
_DRIVE_EXPORT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}
# Batas karakter yang dikembalikan ke model, biar gak membanjiri context window
_DRIVE_READ_MAX_CHARS = 15000


def tool_drive_read_file(file_id: str) -> str:
    """
    Baca isi file Google Drive (Google Docs/Sheets/Slides via export, atau file
    teks biasa via download langsung). Read-only, scope drive.readonly saja.
    """
    try:
        import gmail_auth
    except ImportError:
        return "ERROR: modul gmail_auth.py tidak ditemukan di folder project."

    try:
        service = gmail_auth.get_drive_service()
    except gmail_auth.GmailNotConfigured as e:
        return f"ERROR: Google Drive belum di-setup. {e}"
    except Exception as e:
        return f"ERROR: gagal autentikasi Google Drive ({e})."

    try:
        meta = service.files().get(fileId=file_id, fields="name, mimeType, size").execute()
    except Exception as e:
        return f"ERROR: gagal mengambil metadata file ({e}). Pastikan file_id benar (cari lewat drive_list_files)."

    name = meta.get("name", "(tanpa nama)")
    mime_type = meta.get("mimeType", "")

    try:
        if mime_type in _DRIVE_EXPORT_MIME:
            export_mime = _DRIVE_EXPORT_MIME[mime_type]
            raw = service.files().export(fileId=file_id, mimeType=export_mime).execute()
        elif mime_type.startswith("application/vnd.google-apps."):
            return (
                f"ERROR: Tipe Google Workspace '{mime_type}' belum didukung untuk dibaca "
                f"(cuma Google Docs/Sheets/Slides yang didukung saat ini)."
            )
        elif mime_type.startswith("text/") or mime_type in (
            "application/json", "application/xml", "application/javascript",
        ):
            raw = service.files().get_media(fileId=file_id).execute()
        else:
            return (
                f"ERROR: Tipe file '{mime_type}' bukan file teks/Google Workspace yang "
                f"didukung (kemungkinan gambar, PDF, video, atau biner lain). "
                f"Tool ini hanya bisa membaca file teks."
            )
    except Exception as e:
        return f"ERROR: gagal membaca isi file '{name}' ({e})."

    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
    else:
        text = str(raw)

    truncated = len(text) > _DRIVE_READ_MAX_CHARS
    if truncated:
        text = text[:_DRIVE_READ_MAX_CHARS]

    header = f"Isi file '{name}' (mimeType asli: {mime_type}):\n\n"
    footer = f"\n\n[...dipotong, file lebih dari {_DRIVE_READ_MAX_CHARS} karakter...]" if truncated else ""
    return header + text + footer


_PRICE_PATTERN = re.compile(r"Rp\s?[\d.,]+(?:\s?(?:rb|jt|ribu|juta))?", re.IGNORECASE)


def tool_marketplace_search(query: str, platform: str = "semua", max_results: int = 6) -> str:
    """
    Cari produk di Shopee/Tokopedia lewat web search biasa (bukan API resmi).
    Filter hasil ke domain shopee.co.id / tokopedia.com, ekstrak harga dari
    snippet kalau ada pola 'Rp...'. Tidak bisa ambil gambar produk (itu
    ditangani terpisah oleh sisi UI/image search, bukan tool ini).
    """
    max_results = max(1, min(int(max_results), 15))
    platform = (platform or "semua").lower()

    if platform == "shopee":
        site_query = f"{query} site:shopee.co.id"
        allowed_domains = ("shopee.co.id",)
    elif platform == "tokopedia":
        site_query = f"{query} site:tokopedia.com"
        allowed_domains = ("tokopedia.com",)
    else:
        site_query = f"{query} (site:shopee.co.id OR site:tokopedia.com)"
        allowed_domains = ("shopee.co.id", "tokopedia.com")

    engines = [
        ("Tavily",      _search_tavily),
        ("SearchAPI",   _search_searchapi),
        ("DuckDuckGo",  _search_duckduckgo),
        ("Brave",       _search_brave),
        ("Bing",        _search_bing),
        ("Google",      _search_google),
    ]

    last_error = ""
    raw_results = []
    for name, fn in engines:
        try:
            raw_results = fn(site_query, max_results * 2)  # ambil lebih banyak, nanti difilter
            if raw_results:
                break
        except Exception as e:
            last_error = f"{name}: {e}"
            continue

    if not raw_results:
        return (
            f"ERROR: tidak ada hasil pencarian marketplace untuk '{query}' "
            f"(semua search engine gagal/kosong). Error terakhir: {last_error}"
        )

    filtered = [
        (title, href, snippet) for (title, href, snippet) in raw_results
        if any(d in href for d in allowed_domains)
    ][:max_results]

    if not filtered:
        return (
            f"Tidak ditemukan produk '{query}' di {'Shopee/Tokopedia' if platform == 'semua' else platform.title()}.\n"
            f"Coba kata kunci lain, atau platform mungkin tidak muncul di hasil pencarian untuk query ini."
        )

    lines = [
        f"Hasil pencarian produk '{query}' di {'Shopee & Tokopedia' if platform == 'semua' else platform.title()}:\n",
        "PENTING: harga di bawah diambil dari snippet hasil pencarian web (bukan API resmi "
        "marketplace), jadi BISA SUDAH TIDAK AKURAT/UPDATE. Selalu cek harga final di link "
        "sebelum memutuskan beli.\n",
    ]
    for i, (title, href, snippet) in enumerate(filtered, 1):
        price_match = _PRICE_PATTERN.search(snippet or "")
        price_str = price_match.group(0) if price_match else "(harga tidak terbaca dari snippet, cek di link)"
        platform_label = "Shopee" if "shopee.co.id" in href else "Tokopedia" if "tokopedia.com" in href else "?"
        lines.append(
            f"{i}. {title}\n"
            f"   Platform: {platform_label}\n"
            f"   Perkiraan harga: {price_str}\n"
            f"   Link: {href}\n"
        )
    return "\n".join(lines)


_SPOTIFY_SEARCH_TYPE_PLURAL = {
    "track": "tracks",
    "artist": "artists",
    "album": "albums",
    "playlist": "playlists",
}


def tool_spotify_search(query: str, search_type: str = "track", max_results: int = 5) -> str:
    """
    Cari lagu/artist/album/playlist di Spotify lewat Client Credentials Flow
    (search publik, tidak perlu login akun user). Tidak bisa kontrol playback.
    """
    try:
        import spotify_auth
    except ImportError:
        return "ERROR: modul spotify_auth.py tidak ditemukan di folder project."

    try:
        token = spotify_auth.get_access_token()
    except spotify_auth.SpotifyNotConfigured as e:
        return f"ERROR: Spotify belum di-setup. {e}"
    except Exception as e:
        return f"ERROR: gagal mendapatkan token Spotify ({e})."

    search_type = (search_type or "track").lower()
    if search_type not in _SPOTIFY_SEARCH_TYPE_PLURAL:
        search_type = "track"
    max_results = min(max(1, int(max_results)), 20)

    try:
        resp = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "type": search_type, "limit": max_results},
            timeout=15,
        )
    except requests.RequestException as e:
        return f"ERROR: gagal menghubungi Spotify API ({e})."

    if resp.status_code == 401:
        # Token mungkin expired di tengah jalan (jarang, tapi handle saja); retry sekali.
        spotify_auth._token_cache = None
        try:
            token = spotify_auth.get_access_token()
            resp = requests.get(
                "https://api.spotify.com/v1/search",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": query, "type": search_type, "limit": max_results},
                timeout=15,
            )
        except Exception as e:
            return f"ERROR: token Spotify expired dan gagal di-refresh ({e})."

    if resp.status_code != 200:
        return f"ERROR: Spotify API mengembalikan status {resp.status_code}: {resp.text[:300]}"

    data = resp.json()
    items = data.get(_SPOTIFY_SEARCH_TYPE_PLURAL[search_type], {}).get("items", [])
    items = [item for item in items if item]  # Spotify kadang kasih null di slot kosong
    if not items:
        return f"Tidak ada hasil Spotify untuk '{query}' (tipe: {search_type})."

    lines = [f"Hasil pencarian Spotify '{query}' (tipe: {search_type}):\n"]
    for i, item in enumerate(items, 1):
        link = item.get("external_urls", {}).get("spotify", "")
        if search_type == "track":
            name = item.get("name", "?")
            artists = ", ".join(a.get("name", "?") for a in item.get("artists", []))
            album = item.get("album", {}).get("name", "?")
            lines.append(f"{i}. {name} — {artists}\n   Album: {album}\n   Link: {link}\n")
        elif search_type == "artist":
            name = item.get("name", "?")
            genres = ", ".join(item.get("genres", [])) or "(genre tidak tercantum)"
            followers = item.get("followers", {}).get("total")
            followers_str = f"{followers:,}".replace(",", ".") if followers is not None else "?"
            lines.append(f"{i}. {name}\n   Genre: {genres}\n   Followers: {followers_str}\n   Link: {link}\n")
        elif search_type == "album":
            name = item.get("name", "?")
            artists = ", ".join(a.get("name", "?") for a in item.get("artists", []))
            release_date = item.get("release_date", "?")
            lines.append(f"{i}. {name} — {artists}\n   Rilis: {release_date}\n   Link: {link}\n")
        else:  # playlist
            name = item.get("name", "?")
            owner = item.get("owner", {}).get("display_name", "?")
            track_count = item.get("tracks", {}).get("total", "?")
            lines.append(f"{i}. {name} (oleh {owner})\n   Jumlah track: {track_count}\n   Link: {link}\n")
    return "\n".join(lines)


def tool_google_search(query: str, max_results: int = 5) -> str:
    """
    Cari di Google via scraping HTML (tanpa API key).
    Bisa kena block kapan saja — fallback ke web_search (DuckDuckGo) kalau gagal.
    """
    try:
        max_results = max(1, min(int(max_results), 10))
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        }
        q = requests.utils.quote(query)
        resp = requests.get(
            f"https://www.google.com/search?q={q}&num={max_results}&hl=id",
            headers=headers, timeout=15
        )
        if resp.status_code != 200:
            return (f"ERROR: Google mengembalikan status {resp.status_code} "
                    f"(kemungkinan diblokir). Coba web_search sebagai alternatif.")

        html = resp.text

        # Ekstrak hasil organik: div dengan class "g" biasanya bungkus tiap hasil
        # Pakai regex untuk ambil title + URL + snippet
        results = []

        # Cari semua blok hasil (heuristic, bisa berubah kalau Google update HTML)
        blocks = re.findall(
            r'<div class="[^"]*?tF2Cxc[^"]*?".*?</div>\s*</div>\s*</div>',
            html, re.DOTALL
        )
        if not blocks:
            # Fallback pattern lebih lebar
            blocks = re.findall(r'<h3[^>]*>(.*?)</h3>.*?<span[^>]*>(.*?)</span>', html, re.DOTALL)
            if not blocks:
                return (f"Tidak bisa parse hasil Google untuk '{query}' "
                        f"(struktur HTML mungkin berubah atau diblokir). "
                        f"Coba web_search (DuckDuckGo) sebagai alternatif.")

        def clean_html(text):
            text = re.sub(r'<[^>]+>', '', text or '')
            return re.sub(r'\s+', ' ', text).strip()

        for block in blocks[:max_results]:
            title_m = re.search(r'<h3[^>]*>(.*?)</h3>', block, re.DOTALL)
            url_m = re.search(r'<a[^>]+href="(/url\?q=)?([^"&]+)"', block)
            snippet_m = re.search(r'<span[^>]*class="[^"]*aCOpRe[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
            if not snippet_m:
                snippet_m = re.search(r'<div[^>]*class="[^"]*VwiC3b[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)

            title = clean_html(title_m.group(1)) if title_m else "(tanpa judul)"
            raw_url = url_m.group(2) if url_m else ""
            # Decode URL Google redirect
            if raw_url.startswith("/url?q="):
                raw_url = raw_url[7:]
            href = requests.utils.unquote(raw_url.split("&")[0]) if raw_url else ""
            snippet = clean_html(snippet_m.group(1))[:300] if snippet_m else ""
            if title and href:
                results.append((title, href, snippet))

        if not results:
            return (f"Hasil ditemukan tapi gagal di-parse untuk '{query}'. "
                    f"Coba web_search (DuckDuckGo) sebagai alternatif.")

        lines = [f"Hasil pencarian Google untuk '{query}':\n"]
        for i, (title, href, snippet) in enumerate(results, 1):
            lines.append(f"{i}. {title}\n   URL: {href}\n   {snippet}\n")
        return "\n".join(lines)
    except requests.RequestException as e:
        return f"ERROR: gagal mengakses Google ({e}). Coba web_search (DuckDuckGo) sebagai alternatif."
    except Exception as e:
        return f"ERROR: {e}"


TOOL_IMPL = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
    "list_dir": tool_list_dir,
    "search_files": tool_search_files,
    "web_search": tool_web_search,
    "wikipedia_lookup": tool_wikipedia_lookup,
    "bing_search": tool_bing_search,
    "fetch_url": tool_fetch_url,
    "run_command": tool_run_command,
    "youtube_search": tool_youtube_search,
    "youtube_info": tool_youtube_info,
    "google_search": tool_google_search,
    "gmail_read": tool_gmail_read,
    "gmail_send": tool_gmail_send,
    "calendar_create_event": tool_calendar_create_event,
    "drive_list_files": tool_drive_list_files,
    "drive_read_file": tool_drive_read_file,
    "marketplace_search": tool_marketplace_search,
    "spotify_search": tool_spotify_search,
}

# Tool yang dianggap "read-only" / aman, boleh skip izin kalau auto_approve_safe=True
# PENTING: gmail_send SENGAJA TIDAK dimasukkan ke sini meskipun gmail_read masuk —
# mengirim email punya efek samping permanen ke pihak luar (penerima), jadi harus
# selalu lewat approval user, tidak peduli seberapa "dipercaya" tool lain sudah.
#
# calendar_create_event DIMASUKKAN ke SAFE_TOOLS (auto-approve) atas keputusan
# eksplisit user project ini — beda kasus dari gmail_send karena efeknya hanya
# ke kalender pribadi user sendiri, bukan mengirim apapun ke pihak luar. Event
# yang salah masih mudah dihapus/diedit manual nanti. Trade-off: kalau model
# salah menafsirkan tanggal/jam dari hasil web_search, event langsung kebuat
# tanpa user sempat cek draft dulu (tidak seperti gmail_send yang selalu preview
# dulu). Kalau mau lebih ketat, keluarkan baris "calendar_create_event" di bawah
# ini supaya kembali minta approval seperti gmail_send.
SAFE_TOOLS = {
    "read_file", "list_dir", "search_files",
    "web_search", "wikipedia_lookup", "bing_search", "fetch_url",
    "youtube_search", "youtube_info", "google_search",
    "gmail_read",
    "calendar_create_event",
    "drive_list_files", "drive_read_file",
    "marketplace_search",
    "spotify_search",
}


def describe_tool_call(fn_name: str, args: dict) -> str:
    """Bikin deskripsi singkat & manusiawi tentang apa yang akan dilakukan tool ini."""
    if fn_name == "read_file":
        return f"Membaca file: {args.get('path')}"
    if fn_name == "write_file":
        content = args.get("content", "")
        return f"Menulis file: {args.get('path')} ({len(content)} karakter)"
    if fn_name == "edit_file":
        return f"Mengedit file: {args.get('path')} (find & replace)"
    if fn_name == "list_dir":
        return f"Melihat isi direktori: {args.get('path', '.')}"
    if fn_name == "search_files":
        return f"Mencari '{args.get('pattern')}' di file-file dalam: {args.get('path', '.')}"
    if fn_name == "web_search":
        return f"Mencari di internet: \"{args.get('query')}\""
    if fn_name == "wikipedia_lookup":
        return f"Mencari ringkasan Wikipedia untuk: \"{args.get('topic')}\""
    if fn_name == "bing_search":
        return f"Mencari di Bing: \"{args.get('query')}\""
    if fn_name == "fetch_url":
        return f"Membaca isi halaman: {args.get('url')}"
    if fn_name == "run_command":
        return f"Menjalankan command shell: {args.get('command')}"
    if fn_name == "youtube_search":
        return f"Mencari video YouTube: \"{args.get('query')}\""
    if fn_name == "youtube_info":
        return f"Mengambil info video YouTube: {args.get('url')}"
    if fn_name == "google_search":
        return f"Mencari di Google: \"{args.get('query')}\""
    if fn_name == "gmail_read":
        q = args.get("query", "")
        return f"Membaca email Gmail{f' (query: {q})' if q else ' (inbox terbaru)'}"
    if fn_name == "gmail_send":
        return (
            f"Mengirim email ke: {args.get('to')}\n"
            f"Subjek: {args.get('subject')}\n"
            f"Isi:\n{args.get('body', '')[:500]}"
        )
    if fn_name == "calendar_create_event":
        loc = f" @ {args.get('location')}" if args.get("location") else ""
        return (
            f"Menambahkan ke Google Calendar: {args.get('title')}{loc}\n"
            f"Mulai: {args.get('start_time')}\n"
            f"Selesai: {args.get('end_time')}"
        )
    if fn_name == "drive_list_files":
        q = args.get("query", "")
        suffix = f" (cari: '{q}')" if q else " (terbaru)"
        return f"Mencari file di Google Drive{suffix}"
    if fn_name == "drive_read_file":
        return f"Membaca file Google Drive (file_id: {args.get('file_id')})"
    if fn_name == "marketplace_search":
        p = args.get("platform", "semua")
        return f"Mencari produk '{args.get('query')}' di marketplace ({p})"
    if fn_name == "spotify_search":
        t = args.get("search_type", "track")
        return f"Mencari di Spotify: '{args.get('query')}' (tipe: {t})"
    return f"Memanggil tool: {fn_name}"


def is_safe_command(command: str) -> bool:
    """Cek apakah command shell termasuk whitelist aman (read-only, gak ngubah apapun)."""
    cmd_lower = command.strip().lower()
    for safe in SAFE_COMMANDS:
        if cmd_lower == safe or cmd_lower.startswith(safe + " "):
            return True
    return False


def ask_permission(fn_name: str, args: dict, auto_approve_safe: bool = True) -> str:
    """
    Minta izin user sebelum eksekusi tool.
    Return: 'yes', 'no', atau 'always' (selalu izinkan tool ini sisa sesi)
    """
    if auto_approve_safe and fn_name in SAFE_TOOLS:
        return "yes"

    # Whitelist command read-only, auto-approve tanpa nanya
    if fn_name == "run_command" and is_safe_command(args.get("command", "")):
        console.print(f"[dim]✓ command aman (whitelist), auto-izinkan: {args.get('command')}[/dim]")
        return "yes"

    desc = describe_tool_call(fn_name, args)
    is_destructive = fn_name == "run_command" and any(
        kw in str(args.get("command", "")).lower()
        for kw in ["rm ", "rm -", "del ", "format", "drop table", "> /dev", "mkfs"]
    )

    style = "bold red" if is_destructive else "bold yellow"
    warn = " ⚠️  PERHATIAN: command ini berpotensi destruktif!" if is_destructive else ""

    body = f"[{style}]{desc}[/{style}]{warn}"

    # Untuk edit_file: tampilkan diff yang sebenarnya, bukan cuma deskripsi
    if fn_name == "edit_file":
        path = args.get("path", "")
        old_str = args.get("old_str", "")
        new_str = args.get("new_str", "")
        try:
            current_text = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
            preview_new = current_text.replace(old_str, new_str, 1) if old_str in current_text else current_text
            diff_text = make_diff(current_text, preview_new, path)
            if diff_text:
                body += f"\n\n[bold]Preview perubahan:[/bold]\n"
                console.print(Panel(body, title="🔐 Minta Izin", border_style="yellow"))
                console.print(Syntax(diff_text, "diff", theme="ansi_dark", background_color="default"))
                return _prompt_permission_choice()
        except Exception:
            pass  # kalau gagal bikin diff, fallback ke tampilan biasa di bawah

    # Untuk write_file ke file yang SUDAH ADA: tampilkan diff juga
    if fn_name == "write_file":
        path = args.get("path", "")
        new_content = args.get("content", "")
        p = Path(path)
        if p.exists():
            try:
                old_content = p.read_text(encoding="utf-8")
                diff_text = make_diff(old_content, new_content, path)
                if diff_text:
                    body += f"\n\n[bold]File sudah ada, ini akan MENIMPA isinya:[/bold]\n"
                    console.print(Panel(body, title="🔐 Minta Izin", border_style="yellow"))
                    console.print(Syntax(diff_text, "diff", theme="ansi_dark", background_color="default"))
                    return _prompt_permission_choice()
            except Exception:
                pass

    body += f"\n\n[dim]Detail: {json.dumps(args, ensure_ascii=False)[:400]}[/dim]"
    console.print(Panel(
        body,
        title="🔐 Minta Izin",
        border_style="red" if is_destructive else "yellow",
    ))
    return _prompt_permission_choice()


def _prompt_permission_choice() -> str:
    while True:
        ans = console.input(
            "[bold]Izinkan? [/bold] [green](y)[/green]es / [red](n)[/red]o / (a)lways untuk tool ini sesi ini: "
        ).strip().lower()
        if ans in ("y", "yes", "ya"):
            return "yes"
        if ans in ("n", "no", "tidak"):
            return "no"
        if ans in ("a", "always", "selalu"):
            return "always"
        console.print("[dim]Jawab dengan y / n / a ya.[/dim]")


# ====== KOMUNIKASI DENGAN OPENROUTER ======
def _messages_have_image(messages) -> bool:
    """Cek apakah ada content gambar (image_url) di message terakhir dari user."""
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, list):
            return any(part.get("type") == "image_url" for part in content)
        return False
    return False


def _call_model_once(messages, model: str, tools=None):
    """Panggil OpenRouter API sekali, return (status_code, json_or_text)."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages}
    if tools is not None:
        payload["tools"] = tools
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    return resp.status_code, body


def call_model(messages, model: str, allow_fallback: bool = True):
    """
    Panggil model di OpenRouter. Kalau kena rate limit (429) dan allow_fallback=True,
    otomatis coba model gratis lain di FALLBACK_FREE_MODELS sampai ada yang berhasil.
    Kalau message terakhir user ada gambar, otomatis pakai model dari
    VISION_FALLBACK_MODELS dulu (model utama biasanya text-only, gak bisa lihat gambar).
    Return tuple: (data_response, model_yang_akhirnya_berhasil_dipakai)
    """
    if not OPENROUTER_API_KEY:
        console.print("[bold red]ERROR:[/bold red] OPENROUTER_API_KEY belum di-set. Jalankan:")
        console.print('  export OPENROUTER_API_KEY="sk-or-xxxx"')
        sys.exit(1)

    has_image = _messages_have_image(messages)
    if has_image and model not in VISION_FALLBACK_MODELS:
        console.print(f"[dim]🖼  Gambar terdeteksi, pakai model vision: {VISION_FALLBACK_MODELS[0]}[/dim]")
        model = VISION_FALLBACK_MODELS[0]

    status, body = _call_model_once(messages, model, tools=TOOLS)
    if status == 200:
        return body, model

    if status != 429 or not allow_fallback:
        console.print(f"[bold red]API ERROR {status}:[/bold red] {str(body)[:500]}")
        sys.exit(1)

    # Kena rate limit -> coba model fallback lain satu-satu
    console.print(f"[yellow]⚠ Model '{model}' kena rate limit (429). Mencoba model gratis lain...[/yellow]")
    tried = {model}
    fallback_list = VISION_FALLBACK_MODELS if has_image else FALLBACK_FREE_MODELS
    for candidate in fallback_list:
        if candidate in tried:
            continue
        tried.add(candidate)
        console.print(f"[dim]  → mencoba: {candidate}[/dim]")
        status2, body2 = _call_model_once(messages, candidate, tools=TOOLS)
        if status2 == 200:
            console.print(f"[green]✓ Berhasil pakai model fallback: {candidate}[/green]")
            return body2, candidate
        if status2 != 429:
            console.print(f"[dim]  ✗ {candidate} gagal (status {status2}), coba model lain...[/dim]")
            continue
        console.print(f"[dim]  ✗ {candidate} juga kena rate limit, coba model lain...[/dim]")

    console.print("[bold red]Semua model fallback gratis kena rate limit atau gagal.[/bold red]")
    console.print("[dim]Coba lagi beberapa saat lagi, atau pakai model paid lewat /model.[/dim]")
    sys.exit(1)


def update_usage_stats(stats: dict, data: dict):
    """Tambahkan token usage dari satu response API ke akumulasi sesi."""
    usage = data.get("usage", {})
    stats["prompt_tokens"] += usage.get("prompt_tokens", 0)
    stats["completion_tokens"] += usage.get("completion_tokens", 0)
    stats["total_tokens"] += usage.get("total_tokens", 0)
    # OpenRouter kadang kasih estimasi cost langsung di field ini (USD)
    cost = data.get("usage", {}).get("cost")
    if cost:
        stats["cost_usd"] += cost
    stats["api_calls"] += 1


def run_agent_turn(messages, always_approved: set, model: str, usage_stats: dict):
    """Loop sampai model selesai memanggil tool dan kasih jawaban final teks.
    Return tuple: (messages, model_terakhir_yang_berhasil_dipakai)
    """
    active_model = model
    for _ in range(MAX_TOOL_ITERATIONS):
        data, active_model = call_model(messages, active_model)
        update_usage_stats(usage_stats, data)
        choice = data["choices"][0]
        msg = choice["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            # Jawaban final dari model
            content = msg.get("content") or "(tidak ada respons)"
            console.print(Panel(Markdown(content), title=f"Agent ({active_model})", border_style="green"))
            return messages, active_model

        # Tampilkan dulu penjelasan model (kalau ada teks sebelum tool call)
        if msg.get("content"):
            console.print(Panel(Markdown(msg["content"]), title="Agent berpikir...", border_style="blue"))

        # Model minta panggil tool(s)
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}

            # Minta izin, kecuali sudah di-"always approve" sebelumnya
            if fn_name in always_approved:
                decision = "yes"
            else:
                decision = ask_permission(fn_name, args)
                if decision == "always":
                    always_approved.add(fn_name)

            if decision == "no":
                result = "DITOLAK oleh user: izin untuk menjalankan tool ini tidak diberikan."
                console.print("[red]✗ Ditolak.[/red]")
            else:
                console.print(f"[cyan]→ menjalankan:[/cyan] {fn_name}({args})")
                impl = TOOL_IMPL.get(fn_name)
                if impl is None:
                    result = f"ERROR: tool '{fn_name}' tidak dikenal."
                else:
                    result = impl(**args)
                preview = result if len(result) < 300 else result[:300] + "...(dipotong)"
                console.print(f"[dim]  {preview}[/dim]")

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

    console.print("[yellow]⚠ Mencapai batas iterasi tool, menghentikan loop.[/yellow]")
    return messages, active_model


def summarize_turn_for_reviewer(messages: list, start_index: int) -> str:
    """
    Bikin ringkasan teks dari satu 'turn' (sejak start_index sampai akhir messages)
    untuk dikirim ke reviewer model: apa yang user minta, tool apa yang dipanggil
    worker beserta hasilnya, dan jawaban akhir worker.
    """
    turn_messages = messages[start_index:]
    parts = []
    for m in turn_messages:
        role = m.get("role")
        if role == "user":
            parts.append(f"[USER MINTA]: {m.get('content', '')}")
        elif role == "assistant":
            if m.get("content"):
                parts.append(f"[WORKER BERKATA]: {m['content']}")
            for tc in (m.get("tool_calls") or []):
                fn_name = tc["function"]["name"]
                args = tc["function"]["arguments"]
                parts.append(f"[WORKER PANGGIL TOOL]: {fn_name}({args})")
        elif role == "tool":
            content = m.get("content", "")
            preview = content if len(content) < 500 else content[:500] + "...(dipotong)"
            parts.append(f"[HASIL TOOL]: {preview}")
    return "\n".join(parts)


def call_review(messages: list, start_index: int, reviewer_model: str, usage_stats: dict) -> str:
    """Panggil reviewer model untuk mengkritik hasil kerja worker di turn ini. Reviewer tidak punya tools."""
    summary = summarize_turn_for_reviewer(messages, start_index)
    if not summary.strip():
        return "(tidak ada konten untuk direview)"

    review_messages = [
        {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Berikut log pekerjaan worker yang perlu kamu review:\n\n{summary}"},
    ]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": reviewer_model,
        "messages": review_messages,
        # sengaja TIDAK menyertakan "tools" — reviewer murni teks, tidak bisa eksekusi apapun
    }
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code != 200:
            return f"ERROR: reviewer model gagal dipanggil ({resp.status_code}): {resp.text[:300]}"
        data = resp.json()
        update_usage_stats(usage_stats, data)
        return data["choices"][0]["message"].get("content") or "(reviewer tidak memberikan komentar)"
    except Exception as e:
        return f"ERROR: gagal memanggil reviewer model ({e})"


def save_history(messages, session_file: Path):
    """Simpan riwayat percakapan ke file JSON di HISTORY_DIR."""
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        # Skip system message saat simpan, akan ditambahin lagi pas load
        to_save = [m for m in messages if m.get("role") != "system"]
        session_file.write_text(json.dumps(to_save, ensure_ascii=False, indent=2), encoding="utf-8")
        _cleanup_old_history()
    except Exception as e:
        console.print(f"[dim]⚠ Gagal menyimpan riwayat: {e}[/dim]")


def _cleanup_old_history():
    """Hapus file riwayat lama kalau lebih dari MAX_HISTORY_FILES."""
    try:
        files = sorted(HISTORY_DIR.glob("session_*.json"), key=lambda f: f.stat().st_mtime)
        while len(files) > MAX_HISTORY_FILES:
            files.pop(0).unlink()
    except Exception:
        pass


def list_recent_sessions(limit: int = 5):
    if not HISTORY_DIR.exists():
        return []
    files = sorted(HISTORY_DIR.glob("session_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:limit]


def load_history(session_file: Path):
    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        console.print(f"[red]Gagal memuat riwayat: {e}[/red]")
        return []


# File README/manifest yang dianggap penting untuk dibaca otomatis di awal sesi
KEY_FILES = [
    "README.md", "package.json", "requirements.txt", "pyproject.toml",
    "go.mod", "pom.xml", "build.gradle", "Cargo.toml", "composer.json",
]
KEY_FILE_PREVIEW_CHARS = 1000


def build_project_context(base_path: str = ".") -> str:
    """
    Baca struktur folder + isi file kunci (README, package.json, dst) di awal sesi,
    supaya agent langsung 'tau' project ini tanpa harus disuruh list_dir/read_file manual.
    """
    base = Path(base_path)
    gitignore_patterns = load_gitignore_patterns(base)

    # 1. Struktur folder (2 level, ringkas)
    tree_lines = []
    try:
        for item in sorted(base.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
            if item.name in SKIP_DIRS or item.name.startswith(".") or is_gitignored(item.name, gitignore_patterns):
                continue
            marker = "/" if item.is_dir() else ""
            tree_lines.append(f"  {item.name}{marker}")
            if item.is_dir():
                try:
                    for sub in sorted(item.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))[:10]:
                        if sub.name in SKIP_DIRS or sub.name.startswith("."):
                            continue
                        sub_marker = "/" if sub.is_dir() else ""
                        tree_lines.append(f"    {sub.name}{sub_marker}")
                except Exception:
                    pass
    except Exception:
        pass

    # 2. Isi file kunci (preview singkat)
    key_file_previews = []
    for fname in KEY_FILES:
        fpath = base / fname
        if fpath.exists() and fpath.is_file():
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                preview = content[:KEY_FILE_PREVIEW_CHARS]
                if len(content) > KEY_FILE_PREVIEW_CHARS:
                    preview += "\n...(dipotong)"
                key_file_previews.append(f"--- {fname} ---\n{preview}")
            except Exception:
                pass

    if not tree_lines and not key_file_previews:
        return ""  # folder kosong / gak ada info berguna, gak usah nambahin context

    parts = ["[Konteks proyek otomatis, dibaca saat sesi dimulai]"]
    if tree_lines:
        parts.append("Struktur folder saat ini:\n" + "\n".join(tree_lines))
    if key_file_previews:
        parts.append("Isi file kunci yang ditemukan:\n" + "\n\n".join(key_file_previews))
    return "\n\n".join(parts)


def sanitize_model_id(raw: str) -> str:
    """
    Bersihkan input model-id dari karakter yang gak mungkin valid (kurung, kutip,
    backtick, dll yang kadang nyasar masuk karena autocomplete keyboard/typo).
    Model-id OpenRouter yang valid cuma berisi huruf, angka, '/', '-', '_', '.', ':'.
    """
    cleaned = raw.strip().strip("()[]{}\"'` ")
    # Hapus juga kalau ada karakter aneh di tengah (selain yang diizinkan)
    cleaned = re.sub(r"[^a-zA-Z0-9/\-_.:]", "", cleaned)
    return cleaned


def print_help():
    console.print(Panel(
        "[bold]Perintah yang tersedia:[/bold]\n"
        "  exit / quit     — keluar dari program\n"
        "  history         — lihat & lanjutkan sesi sebelumnya\n"
        "  /clear          — reset percakapan saat ini (tanpa restart program)\n"
        "  /model          — lihat model aktif, atau ganti: /model nama/model-id\n"
        "                    (otomatis pindah ke model gratis lain kalau kena rate limit)\n"
        "  /review         — nyala/matikan mode review (model kedua mengkritik hasil kerja worker)\n"
        "  /reviewer       — lihat/ganti model reviewer: /reviewer nama/model-id\n"
        "  /cost           — lihat estimasi token & biaya yang terpakai sesi ini\n"
        "  /paste          — mode tempel multi-baris, ketik END di baris baru untuk selesai\n"
        "  /help           — tampilkan bantuan ini",
        title="Bantuan",
        border_style="cyan",
    ))


def print_cost(usage_stats: dict, model: str):
    cost_line = (
        f"~${usage_stats['cost_usd']:.4f} USD" if usage_stats["cost_usd"] > 0
        else "(estimasi biaya tidak tersedia dari API, cek harga model di openrouter.ai/models)"
    )
    console.print(Panel(
        f"[bold]Model:[/bold] {model}\n"
        f"[bold]Jumlah API call:[/bold] {usage_stats['api_calls']}\n"
        f"[bold]Prompt tokens:[/bold] {usage_stats['prompt_tokens']:,}\n"
        f"[bold]Completion tokens:[/bold] {usage_stats['completion_tokens']:,}\n"
        f"[bold]Total tokens:[/bold] {usage_stats['total_tokens']:,}\n"
        f"[bold]Estimasi biaya:[/bold] {cost_line}",
        title="📊 Usage Sesi Ini",
        border_style="magenta",
    ))


def build_system_messages() -> list:
    """System message dasar + (kalau ada) konteks proyek otomatis sebagai message terpisah."""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    context = build_project_context(".")
    if context:
        msgs.append({"role": "system", "content": context})
    return msgs


def read_multiline_input() -> str:
    """Mode /paste: terima banyak baris sampai user ketik END sendirian di baris baru."""
    console.print("[dim]Mode tempel aktif. Tempel teks/kode, lalu ketik END di baris baru untuk selesai (atau /cancel untuk batal).[/dim]")
    lines = []
    while True:
        try:
            line = console.input()
        except (EOFError, KeyboardInterrupt):
            break
        if line.strip() == "END":
            break
        if line.strip() == "/cancel":
            return ""
        lines.append(line)
    return "\n".join(lines)


def maybe_run_review(messages, start_index, review_enabled, reviewer_model, usage_stats):
    """Kalau mode review aktif, panggil reviewer model dan tampilkan hasilnya."""
    if not review_enabled:
        return
    console.print(f"[dim]🔍 Meminta review dari {reviewer_model}...[/dim]")
    review_text = call_review(messages, start_index, reviewer_model, usage_stats)
    console.print(Panel(Markdown(review_text), title=f"🧐 Review ({reviewer_model})", border_style="magenta"))


def main():
    current_model = OPENROUTER_MODEL
    reviewer_model = REVIEWER_MODEL
    review_enabled = False
    usage_stats = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0, "api_calls": 0}

    console.print(Panel(
        f"[bold]Mini Coding Agent CLI[/bold]\nModel: {current_model}\n"
        f"Setiap aksi (tulis/edit file, jalankan command) akan minta izin dulu.\n"
        f"Ketik '/help' untuk lihat semua perintah, 'exit' untuk keluar.",
        border_style="blue",
    ))

    messages = build_system_messages()
    if len(messages) > 1:
        console.print("[dim]✓ Konteks proyek (struktur folder + file kunci) otomatis dimuat.[/dim]")

    always_approved = set()
    session_file = HISTORY_DIR / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    recent = list_recent_sessions(limit=5)
    if recent:
        console.print("[dim]Sesi sebelumnya ditemukan. Ketik 'history' untuk melanjutkan salah satunya, atau langsung mulai chat baru.[/dim]")

    while True:
        try:
            user_input = console.input("\n[bold yellow]you>[/bold yellow] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\nBye!")
            break

        cmd = user_input.strip()
        cmd_lower = cmd.lower()

        if cmd_lower in {"exit", "quit"}:
            console.print("Bye!")
            break

        if cmd_lower in {"/help", "help"}:
            print_help()
            continue

        if cmd_lower == "/review":
            review_enabled = not review_enabled
            status = "AKTIF" if review_enabled else "NONAKTIF"
            console.print(f"[green]✓ Mode review sekarang {status}.[/green]")
            if review_enabled:
                console.print(f"[dim]Setiap jawaban worker ({current_model}) akan direview oleh {reviewer_model}.[/dim]")
            continue

        if cmd_lower == "/reviewer" or cmd_lower.startswith("/reviewer "):
            new_reviewer = cmd[len("/reviewer"):].strip()
            if not new_reviewer:
                console.print(f"[bold]Reviewer model aktif:[/bold] {reviewer_model}")
                console.print("[dim]Untuk ganti: /reviewer nama/model-id  (contoh: /reviewer qwen/qwen3-coder:free)[/dim]")
            else:
                reviewer_model = new_reviewer
                console.print(f"[green]✓ Reviewer model diganti ke:[/green] {reviewer_model}")
            continue

        if cmd_lower == "/paste":
            pasted = read_multiline_input()
            if not pasted.strip():
                console.print("[dim](dibatalkan, tidak ada teks dikirim)[/dim]")
                continue
            console.print(f"[dim]✓ Diterima {len(pasted.splitlines())} baris.[/dim]")
            messages.append({"role": "user", "content": pasted})
            turn_start = len(messages) - 1
            messages, used_model = run_agent_turn(messages, always_approved, current_model, usage_stats)
            if used_model != current_model:
                console.print(f"[dim]ℹ Model aktif untuk sesi ini sekarang: {used_model}[/dim]")
                current_model = used_model
            maybe_run_review(messages, turn_start, review_enabled, reviewer_model, usage_stats)
            save_history(messages, session_file)
            continue

        if cmd_lower == "/clear":
            messages = build_system_messages()
            always_approved = set()
            session_file = HISTORY_DIR / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            console.print("[green]✓ Percakapan direset. Memori sebelumnya di sesi ini dihapus.[/green]")
            continue

        if cmd_lower == "/cost":
            print_cost(usage_stats, current_model)
            continue

        if cmd_lower == "/model" or cmd_lower.startswith("/model "):
            raw_new_model = cmd[len("/model"):].strip()
            if not raw_new_model:
                console.print(f"[bold]Model aktif saat ini:[/bold] {current_model}")
                console.print("[dim]Untuk ganti: /model nama/model-id  (contoh: /model deepseek/deepseek-chat)[/dim]")
            else:
                new_model = sanitize_model_id(raw_new_model)
                if new_model != raw_new_model:
                    console.print(f"[dim]ℹ Membersihkan karakter tidak valid dari input: '{raw_new_model}' → '{new_model}'[/dim]")
                if "/" not in new_model:
                    console.print(f"[yellow]⚠ Peringatan: '{new_model}' sepertinya bukan format model-id yang benar "
                                  f"(harusnya ada '/', contoh: qwen/qwen3-coder:free). Tetap diset, tapi mungkin gagal "
                                  f"saat dipanggil.[/yellow]")
                current_model = new_model
                console.print(f"[green]✓ Model diganti ke:[/green] {current_model}")
            continue

        if cmd_lower == "history":
            recent = list_recent_sessions(limit=5)
            if not recent:
                console.print("[dim](belum ada riwayat sesi)[/dim]")
                continue
            console.print("[bold]Sesi terakhir:[/bold]")
            for i, f in enumerate(recent, start=1):
                mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                console.print(f"  {i}. {f.name}  ({mtime})")
            choice = console.input("Ketik nomor untuk lanjutkan, atau Enter untuk batal: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(recent):
                loaded = load_history(recent[int(choice) - 1])
                messages = build_system_messages()[:1] + loaded  # system prompt + history lama
                console.print(f"[green]✓ Sesi dimuat ({len(loaded)} pesan).[/green]")
            continue

        if not cmd:
            continue

        messages.append({"role": "user", "content": user_input})
        turn_start = len(messages) - 1
        messages, used_model = run_agent_turn(messages, always_approved, current_model, usage_stats)
        if used_model != current_model:
            console.print(f"[dim]ℹ Model aktif untuk sesi ini sekarang: {used_model}[/dim]")
            current_model = used_model
        maybe_run_review(messages, turn_start, review_enabled, reviewer_model, usage_stats)
        save_history(messages, session_file)


if __name__ == "__main__":
    main()
