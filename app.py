import os
import re
import uuid
import requests
from flask import Flask, request, jsonify, send_file
from urllib.parse import urlparse
import subprocess

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB
TEMP_DIR = '/tmp'
OUTPUT_DIR = '/tmp/output'

os.makedirs(OUTPUT_DIR, exist_ok=True)

def download_file(url, dest):
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(dest, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"Download error: {e}")
        return False

@app.route('/burn', methods=['POST'])
def burn_subtitles():
    data = request.json
    video_url = data.get('video_url')
    subtitles_url = data.get('subtitles_url')

    if not video_url or not subtitles_url:
        return jsonify({"error": "Missing video_url or subtitles_url"}), 400

    # Generate unique ID
    job_id = str(uuid.uuid4())[:8]
    video_path = os.path.join(TEMP_DIR, f"{job_id}.mp4")
    subtitles_path = os.path.join(TEMP_DIR, f"{job_id}.srt")
    output_path = os.path.join(OUTPUT_DIR, f"subtitled_{job_id}.mp4")

    # Download video
    if not download_file(video_url, video_path):
        return jsonify({"error": "Failed to download video"}), 500

    # Download subtitles
    if not download_file(subtitles_url, subtitles_path):
        return jsonify({"error": "Failed to download subtitles"}), 500

    # FFmpeg command to burn subtitles
    cmd = [
        'ffmpeg', '-i', video_path, '-vf',
        f"subtitles='{subtitles_path}'", '-c:a', 'copy', '-y', output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)  # 2 hours
        if result.returncode != 0:
            return jsonify({"error": "FFmpeg failed", "details": result.stderr}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Processing timed out"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Cleanup
    os.remove(video_path)
    os.remove(subtitles_path)

    # Return download URL
    download_url = request.url_root.rstrip('/') + f'/download/{job_id}'
    return jsonify({
        "message": "Subtitles burned successfully",
        "download_url": download_url
    })

@app.route('/download/<job_id>')
def download(job_id):
    sanitized = re.sub(r'[^a-zA-Z0-9]', '', job_id)
    path = os.path.join(OUTPUT_DIR, f"subtitled_{sanitized}.mp4")
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return jsonify({"error": "File not found"}), 404

@app.route('/')
def index():
    return jsonify({"status": "Subtitle burner is running. Use POST /burn"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
