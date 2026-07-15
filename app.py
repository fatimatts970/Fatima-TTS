from flask import Flask, request, jsonify, send_from_directory
import os
import asyncio
import edge_tts
import random

app = Flask(__name__)
PORT = int(os.environ.get("PORT", 10000))
BASE_DIR = "/tmp" 
HTML_DIR = os.getcwd()

async def generate_voice_async(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

@app.route('/')
def index():
    return send_from_directory(HTML_DIR, 'index.html')

@app.route('/preview', methods=['POST'])
def preview():
    data = request.json
    voice = data.get('voice', 'ur-PK-UzmaNeural')

    if voice.startswith("ur-PK") or voice.startswith("ur-IN"):
        preview_text = "فاطمہ ٹی ٹی ایس اسٹوڈیو میں آپ کا خوش آمدید ہے۔"
    elif voice.startswith("hi-IN"):
        preview_text = "फ़ातिमा टीटीएस स्टूडियो में आपका स्वागत है।"
    elif voice.startswith("en-"):
        preview_text = "Welcome to the Fatima T.T.S. Studio."
    elif voice.startswith("es-"):
        preview_text = "Bienvenido a Fatima T.T.S. Studio."
    elif voice.startswith("ar-"):
        preview_text = "مرحباً بكم في استوديو فاطمة للأصوات."
    elif voice.startswith("af-"):
        preview_text = "Welkom by Fatima T.T.S. Studio."
    elif voice.startswith("he-"):
        preview_text = "ברוכים הבאים לסטודיו פאטימה."
    else:
        preview_text = "Welcome to Fatima TTS Studio."

    output_file = f"preview-{voice}.mp3"
    output_path = os.path.join(BASE_DIR, output_file)

    if os.path.exists(output_path):
        try: os.remove(output_path)
        except: pass

    try:
        asyncio.run(generate_voice_async(preview_text, voice, output_path))
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return jsonify({"success": True, "audio_url": f"/download/{output_file}?v={os.urandom(4).hex()}"})
        else:
            return jsonify({"success": False, "error": "Zero-byte file generated."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    text = data.get('text', '')
    voice = data.get('voice', 'ur-PK-UzmaNeural')

    if not text.strip():
        return jsonify({"success": False, "error": "Script is empty!"})

    # Lakhon carororen mein se random number generate karne ke liye range barha di hai
    random_num = random.randint(100000000000000000, 999999999999999999)
    output_file = f"FatimaTTS-{random_num}.mp3"
    output_path = os.path.join(BASE_DIR, output_file)

    try:
        asyncio.run(generate_voice_async(text, voice, output_path))
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return jsonify({
                "success": True, 
                "audio_url": f"/download/{output_file}?v={os.urandom(4).hex()}",
                "filename": output_file
            })
        else:
            return jsonify({"success": False, "error": "Server failed to process TTS."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/stop', methods=['POST'])
def stop():
    return jsonify({"success": True})

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(BASE_DIR, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
