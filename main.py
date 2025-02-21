from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, send_from_directory, flash
from werkzeug.utils import secure_filename
import os
import subprocess
from google.cloud import speech, texttospeech
import io
import wave

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'wav'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the uploads and TTS folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('tts', exist_ok=True)

@app.route('/tts/<filename>')
def serve_tts_file(filename):
    return send_from_directory('tts', filename)

# Check if the file is allowed
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Convert audio to LINEAR16 with 16kHz
def convert_to_16000hz(input_path, output_path):
    try:
        subprocess.run(
            ['ffmpeg', '-i', input_path, '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', output_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True  # Add shell=True to ensure Windows compatibility
)

        print(f"Converted {input_path} to {output_path} with 16000 Hz sample rate")
        return output_path
    except Exception as e:
        print(f"Error during conversion: {e}")
        return None

# Fetch files for display
def get_files():
    files = []
    for filename in os.listdir(UPLOAD_FOLDER):
        if allowed_file(filename) or filename.endswith('.txt'):
            files.append(filename)
    files.sort(reverse=True)
    return files

@app.route('/')
def index():
    files = get_files()  # List of uploaded audio files (from uploads folder)
    tts_folder = 'tts'
    tts_files = [f for f in os.listdir(tts_folder) if f.endswith('.mp3')]  # Fetch TTS files
    return render_template('index.html', files=files, tts_files=tts_files)



@app.route('/upload', methods=['POST'])
def upload_audio():
    if 'audio_data' not in request.files:
        print("No audio data in request")
        return "No audio data in request", 400

    file = request.files['audio_data']
    if file.filename == '':
        print("No file selected")
        return "No file selected", 400

    # Save the uploaded audio file
    filename = datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.wav'
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)
    print(f"Saved file: {file_path}")

    # Convert and transcribe the audio
    converted_file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"converted_{filename}")
    convert_to_16000hz(file_path, converted_file_path)

    try:
        transcript = transcribe_audio(converted_file_path)
        if transcript:
            print(f"Transcription result: {transcript}")
        else:
            print("No transcription results")
    except Exception as e:
        print(f"Error during transcription: {e}")
        return f"Error during transcription: {e}", 500

    return "Uploaded and transcribed successfully (Check console for transcription result)", 200

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Get the sample rate of an audio file
def get_sample_rate(file_path):
    with wave.open(file_path, 'rb') as audio:
        return audio.getframerate()

# Transcribe audio using Google Cloud Speech-to-Text
def transcribe_audio(file_path):
    try:
        client = speech.SpeechClient()

        # Read the audio file
        with io.open(file_path, 'rb') as audio_file:
            content = audio_file.read()

        # Configure the request
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code='en-US',  # Set the language for transcription
        )

        # Perform transcription
        response = client.recognize(config=config, audio=audio)

        if response.results:
            # Combine all transcriptions into a single text
            transcript = "\n".join(result.alternatives[0].transcript for result in response.results)
            print(f"Transcription successful: {transcript}")

            # Save the transcription to a text file
            text_file_path = os.path.splitext(file_path)[0] + ".txt"
            with open(text_file_path, 'w') as text_file:
                text_file.write(transcript)

            print(f"Transcription saved to: {text_file_path}")
            return text_file_path  # Return the path to the text file for displaying later

        else:
            print("No transcription results")
            return None

    except Exception as e:
        print(f"Error in transcription: {e}")
        return None

@app.route('/upload_text', methods=['POST'])
def upload_text():
    text = request.form['text']
    if not text.strip():
        print("No text provided")
        return redirect('/')

    # Save the generated audio to the 'tts' directory
    tts_folder = 'tts'
    os.makedirs(tts_folder, exist_ok=True)
    filename = datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.mp3'
    output_path = os.path.join(tts_folder, filename)

    try:
        synthesize_text(text, output_path)
    except Exception as e:
        print(f"Error generating audio: {e}")
        return f"Error generating audio: {e}", 500

    print(f"Generated audio saved as {filename}")
    return redirect('/')

# Synthesize text to speech using Google Cloud Text-to-Speech
def synthesize_text(text, output_path):
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
    )
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

    response = client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )

    with open(output_path, "wb") as out:
        out.write(response.audio_content)

@app.route('/script.js', methods=['GET'])
def scripts_js():
    return send_file('./script.js')

@app.route('/ping', methods=['GET'])
def ping():
    return "Server is running", 200

@app.route('/info', methods=['GET'])
def info():
    return {"status": "active", "version": "1.0.1", "description": "Audio and TTS processing app"}

if __name__ == '__main__':
    app.run(debug=True)


    #test comment 
    #added