import streamlit as st
import google.generativeai as genai
import tempfile
import os
import time
import math
import subprocess
import yt_dlp
from moviepy import VideoFileClip, AudioFileClip
from imageio_ffmpeg import get_ffmpeg_exe
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Lecture-to-Notes Pro", page_icon="🎓", layout="centered")

# --- CSS ---
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        background-color: #FF4B4B;
        color: white;
        font-size: 20px;
        padding: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

if "master_notes" not in st.session_state:
    st.session_state["master_notes"] = ""

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # Check secrets
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("✅ API Key Loaded")
    else:
        api_key = st.text_input("Enter API Key", type="password")
        
    st.markdown("---")
    st.header("📝 Note Style")
    detail_level = st.radio(
        "Choose Depth:",
        ["Summary (Concise)", "Comprehensive (Standard)", "Exhaustive (Everything)"],
        index=1
    )
    
    if st.button("Clear All Notes"):
        st.session_state["master_notes"] = ""
        st.rerun()

# --- PROMPT GENERATOR ---
def get_system_prompt(detail_level, context_type, part_info=""):
    if "Summary" in detail_level:
        return f"""
        You are an expert Summarizer. {part_info}
        The student wants a **CONCISE SUMMARY** of this {context_type}.
        Output Structure:
        1. **The Main Idea:** One paragraph explaining the core thesis.
        2. **Top 3 Takeaways:** The most important points only.
        3. **Key Terms:** A quick list of defined terms.
        """
    elif "Exhaustive" in detail_level:
        return f"""
        You are a dedicated Scribe. {part_info}
        The student wants **EXHAUSTIVE, DEEP NOTES** of this {context_type}.
        Output Structure:
        1. **Minute-by-Minute Walkthrough:** Detailed chronological notes.
        2. **All Arguments:** Explain the logic behind every point.
        3. **All Examples:** Write down every example given.
        4. **Visuals:** Describe every single graph, chart, or slide shown in the video.
        """
    else: 
        return f"""
        You are an expert Academic Tutor. {part_info}
        The student wants **STANDARD STUDY NOTES** of this {context_type}.
        Output Structure:
        1. **Key Concepts:** Definitions and Explanations.
        2. **Main Arguments:** The core logic.
        3. **Visuals:** Describe important charts/diagrams shown on screen.
        4. **Exam Predictions:** What is likely to be tested?
        """

# --- HELPER FUNCTIONS ---
def get_video_id(url):
    """Extracts video ID from YouTube URL"""
    query = urlparse(url)
    if query.hostname == 'youtu.be':
        return query.path[1:]
    if query.hostname in ('www.youtube.com', 'youtube.com'):
        if query.path == '/watch':
            p = parse_qs(query.query)
            return p['v'][0]
    return None

def get_transcript(video_id):
    """Fetches text transcript instantly"""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        full_text = ""
        for line in transcript_list:
            full_text += f"{line['text']} "
        return full_text
    except Exception as e:
        return None

def download_video_from_youtube(url):
    """Downloads VIDEO (MP4) from YouTube to a temp file"""
    try:
        # UPDATED: We now download 'best' video but limit height to 720p
        # This ensures we get Visuals but file size doesn't explode.
        ydl_opts = {
            'format': 'best[ext=mp4][height<=720]/best[ext=mp4]',
            'outtmpl': 'temp_yt_download.%(ext)s',
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        return "temp_yt_download.mp4"
    except Exception as e:
        st.error(f"YouTube Download Error: {e}")
        return None

def get_media_duration(file_path):
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.mp3', '.wav', '.m4a']:
            clip = AudioFileClip(file_path)
        else:
            clip = VideoFileClip(file_path)
        duration = clip.duration
        clip.close()
        return duration
    except:
        return 0

def cut_media_fast(input_path, output_path, start_time, end_time):
    ffmpeg_exe = get_ffmpeg_exe()
    cmd = [ffmpeg_exe, "-y", "-i", input_path, "-ss", str(start_time), "-to", str(end_time), "-c", "copy", output_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# --- CORE PROCESSORS ---
def process_text_content(text_data, api_key, detail_level, source_name):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-pro")
    
    with st.spinner(f'🧠 Analyzing {source_name} ({detail_level})...'):
        try:
            system_prompt = get_system_prompt(detail_level, "transcript text", "")
            response = model.generate_content([system_prompt, text_data])
            st.session_state["master_notes"] += f"\n\n# 📄 Notes from {source_name}\n"
            st.session_state["master_notes"] += response.text
            st.balloons()
        except Exception as e:
            st.error(f"Error: {e}")

def split_and_process_media(original_file_path, api_key, detail_level):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-pro")
    duration_sec = get_media_duration(original_file_path)
    if duration_sec == 0: return
    
    chunk_size_sec = 2400 
    total_chunks = math.ceil(duration_sec / chunk_size_sec)
    
    st.warning(f"🍿 Media is {duration_sec/60:.0f} mins long. Processing style: {detail_level}.\n\nThis will take a few minutes... Time for a Reels break! 📱")
    progress_bar = st.progress(0)
    
    for i in range(total_chunks):
        start_time = i * chunk_size_sec
        end_time = min((i + 1) * chunk_size_sec, duration_sec)
        
        with st.status(f"Processing Part {i+1} of {total_chunks}...", expanded=True) as status:
            ext = os.path.splitext(original_file_path)[1]
            chunk_path = f"temp_chunk_{i}{ext}"
            
            status.write("✂️ Cutting segment...")
            cut_media_fast(original_file_path, chunk_path, start_time, end_time)
            
            status.write("📤 Uploading to AI...")
            try:
                video_file = genai.upload_file(path=chunk_path)
                while video_file.state.name == "PROCESSING":
                    time.sleep(2)
                    video_file = genai.get_file(video_file.name)
                
                if video_file.state.name == "FAILED":
                    st.error(f"Part {i+1} failed.")
                    continue

                status.write(f"🧠 Analyzing ({detail_level})...")
                ext_check = os.path.splitext(original_file_path)[1].lower()
                context_type = "audio recording" if ext_check in ['.mp3', '.wav', '.m4a'] else "video lecture"
                part_info = f"You are analyzing Part {i+1} of a {total_chunks}-part lecture."
                system_prompt = get_system_prompt(detail_level, context_type, part_info)
                
                response = model.generate_content([video_file, system_prompt])
                st.session_state["master_notes"] += f"\n\n# 📼 Part {i+1} ({start_time//60}m - {end_time//60}m)\n"
                st.session_state["master_notes"] += response.text
                status.update(label=f"✅ Part {i+1} Done!", state="complete", expanded=False)
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                if os.path.exists(chunk_path): os.remove(chunk_path)
        progress_bar.progress((i + 1) / total_chunks)

# --- MAIN UI ---
st.title("🎓 Lecture-to-Notes Pro")
st.write("Upload a file OR paste a YouTube link.")

tab_upload, tab_youtube = st.tabs(["📁 Upload File", "🔗 YouTube Link"])

with tab_upload:
    uploaded_file = st.file_uploader("Upload File", type=["mp4", "mov", "avi", "mkv", "mp3", "wav", "m4a", "txt", "md", "srt", "vtt"])
    if st.button("Process Uploaded File 🚀"):
        if not api_key: st.error("⚠️ Please enter API Key in sidebar.")
        elif uploaded_file:
            file_ext = os.path.splitext(uploaded_file.name)[1].lower()
            if file_ext in ['.txt', '.md', '.srt', '.vtt']:
                string_data = uploaded_file.read().decode("utf-8")
                process_text_content(string_data, api_key, detail_level, "Uploaded Text")
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    original_path = tmp_file.name
                try:
                    split_and_process_media(original_path, api_key, detail_level)
                    st.balloons()
                finally:
                    if os.path.exists(original_path): os.unlink(original_path)

with tab_youtube:
    youtube_url = st.text_input("Paste YouTube URL here")
    
    col1, col2 = st.columns(2)
    
    # BUTTON 1: SPEED RUN (TRANSCRIPT / AUDIO CONTENT)
    with col1:
        if st.button("⚡ Speed Run (Audio Content)"):
            if not api_key: st.error("⚠️ Please enter API Key.")
            elif youtube_url:
                video_id = get_video_id(youtube_url)
                if not video_id:
                    st.error("Invalid YouTube URL.")
                else:
                    transcript_text = get_transcript(video_id)
                    if transcript_text:
                        process_text_content(transcript_text, api_key, detail_level, "YouTube Transcript")
                    else:
                        st.error("No transcript available. Try Deep Analysis.")

    # BUTTON 2: DEEP ANALYSIS (VIDEO / VISUALS)
    with col2:
        if st.button("🧠 Deep Analysis (Video & Visuals)"):
            if not api_key: st.error("⚠️ Please enter API Key.")
            elif youtube_url:
                with st.spinner("Downloading Video... (This takes time for visuals!)"):
                    # UPDATED: Now calls the video downloader, not audio
                    downloaded_path = download_video_from_youtube(youtube_url)
                
                if downloaded_path:
                    try:
                        split_and_process_media(downloaded_path, api_key, detail_level)
                        st.balloons()
                    finally:
                        if os.path.exists(downloaded_path): os.unlink(downloaded_path)

# --- RESULTS ---
if st.session_state["master_notes"]:
    st.markdown("---")
    st.success("🎉 Processing Complete!")
    tab1, tab2 = st.tabs(["📖 Read Notes", "📋 Copy Raw Text"])
    with tab1: st.markdown(st.session_state["master_notes"])
    with tab2: st.text_area("Copy Code", value=st.session_state["master_notes"], height=400)
    st.download_button("📥 Download Notes", st.session_state["master_notes"], "Notes.md")