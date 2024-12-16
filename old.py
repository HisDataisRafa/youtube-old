import streamlit as st
import requests
import json
from datetime import datetime
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import time
import whisper
from pytube import YouTube
import os

@st.cache_resource
def load_whisper_model():
    """
    Carga el modelo de Whisper una sola vez y lo cachea
    """
    return whisper.load_model("base")

def get_audio_transcript(video_id):
    """
    Obtiene la transcripción del audio usando Whisper cuando no hay subtítulos disponibles
    """
    try:
        # Crear directorio temporal si no existe
        temp_dir = "temp_audio"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        temp_path = os.path.join(temp_dir, f"{video_id}.mp4")
        
        try:
            # Descargar audio
            st.info(f"Transcribiendo audio del video {video_id}...")
            yt = YouTube(f'https://youtube.com/watch?v={video_id}')
            audio = yt.streams.filter(only_audio=True).first()
            audio.download(output_path=temp_dir, filename=f"{video_id}.mp4")
            
            # Usar el modelo cacheado
            model = load_whisper_model()
            
            # Transcribir
            result = model.transcribe(temp_path, language='es')
            
            # Convertir al formato esperado
            transcript_data = [
                {
                    'text': segment['text'].strip(),
                    'start': round(segment['start'], 1)
                }
                for segment in result['segments']
            ]
            
            return transcript_data, "Whisper (audio)"
            
        finally:
            # Limpiar archivo temporal
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        st.warning(f"Error en la transcripción por audio: {str(e)}")
        return None, "No disponible"

def get_transcript(video_id):
    """
    Obtiene la transcripción de un video, primero intentando con la API de YouTube
    y si no está disponible, usando Whisper
    """
    try:
        # Primer intento: API de YouTube
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Lista de idiomas preferidos en orden de preferencia
        preferred_languages = ['es', 'es-ES', 'es-419', 'es-US', 'en', 'en-US', 'en-GB']
        
        transcript = None
        transcript_info = "No encontrada"
        
        # Intentar primero transcripciones manuales
        for lang in preferred_languages:
            try:
                available_manual = transcript_list.find_manually_created_transcript([lang])
                if available_manual:
                    transcript = available_manual
                    transcript_info = f"Manual ({lang})"
                    break
            except:
                continue
        
        # Si no hay manual, intentar con transcripciones automáticas
        if not transcript:
            for lang in preferred_languages:
                try:
                    available_auto = transcript_list.find_generated_transcript([lang])
                    if available_auto:
                        transcript = available_auto
                        transcript_info = f"Automática ({lang})"
                        break
                except:
                    continue
        
        # Si aún no hay transcripción, tomar cualquiera disponible
        if not transcript:
            try:
                available_transcripts = transcript_list.manual_transcripts
                if available_transcripts:
                    transcript = list(available_transcripts.values())[0]
                    lang = transcript.language_code
                    transcript_info = f"Manual ({lang})"
                else:
                    available_transcripts = transcript_list.generated_transcripts
                    if available_transcripts:
                        transcript = list(available_transcripts.values())[0]
                        lang = transcript.language_code
                        transcript_info = f"Automática ({lang})"
            except:
                pass
        
        # Si encontramos una transcripción, intentar traducirla si no está en español
        if transcript:
            try:
                if transcript.language_code not in ['es', 'es-ES', 'es-419', 'es-US']:
                    transcript = transcript.translate('es')
                    transcript_info += " (Traducida)"
            except Exception as e:
                st.warning(f"No se pudo traducir la transcripción: {str(e)}")
            
            # Obtener el texto de la transcripción
            transcript_data = transcript.fetch()
            return transcript_data, transcript_info
            
    except (TranscriptsDisabled, NoTranscriptFound):
        # Si no hay transcripción disponible, intentar con Whisper
        return get_audio_transcript(video_id)
    except Exception as e:
        st.warning(f"Error al obtener transcripción: {str(e)}")
        
    return None, "No disponible"
finally:
        # Intentar limpiar archivo temporal si existe
        if os.path.exists(temp_path):
            os.remove(temp_path)

# Modificar tu función get_transcript actual
def get_transcript(video_id):
    """
    Obtiene la transcripción de un video, primero intentando con la API de YouTube
    y si no está disponible, usando Whisper para transcribir el audio
    """
    try:
        # Primer intento: API de YouTube
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Tu código actual de obtención de transcripción...
        # [Mantén todo tu código existente aquí]
        
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        # Si no hay transcripción disponible, intentar con Whisper
        return get_audio_transcript(video_id)
    except Exception as e:
        st.warning(f"No se pudo obtener la transcripción: {str(e)}")
        return None, "No disponible"
