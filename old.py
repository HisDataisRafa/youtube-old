import streamlit as st
import requests
import json
from datetime import datetime
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import time

def get_channel_id(api_key, channel_identifier):
    """
    Convierte cualquier identificador de canal (nombre de usuario, handle, o ID) 
    en el ID oficial del canal que necesita la API de YouTube.
    """
    # Si ya es un ID de canal válido, lo retornamos directamente
    if channel_identifier.startswith('UC'):
        return channel_identifier
        
    # Removemos el @ si es un handle
    if channel_identifier.startswith('@'):
        channel_identifier = channel_identifier[1:]
    
    # Buscamos el canal en YouTube
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

def get_transcript(video_id):
    """
    Obtiene la transcripción de un video con manejo extensivo de casos y errores.
    Intenta obtener la mejor transcripción disponible en el idioma preferido.
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
            
    except Exception as e:
        st.warning(f"No se pudo obtener la transcripción para el video {video_id}: {str(e)}")
    
    return None, "No disponible"

def get_channel_videos(api_key, channel_identifier, max_results=10):
    """
    Obtiene los videos más recientes de un canal junto con sus detalles y transcripciones
    """
    # Obtener el ID correcto del canal
    channel_id = get_channel_id(api_key, channel_identifier)
    if not channel_id:
        return None
        
    # Obtener los IDs de los videos más recientes
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
        
        # Obtener detalles completos de los videos
        videos_url = "https://www.googleapis.com/youtube/v3/videos"
        videos_params = {
            "key": api_key,
            "id": ",".join(video_ids),
            "part": "snippet,statistics"
        }
        
        response = requests.get(videos_url, params=videos_params)
        response.raise_for_status()
        videos_data = response.json()
        
        # Procesar cada video
        videos = []
        progress_text = st.empty()
        progress_bar = st.progress(0)
        total_videos = len(videos_data.get('items', []))
        
        for i, video in enumerate(videos_data.get('items', [])):
            progress_text.text(f"Procesando video {i+1} de {total_videos}...")
            progress_bar.progress((i + 1) / total_videos)
            
            # Obtener transcripción
            transcript_data, transcript_info = get_transcript(video['id'])
            transcript_text = ""
            if transcript_data:
                transcript_text = "\n".join([f"{item['start']:.1f}s: {item['text']}" for item in transcript_data])
            
            # Recopilar toda la información del video
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
            
            # Pequeña pausa para evitar límites de API
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
            videos = get_channel_videos(api_key, channel_identifier, max_results)
            
        if videos:
            # Mostrar los videos encontrados
            st.success(f"✅ Se encontraron {len(videos)} videos!")
            
            # Recorrer cada video
            for video in videos:
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
                json_str = json.dumps(videos, ensure_ascii=False, indent=2)
                st.download_button(
                    label="⬇️ Descargar todo (JSON)",
                    data=json_str,
                    file_name=f"youtube_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
            
            with col2:
                # Descargar solo transcripciones en formato TXT
                transcripts_text = ""
                for video in videos:
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
