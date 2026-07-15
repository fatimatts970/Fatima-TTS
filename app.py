from flask import Flask, request, jsonify, send_from_directory
import os
import asyncio
import edge_tts

app = Flask(__name__)
# Render automatically port provide karta hai, agar na ho to 10000 par chalega
PORT = int(os.environ.get("PORT", 10000))
BASE_DIR = os.getcwd()

async def generate_voice_async(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/preview', methods=['POST'])
def preview():
    data = request.json
    voice = data.get('voice', 'ur-PK-UzmaNeural')

    preview_text = "Welcome to Fatima TTS Studio. Testing this voice now."
    if voice.startswith("ur-PK") or voice.startswith("ur-IN"):
        preview_text = "ویڈیو بنانے کے لیے یہ آواز بالکل ٹھیک رہے گی۔"
    elif voice.startswith("hi-IN"):
        preview_text = "फ़ातिما टीटीएस स्टूडियो में आपका स्वागत है।"
    elif voice.startswith("ar-"):
        preview_text = "مرحباً بكم في استوديو فاطمة للأصوات."

    output_file = f"preview-{voice}.mp3"
    output_path = os.path.join(BASE_DIR, output_file)

    if os.path.exists(output_path):
        try: os.remove(output_path)
        except: pass

    try:
        asyncio.run(generate_voice_async(preview_text, voice, output_path))
        return jsonify({"success": True, "audio_url": f"/download/{output_file}?v={os.urandom(4).hex()}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    text = data.get('text', '')
    voice = data.get('voice', 'ur-PK-UzmaNeural')

    if not text.strip():
        return jsonify({"success": False, "error": "Script is empty!"})

    output_file = "output.mp3"
    output_path = os.path.join(BASE_DIR, output_file)

    if os.path.exists(output_path):
        try: os.remove(output_path)
        except: pass

    try:
        asyncio.run(generate_voice_async(text, voice, output_path))
        return jsonify({"success": True, "audio_url": f"/download/{output_file}?v={os.urandom(4).hex()}"})
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
