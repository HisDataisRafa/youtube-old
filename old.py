import streamlit as st
import requests
import json
from datetime import datetime
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import time
import whisper
from pytube import YouTube
import os

# Inicializar session_state para videos
if 'videos' not in st.session_state:
    st.session_state.videos = None

def bypass_age_gate():
    """
    Función para bypasear restricciones de YouTube
    """
    def get_ytplayer_config(html):
        return None
    YouTube.get_ytplayer_config = get_ytplayer_config

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
            # Descargar audio con manejo de errores mejorado
            st.info(f"Transcribiendo audio del video {video_id}...")
            bypass_age_gate()  # Aplicar bypass
            
            yt = YouTube(
                f'https://youtube.com/watch?v={video_id}',
                use_oauth=True,
                allow_oauth_cache=True
            )
            
            # Intentar diferentes streams si el primero falla
            audio_stream = None
            for stream in yt.streams.filter(only_audio=True):
                try:
                    audio_stream = stream
                    break
                except:
                    continue
                    
            if not audio_stream:
                raise Exception("No se pudo obtener el audio del video")
                
            audio_stream.download(output_path=temp_dir, filename=f"{video_id}.mp4")
            
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
                try:
                    os.remove(temp_path)
                except:
                    pass
                    
    except Exception as e:
        st.warning(f"Error en la transcripción por audio: {str(e)}")
        return None, "No disponible"

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
    
    # Configuración en la barra lateral
    st.sidebar.header("⚙️ Configuración")
    api_key = st.sidebar.text_input("YouTube API Key", type="password")
    channel_identifier = st.sidebar.text_input("ID/Nombre/Handle del Canal")
    max_results = st.sidebar.slider("Número de videos a obtener", 1, 50, 10)
    
    # Botón para iniciar el proceso
    if st.button("🔍 Obtener Videos y Transcripciones"):
        if not api_key or not channel_identifier:
            st.warning("⚠️ Por favor ingresa tanto la API key como el identificador del canal.")
            return
            
        with st.spinner("🔄 Obteniendo videos y transcripciones..."):
            st.session_state.videos = get_channel_videos(api_key, channel_identifier, max_results)
            
    # Mostrar videos (usando session_state)
    if st.session_state.videos:
        # Mostrar los videos encontrados
        st.success(f"✅ Se encontraron {len(st.session_state.videos)} videos!")
        
        # Recorrer cada video
        for video in st.session_state.videos:
            st.write("---")
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.image(video['thumbnail'])
            
            with col2:
                st.markdown(f"### [{video['title']}]({video['url']})")
                st.write(f"👁️ Vistas: {int(video['views']):,}  |  👍 Likes: {int(video['likes']):,}")
                
                # Usar pestañas para organizar la información
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
            # Descargar todo en formato JSON
            json_str = json.dumps(st.session_state.videos, ensure_ascii=False, indent=2)
            st.download_button(
                label="⬇️ Descargar todo (JSON)",
                data=json_str,
                file_name=f"youtube_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
        
        with col2:
            # Descargar solo transcripciones en formato TXT
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
