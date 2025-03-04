from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, send_from_directory, flash
from werkzeug.utils import secure_filename
import os
import subprocess
from google.cloud import speech, texttospeech
import io
import wave
from google.cloud import language_v1
from datetime import datetime
from pydub import AudioSegment


app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
TTS_FOLDER='tts'
SENTIMENT_ANALYSIS_FOLDER = 'sentiment_analysis'
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

#Convert audio to LINEAR16 with 16kHz


def convert_to_16000hz(input_path, output_path):
    try:
        # Load the input audio file
        audio = AudioSegment.from_file(input_path)
        
        # Set the parameters and export to the desired output format
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)  # 2 bytes per sample = pcm_s16le
        audio.export(output_path, format="wav")  # Save the output as a WAV file

        print(f"Converted {input_path} to {output_path} with 16000 Hz sample rate")

        # Optionally, delete the original file if needed
        os.remove(input_path)
        print(f"Deleted original file: {input_path}")

        return output_path
    except Exception as e:
        print(f"Error during conversion: {e}")
        return None
#     try:
#         subprocess.run(
#             ['ffmpeg', '-i', input_path, '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', output_path],
#             check=True,
#             stdout=subprocess.PIPE,
#             stderr=subprocess.PIPE,
#             shell=True  # Add shell=True to ensure Windows compatibility
# )


# Load the input audio file


# def convert_to_16000hz(input_path, output_path):
#     try:
#         # Load the audio file
#         audio = AudioSegment.from_wav(input_path)

#         # Convert to 16kHz sample rate
#         audio = audio.set_frame_rate(16000)

#         # Export the audio to the output path
#         audio.export(output_path, format="wav")
        
   

      

# Fetch files for display
def get_files():
    # files = []

    # for filename in os.listdir(UPLOAD_FOLDER):
    #     if allowed_file(filename) or filename.endswith('.txt'):
    #         files.append(filename)
    # files.sort(reverse=True)
    # return files

    
    files = set()  # Use a set to prevent duplicates
    for filename in os.listdir(UPLOAD_FOLDER):
        if allowed_file(filename):
            files.add(filename)  # Store only unique file names
    return sorted(files, reverse=True)  # Sort for consistency

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
    
    try:
        sentiment_analysis(UPLOAD_FOLDER)
    except Exception as e:
        print(f"Error during sentiment analysis: {e}")
        return f"Error during sentiment analysis: {e}", 500
    


    return "Uploaded ,transcribed and sentiment analysis successfully (Check console for transcription result)", 200

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
    text_filename = datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.txt'
    output_path = os.path.join(tts_folder, filename)
    text_output_path = os.path.join(tts_folder, text_filename)

    with open(text_output_path, 'w') as file:
        file.write(text)
    sentiment_analysis(tts_folder)

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

@app.route('/sentiment_analysis/<filename>')
def get_sentiment_analysis(filename):
    # Construct the file path for sentiment analysis
    sentiment_file_path = os.path.join(SENTIMENT_ANALYSIS_FOLDER, filename)
    print("entered the sentiment method")
    print(filename)
    print(SENTIMENT_ANALYSIS_FOLDER)
    if os.path.exists(sentiment_file_path):
        # Send the sentiment analysis file if it exists
        return send_from_directory(SENTIMENT_ANALYSIS_FOLDER, filename)
    else:
        # Return an error if the sentiment analysis file doesn't exist
        return "Sentiment Analysis file not found.", 404



# Process the text files and perform sentiment analysis
def sentiment_analysis(folder):
    for filename in os.listdir(folder):
        if filename.endswith('.txt'):
            text_file_path = os.path.join(folder, filename)
            
            # Read the transcription text
            with open(text_file_path, 'r') as file:
                transcription_text = file.read()

            # Perform sentiment analysis
            sentiment_score, sentiment_magnitude = analyze_sentiment(transcription_text)

            # Determine sentiment label
            if sentiment_score >= 0.25:
                sentiment_label = 'Positive'
            elif sentiment_score <= -0.25:
                sentiment_label = 'Negative'
            else:
                sentiment_label = 'Neutral'

            # Create the sentiment analysis result
            sentiment_result = f"Sentiment Analysis for {filename}:\n\n"
            sentiment_result += f"Original Text:\n{transcription_text}\n\n"
            sentiment_result += f"Sentiment Score: {sentiment_score}\n"
            sentiment_result += f"Sentiment Magnitude: {sentiment_magnitude}\n\n"
            sentiment_result += f"Overall Sentiment: {sentiment_label}\n"

            # Save the sentiment result in the 'sentiment_analysis' folder
            sentiment_filename = f"sentiment_{filename}"
            sentiment_file_path = os.path.join(SENTIMENT_ANALYSIS_FOLDER, sentiment_filename)

            with open(sentiment_file_path, 'w') as sentiment_file:
                sentiment_file.write(sentiment_result)

            print(f"Sentiment result saved: {sentiment_file_path}")


# Perform sentiment analysis using Google Cloud Natural Language API
def analyze_sentiment(text):
    client = language_v1.LanguageServiceClient()

    document = language_v1.Document(content=text, type_=language_v1.Document.Type.PLAIN_TEXT)
    
    # Send the request to analyze sentiment
    sentiment = client.analyze_sentiment(request={'document': document}).document_sentiment

    # Return sentiment score and magnitude
    return sentiment.score, sentiment.magnitude


if __name__ == '__main__':
    app.run(debug=True)


    #test comment 
    #2
    #added