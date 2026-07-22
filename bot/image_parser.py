"""
Image Signal Parser (Google Gemini Vision API)
==============================================
Modul ini menerima bytes gambar (screenshot sinyal trading) dan menggunakan
Google Gemini API untuk mengekstrak informasi order secara terstruktur (JSON).
"""

import json
import logging
import os
import re

log = logging.getLogger("mt5bot.image_parser")

SYSTEM_PROMPT = """
Anda adalah AI pengenal sinyal trading forex/gold dari gambar screenshot.
Tugas Anda adalah membaca gambar sinyal trading dan mengekstrak informasi order dalam bentuk JSON murni (tanpa markdown format).

Kembalikan HANYA JSON murni dengan skema berikut:
{
  "is_valid_signal": true|false,
  "action": "BUY" | "SELL" | "BUY_LIMIT" | "SELL_LIMIT" | "BUY_STOP" | "SELL_STOP",
  "symbol": "XAUUSD" | "EURUSD" | "GBPUSD" | dll,
  "lot": 0.1,
  "entry_price": 2345.50,
  "sl": 2335.00,
  "tp": 2365.00,
  "expiration": "23 Jul 2026, 13:05 WIB" | "2026-07-23 13:05:00" | null,
  "raw_summary": "Sinyal Buy XAUUSD SL 2335 TP 2365 Expired 23 Jul 2026 13:05",
  "error_message": null
}

Catatan Aturan:
1. Jika bukan gambar sinyal trading, set "is_valid_signal": false.
2. Symbol disesuaikan (misal GOLD / XAUUSD -> "XAUUSD").
3. Action harus huruf kapital (BUY, SELL, BUY_LIMIT, SELL_LIMIT, dll).
4. Jika lot tidak tertulis di gambar, set "lot": null.
5. Jika SL atau TP tidak tertulis, set nilainya ke null atau 0.0.
6. Jika ada waktu kedaluwarsa / expired time (misal "Expired at: 23 Jul 2026, 13:05 WIB"), ekstrak ke field "expiration" sebagai string. Jika tidak ada, set "expiration": null.
7. HANYA keluarkan string JSON murni tanpa triple backticks ```json.
"""


def parse_image_with_gemini(image_bytes: bytes, api_key: str) -> dict:
    """
    Mengirimkan bytes gambar ke Gemini API dan mengembalikan dictionary terstruktur.
    """
    if not api_key or "YOUR_GEMINI_API_KEY" in api_key:
        return {
            "is_valid_signal": False,
            "error_message": "GEMINI_API_KEY belum diisi di file .env!"
        }

    # Model-model Gemini Vision yang aktif (diutamakan Gemini 3.1 Flash Lite)
    CANDIDATE_MODELS = ['gemini-3.1-flash-lite', 'gemini-flash-latest', 'gemini-2.5-flash']

    text_resp = None
    last_err = None

    # Coba import SDK google-genai terbaru (google.genai) atau google.generativeai
    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=api_key)
        for model_name in CANDIDATE_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(
                            data=image_bytes,
                            mime_type="image/jpeg",
                        ),
                        SYSTEM_PROMPT,
                    ]
                )
                text_resp = response.text
                if text_resp:
                    break
            except Exception as model_err:
                last_err = model_err
                log.warning(f"Gagal memanggil model {model_name}: {model_err}. Membuka model fallback...")

    except ImportError:
        try:
            import google.generativeai as genai
            from PIL import Image
            import io

            genai.configure(api_key=api_key)
            img = Image.open(io.BytesIO(image_bytes))

            for model_name in CANDIDATE_MODELS:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content([img, SYSTEM_PROMPT])
                    text_resp = response.text
                    if text_resp:
                        break
                except Exception as model_err:
                    last_err = model_err
                    log.warning(f"Gagal memanggil legacy model {model_name}: {model_err}...")
        except Exception as e:
            log.error(f"Gagal memanggil Gemini API: {e}")
            return {
                "is_valid_signal": False,
                "error_message": f"Gagal memanggil Gemini API: {e}"
            }
    except Exception as e:
        log.error(f"Error saat analisis gambar dengan Gemini: {e}")
        return {
            "is_valid_signal": False,
            "error_message": f"Error saat analisis gambar dengan Gemini: {e}"
        }

    if not text_resp:
        return {
            "is_valid_signal": False,
            "error_message": f"Gagal mendapatkan respon dari Gemini API: {last_err}"
        }

    # Cleaning JSON text output
    cleaned_text = text_resp.strip()
    if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text[7:]
    if cleaned_text.startswith("```"):
        cleaned_text = cleaned_text[3:]
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-3]
    cleaned_text = cleaned_text.strip()

    try:
        data = json.loads(cleaned_text)
        return data
    except Exception as parse_err:
        log.error(f"Gagal parse JSON dari Gemini response: {cleaned_text}. Error: {parse_err}")
        return {
            "is_valid_signal": False,
            "error_message": f"Hasil respon Gemini bukan JSON valid: {cleaned_text[:100]}"
        }
