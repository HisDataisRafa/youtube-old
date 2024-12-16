import streamlit as st
import requests
import json
from datetime import datetime
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import time
import whisper
from pytube import YouTube
import os
import pytube.request
import pytube.cipher

# Configurar pytube
pytube.request.default_range_size = 1048576  # 1MB en bytes

def patch_pytube():
    """
    Parcha pytube para evitar errores de conexión
    """
    pytube.request.default_range_size = 1048576
    
    def get_throttling_function_name(js):
        return "xxx"
        
    pytube.cipher.get_throttling_function_name = get_throttling_function_name

# Aplicar el patch al inicio
patch_pytube()

# Inicializar variables de estado
if 'videos' not in st.session_state:
    st.session_state.videos = None
if 'api_key' not in st.session_state:
    st.session_state.api_key = ''
if 'channel_identifier' not in st.session_state:
    st.session_state.channel_identifier = ''
if 'max_results' not in st.session_state:
    st.session_state.max_results = 10

@st.cache_resource
def load_whisper_model():
    """
    Carga el modelo de Whisper una sola vez y lo cachea
    """
    return whisper.load_model("base")

def get_channel_id(api_key, channel_identifier):
    """
    Convierte cualquier identificador de canal en el ID oficial del canal
    """
    if channel_identifier.startswith('UC'):
        return channel_identifier
        
    if channel_identifier.startswith('@'):
        channel_identifier = channel_identifier[1:]
    
    search_url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": api_key,
        "q": channel_identifier,
        "type": "channel",
        "part": "id",
        "maxResults": 1
    }
    
    try:
        response = requests.get(search_url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if 'items' in data and data['items']:
            return data['items'][0]['id']['channelId']
        else:
            st.error(f"No se encontró el canal: {channel_identifier}")
            return None
            
    except requests.exceptions.RequestException as e:
        st.error(f"Error al buscar el canal: {str(e)}")
        return None

def get_audio_transcript(video_id):
    """
    Obtiene la transcripción del audio usando Whisper
    """
    try:
        temp_dir = "temp_audio"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        temp_path = os.path.join(temp_dir, f"{video_id}.mp4")
        
        try:
            st.info(f"Transcribiendo audio del video {video_id}...")
            
            # Configurar headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
            }
            
            yt = YouTube(
                url=f'https://youtube.com/watch?v={video_id}'
            )
            
            # Aplicar headers
            yt.stream_monostate.headers = headers
            
            # Intentar diferentes streams
            streams = yt.streams.filter(only_audio=True).order_by('abr').desc()
            audio_stream = None
            
            for stream in streams:
                try:
                    audio_stream = stream
                    break
                except:
                    continue
                    
            if not audio_stream:
                raise Exception("No se pudo obtener el audio del video")
                
            # Descargar con retry
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    audio_stream.download(output_path=temp_dir, filename=f"{video_id}.mp4")
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    time.sleep(1)
            
            # Transcribir con Whisper
            model = load_whisper_model()
            result = model.transcribe(temp_path, language='es')
            
            # Solo guardar el texto sin timestamps
            transcript_text = " ".join([segment['text'].strip() for segment in result['segments']])
            
            return [{'text': transcript_text, 'start': 0}], "Whisper (audio)"
            
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
                    
    except Exception as e:
        st.warning(f"Error en la transcripción por audio: {str(e)}")
        return None, "No disponible"

def get_transcript(video_id):
    """
    Obtiene la transcripción de un video, priorizando transcripciones de YouTube
    """
    transcript_data = None
    transcript_info = "No disponible"
    
    # Primer intento: Transcripciones de YouTube
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        preferred_languages = ['es', 'es-ES', 'es-419', 'es-US', 'en', 'en-US', 'en-GB']
        
        # Intentar transcripciones manuales
        for lang in preferred_languages:
            try:
                transcript = transcript_list.find_manually_created_transcript([lang])
                if transcript:
                    transcript_info = f"Manual ({lang})"
                    # Traducir si no está en español
                    if lang.startswith('en'):
                        transcript = transcript.translate('es')
                        transcript_info += " (Traducida)"
                    transcript_data = transcript.fetch()
                    break
            except:
                continue
                
        # Si no hay manual, intentar automáticas
        if not transcript_data:
            for lang in preferred_languages:
                try:
                    transcript = transcript_list.find_generated_transcript([lang])
                    if transcript:
                        transcript_info = f"Automática ({lang})"
                        if lang.startswith('en'):
                            transcript = transcript.translate('es')
                            transcript_info += " (Traducida)"
                        transcript_data = transcript.fetch()
                        break
                except:
                    continue
    
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        # Solo si no hay transcripciones disponibles, intentar Whisper
        st.info("No se encontraron transcripciones. Intentando con audio...")
        transcript_data, transcript_info = get_audio_transcript(video_id)
    
    except Exception as e:
        st.warning(f"Error al obtener transcripción: {str(e)}")
    
    return transcript_data, transcript_info

def get_channel_videos(api_key, channel_identifier, max_results=10):
    """
    Obtiene los videos más recientes de un canal
    """
    channel_id = get_channel_id(api_key, channel_identifier)
    if not channel_id:
        return None
        
    search_url = "https://www.googleapis.com/youtube/v3/search"
    search_params = {
        "key": api_key,
        "channelId": channel_id,
        "part": "id",
        "order": "date",
        "maxResults": max_results,
        "type": "video"
    }
    
    try:
        response = requests.get(search_url, params=search_params)
        response.raise_for_status()
        search_data = response.json()
        
        video_ids = [item['id']['videoId'] for item in search_data.get('items', [])]
        
        if not video_ids:
            st.warning("No se encontraron videos en este canal.")
            return None
        
        videos_url = "https://www.googleapis.com/youtube/v3/videos"
        videos_params = {
            "key": api_key,
            "id": ",".join(video_ids),
            "part": "snippet,statistics"
        }
        
        response = requests.get(videos_url, params=videos_params)
        response.raise_for_status()
        videos_data = response.json()
        
        videos = []
        progress_text = st.empty()
        progress_bar = st.progress(0)
        total_videos = len(videos_data.get('items', []))
        
        for i, video in enumerate(videos_data.get('items', [])):
            progress_text.text(f"Procesando video {i+1} de {total_videos}...")
            progress_bar.progress((i + 1) / total_videos)
            
            # Obtener y procesar transcripción
            transcript_data, transcript_info = get_transcript(video['id'])
            transcript_text = ""
            if transcript_data:
                # Para transcripciones normales de YouTube, eliminar timestamps
                if transcript_info != "Whisper (audio)":
                    transcript_text = " ".join([item['text'] for item in transcript_data])
                else:
                    # Para transcripciones de Whisper, ya vienen sin timestamps
                    transcript_text = transcript_data[0]['text']
            
            videos.append({
                'title': video['snippet']['title'],
                'description': video['snippet']['description'],
                'thumbnail': video['snippet']['thumbnails']['high']['url'],
                'views': video['statistics'].get('viewCount', '0'),
                'likes': video['statistics'].get('likeCount', '0'),
                'url': f"https://youtube.com/watch?v={video['id']}",
                'transcript': transcript_text,
                'transcript_info': transcript_info,
                'video_id': video['id']
            })
            
            time.sleep(0.5)
        
        progress_text.empty()
        progress_bar.empty()
        return videos
        
    except requests.exceptions.RequestException as e:
        st.error(f"Error al obtener videos: {str(e)}")
        return None

def main():
    st.set_page_config(page_title="YouTube Content Explorer", layout="wide")
    
    st.title("📺 YouTube Content Explorer")
    st.write("""
    Esta herramienta te permite explorar los videos más recientes de un canal de YouTube 
    y obtener sus transcripciones. Puedes usar cualquiera de estos identificadores:
    - ID del canal (comienza con UC...)
    - Nombre de usuario del canal
    - Handle del canal (comienza con @)
    """)
    
    # Configuración en la barra lateral usando session_state
    st.sidebar.header("⚙️ Configuración")
    
    st.session_state.api_key = st.sidebar.text_input(
        "YouTube API Key",
        value=st.session_state.api_key,
        type="password"
    )
    
    st.session_state.channel_identifier = st.sidebar.text_input(
        "ID/Nombre/Handle del Canal",
        value=st.session_state.channel_identifier
    )
    
    st.session_state.max_results = st.sidebar.slider(
        "Número de videos a obtener",
        1, 50, st.session_state.max_results
    )
    
    # Botón para iniciar el proceso
    if st.button("🔍 Obtener Videos y Transcripciones"):
        if not st.session_state.api_key or not st.session_state.channel_identifier:
            st.warning("⚠️ Por favor ingresa tanto la API key como el identificador del canal.")
            return
            
        with st.spinner("🔄 Obteniendo videos y transcripciones..."):
            st.session_state.videos = get_channel_videos(
                st.session_state.api_key,
                st.session_state.channel_identifier,
                st.session_state.max_results
            )
            
    # Mostrar videos si existen en session_state
    if st.session_state.videos:
        st.success(f"✅ Se encontraron {len(st.session_state.videos)} videos!")
        
        for video in st.session_state.videos:
            st.write("---")
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.image(video['thumbnail'])
            
            with col2:
                st.markdown(f"### [{video['title']}]({video['url']})")
                st.write(f"👁️ Vistas: {int(video['views']):,}  |  👍 Likes: {int(video['likes']):,}")
                
                tab1, tab2 = st.tabs(["📝 Descripción", "🎯 Transcripción"])
                with tab1:
                    st.write(video['description'])
                with tab2:
                    col1, col2 = st.columns([3,1])
                    with col1:
                        if video['transcript']:
                            st.text_area("", value=video['transcript'], height=200)
                        else:
                            st.info("No hay transcripción disponible para este video")
                    with col2:
                        st.info(f"Tipo: {video['transcript_info']}")
        
        # Botones de descarga
        st.write("---")
        st.subheader("📥 Descargar Datos")
        col1, col2 = st.columns(2)
        
        with col1:
            json_str = json.dumps(st.session_state.videos, ensure_ascii=False, indent=2)
            st.download_button(
                label="⬇️ Descargar todo (JSON)",
                data=json_str,
                file_name=f"youtube_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
        
        with col2:
            transcripts_text = ""
            for video in st.session_state.videos:
                if video['transcript']:
                    transcripts_text += f"\n\n=== {video['title']} ===\n"
                    transcripts_text += f"URL: {video['url']}\n"
                    transcripts_text += f"Tipo: {video['transcript_info']}\n\n"
                    transcripts_text += video['transcript']
                    transcripts_text += "\n\n" + "="*50 + "\n"
            
            st.download_button(
                label="⬇️ Descargar transcripciones (TXT)",
                data=transcripts_text,
                file_name=f"transcripts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain"
            )

if __name__ == "__main__":
    main()
