import streamlit as st
import requests
import json
from datetime import datetime
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import time
import whisper
from pytube import YouTube
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError

# Inicializar todas las variables de estado necesarias
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
    Obtiene la transcripción del audio usando Whisper con timeout
    """
    try:
        with ThreadPoolExecutor() as executor:
            future = executor.submit(_process_audio, video_id)
            try:
                return future.result(timeout=60)  # 60 segundos máximo
            except TimeoutError:
                st.warning(f"Timeout al procesar el video {video_id}")
                return None, "No disponible"
    except Exception as e:
        st.warning(f"Error en la transcripción por audio: {str(e)}")
        return None, "No disponible"

def _process_audio(video_id):
    """
    Función auxiliar para procesar el audio
    """
    temp_dir = "temp_audio"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        
    temp_path = os.path.join(temp_dir, f"{video_id}.mp4")
    
    try:
        st.info(f"Transcribiendo audio del video {video_id}...")
        
        # Intentar descargar con timeout interno
        try:
            yt = YouTube(
                f'https://youtube.com/watch?v={video_id}',
                use_oauth=True,
                allow_oauth_cache=True
            )
            
            # Intentar por 30 segundos máximo obtener el stream
            start_time = time.time()
            audio_stream = None
            while time.time() - start_time < 30:
                try:
                    streams = yt.streams.filter(only_audio=True)
                    if streams:
                        audio_stream = streams.first()
                        break
                except:
                    time.sleep(1)
                    continue
                    
            if not audio_stream:
                raise Exception("No se pudo obtener el audio del video")
            
            # Descargar con timeout
            audio_stream.download(output_path=temp_dir, filename=f"{video_id}.mp4")
            
            model = load_whisper_model()
            result = model.transcribe(temp_path, language='es')
            
            transcript_text = " ".join([segment['text'].strip() for segment in result['segments']])
            
            return [{'text': transcript_text}], "Whisper (audio)"
            
        except Exception as e:
            raise Exception(f"Error al descargar audio: {str(e)}")
            
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

def get_transcript(video_id):
    """
    Obtiene la transcripción de un video, primero intentando con la API de YouTube
    y si no está disponible, usando Whisper
    """
    try:
        # Obtener la lista de transcripciones disponibles
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Lista de idiomas preferidos en orden de preferencia
        preferred_languages = ['es', 'es-ES', 'es-419', 'es-US', 'en', 'en-US', 'en-GB']
        
        # Primer intento: buscar transcripción manual en idiomas preferidos
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
                # Intentar obtener cualquier transcripción manual
                available_transcripts = transcript_list.manual_transcripts
                if available_transcripts:
                    transcript = list(available_transcripts.values())[0]
                    lang = transcript.language_code
                    transcript_info = f"Manual ({lang})"
                else:
                    # Como último recurso, tomar cualquier transcripción automática
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
            
            try:
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(get_transcript, video['id'])
                    try:
                        transcript_data, transcript_info = future.result(timeout=90)  # 90 segundos máximo por video
                    except TimeoutError:
                        transcript_data, transcript_info = None, "Timeout excedido"
            except Exception:
                transcript_data, transcript_info = None, "Error al procesar"
            
            transcript_text = ""
            if transcript_data:
                transcript_text = " ".join([item['text'] for item in transcript_data])
            
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
