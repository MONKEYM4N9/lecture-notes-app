import streamlit as st
import google.generativeai as genai
import tempfile
import os
import time
import math
import shutil
import subprocess
import yt_dlp
import markdown
import json
from fpdf import FPDF
from io import BytesIO
from moviepy import VideoFileClip, AudioFileClip
import imageio_ffmpeg
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Lecture-to-Notes Pro", 
    page_icon="🎓", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- AUTO-SETUP FFmpeg ---
def ensure_ffmpeg_exists():
    current_folder = os.getcwd()
    ffmpeg_local = os.path.join(current_folder, "ffmpeg.exe")
    if not os.path.exists(ffmpeg_local):
        try:
            ffmpeg_src = imageio_ffmpeg.get_ffmpeg_exe()
            shutil.copy(ffmpeg_src, ffmpeg_local)
        except Exception as e:
            print(f"FFmpeg setup warning: {e}")
    return ffmpeg_local

FFMPEG_PATH = ensure_ffmpeg_exists()

# --- CUSTOM CSS DESIGN (DARK MODE) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #E0E0E0;
    }
    .stApp {
        background-color: #0E1117;
    }
    section[data-testid="stSidebar"] {
        background-color: #262730;
        border-right: 1px solid #333333;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #FFFFFF !important;
    }
    .stButton>button {
        background: linear-gradient(90deg, #8A2387 0%, #E94057 100%);
        color: white;
        border: none;
        border-radius: 12px;
        height: 3.5em;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(233, 64, 87, 0.3);
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(233, 64, 87, 0.5);
    }
    .stTextInput>div>div>input {
        background-color: #1E1E1E;
        color: white;
        border: 1px solid #444;
    }
    .correct-ans {
        background-color: #064e3b;
        padding: 15px;
        border-radius: 10px;
        color: #a7f3d0;
        border: 1px solid #059669;
        margin-bottom: 10px;
    }
    .wrong-ans {
        background-color: #7f1d1d;
        padding: 15px;
        border-radius: 10px;
        color: #fecaca;
        border: 1px solid #dc2626;
        margin-bottom: 10px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #262730;
        color: #ffffff;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.5);
        padding: 0 20px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #E94057;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SESSION STATE ---
if "master_notes" not in st.session_state: st.session_state["master_notes"] = ""
if "messages" not in st.session_state: st.session_state["messages"] = []
if "quiz_data" not in st.session_state: st.session_state["quiz_data"] = None

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712009.png", width=50)
    st.title("Settings")
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("✅ API Key Connected")
    else:
        api_key = st.text_input("🔑 Enter API Key", type="password")
        
    st.markdown("---")
    st.write("### 🎨 Note Style")
    detail_level = st.radio("Choose Depth:", ["Summary (Concise)", "Comprehensive (Standard)", "Exhaustive (Everything)"], index=1)
    
    st.markdown("---")
    if st.button("🗑️ Clear All Data"):
        st.session_state.clear()
        st.rerun()

# --- HELPER FUNCTIONS ---
def convert_markdown_to_pdf(markdown_text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)
    clean_text = markdown_text.replace("# ", "").replace("## ", "").replace("**", "")
    for line in clean_text.split('\n'):
        safe_line = line.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 10, safe_line)
    return pdf.output(dest='S').encode('latin-1')

def get_system_prompt(detail_level, context_type, part_info=""):
    if "Summary" in detail_level: return f"You are an expert Summarizer. {part_info} Create a CONCISE SUMMARY of this {context_type}."
    elif "Exhaustive" in detail_level: return f"You are a dedicated Scribe. {part_info} Create EXHAUSTIVE NOTES of this {context_type}."
    else: return f"You are an expert Tutor. {part_info} Create STANDARD STUDY NOTES of this {context_type}."

def generate_quiz(notes_text, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    prompt = f"""
    Create 5 multiple choice questions based on these notes.
    OUTPUT ONLY RAW JSON. NO MARKDOWN.
    Structure: [ {{"question": "?", "options": ["A) x", "B) y"], "answer": "B) y"}} ]
    NOTES: {notes_text[:15000]}
    """
    for attempt in range(3):
        try:
            response = model.generate_content(prompt)
            text = response.text
            start = text.find('[')
            end = text.rfind(']') + 1
            if start != -1 and end != -1: return json.loads(text[start:end])
        except Exception: time.sleep(4); continue
    st.error("Failed to generate quiz. Please wait 1 minute and try again."); return None

# --- MEDIA LOGIC ---
def get_video_id(url):
    try:
        query = urlparse(url)
        if query.hostname == 'youtu.be': return query.path[1:]
        if query.hostname in ('www.youtube.com', 'youtube.com'):
            if query.path == '/watch': return parse_qs(query.query)['v'][0]
    except: return None

def get_transcript(video_id):
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([line['text'] for line in transcript_list])
    except: return None

# --- DOWNLOADERS ---
def download_audio_from_youtube(url):
    try:
        ffmpeg_loc = "ffmpeg" if shutil.which("ffmpeg") else os.path.abspath("ffmpeg.exe")
        ydl_opts = {'format': 'bestaudio[ext=m4a]/bestaudio', 'outtmpl': 'temp_yt_audio.%(ext)s', 'ffmpeg_location': ffmpeg_loc, 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        return "temp_yt_audio.m4a"
    except Exception as e: st.error(f"Audio DL Error: {e}"); return None

def download_video_from_youtube(url):
    try:
        ffmpeg_loc = "ffmpeg" if shutil.which("ffmpeg") else os.path.abspath("ffmpeg.exe")
        ydl_opts = {'format': 'best[ext=mp4][height<=720]', 'outtmpl': 'temp_yt_vid.%(ext)s', 'ffmpeg_location': ffmpeg_loc, 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        return "temp_yt_vid.mp4"
    except Exception as e: st.error(f"Video DL Error: {e}"); return None

def get_media_duration(file_path):
    try:
        if file_path.endswith('.m4a') or file_path.endswith('.mp3'): clip = AudioFileClip(file_path)
        else: clip = VideoFileClip(file_path)
        duration = clip.duration; clip.close(); return duration
    except: return 0

def cut_media_fast(input_path, output_path, start_time, end_time):
    ffmpeg_exe = "ffmpeg" if shutil.which("ffmpeg") else os.path.abspath("ffmpeg.exe")
    cmd = [ffmpeg_exe, "-y", "-i", input_path, "-ss", str(start_time), "-to", str(end_time), "-c", "copy", output_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def split_and_process_media(original_file_path, api_key, detail_level):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-pro")
    duration_sec = get_media_duration(original_file_path)
    if duration_sec == 0: return
    
    chunk_size_sec = 2400; total_chunks = math.ceil(duration_sec / chunk_size_sec)
    st.info(f"🍿 Media is {duration_sec/60:.0f} mins long. Style: {detail_level}. Time for a Reels break! 📱")
    progress_bar = st.progress(0)
    
    for i in range(total_chunks):
        start_time = i * chunk_size_sec; end_time = min((i + 1) * chunk_size_sec, duration_sec)
        with st.status(f"Processing Part {i+1}/{total_chunks}...", expanded=True) as status:
            ext = os.path.splitext(original_file_path)[1]
            chunk_path = f"temp_chunk_{i}{ext}"
            cut_media_fast(original_file_path, chunk_path, start_time, end_time)
            try:
                video_file = genai.upload_file(path=chunk_path)
                while video_file.state.name == "PROCESSING": time.sleep(2); video_file = genai.get_file(video_file.name)
                status.write(f"🧠 Analyzing ({detail_level})...")
                is_audio = ext.lower() in ['.mp3', '.wav', '.m4a']
                context_type = "audio" if is_audio else "video"
                system_prompt = get_system_prompt(detail_level, context_type, f"Part {i+1}/{total_chunks}")
                response = model.generate_content([video_file, system_prompt])
                st.session_state["master_notes"] += f"\n\n# 📼 Part {i+1}\n{response.text}"
                status.update(label=f"✅ Part {i+1} Done!", state="complete", expanded=False)
            except Exception as e: st.error(f"Error: {e}")
            finally: 
                if os.path.exists(chunk_path): os.remove(chunk_path)
        progress_bar.progress((i + 1) / total_chunks)

def process_text_content(text_data, api_key, detail_level, source_name):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    with st.spinner(f'🧠 Analyzing...'):
        try:
            system_prompt = get_system_prompt(detail_level, "transcript", "")
            response = model.generate_content([system_prompt, text_data])
            st.session_state["master_notes"] += f"\n\n# 📄 Notes from {source_name}\n{response.text}"
            st.balloons()
        except Exception as e: st.error(f"Error: {e}")

# --- MAIN UI ---
st.title("🎓 Lecture-to-Notes Pro")
st.caption("Your personal AI study companion. Upload lectures, get notes, take quizzes.")

if not st.session_state["master_notes"]:
    st.info("👈 Start by entering your API Key in the sidebar.")
    
    tab_upload, tab_youtube, tab_echo = st.tabs(["📁 Upload File", "🔗 YouTube Link", "📘 Echo360 Guide"])

    with tab_upload:
        st.write("### Upload Lecture File")
        uploaded_file = st.file_uploader("Drag and drop audio/video here", type=["mp4", "mov", "mp3", "m4a", "txt", "md"])
        if st.button("Process Uploaded File 🚀") and uploaded_file and api_key:
            file_ext = os.path.splitext(uploaded_file.name)[1].lower()
            if file_ext in ['.txt', '.md']:
                process_text_content(uploaded_file.read().decode("utf-8"), api_key, detail_level, "Text File"); st.rerun()
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                    tmp_file.write(uploaded_file.read()); original_path = tmp_file.name
                try: split_and_process_media(original_path, api_key, detail_level); st.rerun()
                finally: 
                    if os.path.exists(original_path): os.unlink(original_path)

    with tab_youtube:
        st.write("### Paste YouTube URL")
        youtube_url = st.text_input("Link:", placeholder="https://youtube.com/watch?v=...")
        c1, c2, c3 = st.columns(3)
        if c1.button("⚡ Speed Run (Text)") and api_key and youtube_url:
             vid_id = get_video_id(youtube_url)
             transcript = get_transcript(vid_id)
             if transcript: process_text_content(transcript, api_key, detail_level, "Transcript"); st.rerun()
             else: st.error("No transcript.")
        if c2.button("🎧 Audio Mode") and api_key and youtube_url:
            with st.spinner("Downloading Audio..."): path = download_audio_from_youtube(youtube_url)
            if path: 
                try: split_and_process_media(path, api_key, detail_level); st.rerun()
                finally: 
                    if os.path.exists(path): os.unlink(path)
        if c3.button("🧠 Video Mode") and api_key and youtube_url:
            with st.spinner("Downloading Video..."): path = download_video_from_youtube(youtube_url)
            if path:
                try: split_and_process_media(path, api_key, detail_level); st.rerun()
                finally:
                    if os.path.exists(path): os.unlink(path)
                    
    # RESTORED: Detailed Echo360 Guide
    with tab_echo:
        st.header("How to use Echo360 Recordings")
        st.write("Echo360 videos are private. You must download the file first.")
        
        st.subheader("Option 1: The Official Way")
        st.markdown("""
        1. Go to your Echo360 Course page.
        2. Click the **Green Video Icon** (or the three dots).
        3. Select **Download Original**.
        4. Upload the `.mp4` file to the **📁 Upload File** tab.
        """)
        
        st.subheader("Option 2: If Download is Disabled")
        st.markdown("""
        1. Install the **'Echo360 Downloader'** Chrome Extension.
        2. Go to the lecture page.
        3. Click the extension icon to save the video.
        4. Upload the file here.
        """)

else:
    st.success("🎉 Processing Complete! Your study materials are ready.")
    t1, t2, t3 = st.tabs(["📖 Notes", "💬 Chat", "📝 Quiz"])
    with t1:
        st.markdown(st.session_state["master_notes"])
        if st.button("📄 Generate PDF"):
            pdf = convert_markdown_to_pdf(st.session_state["master_notes"])
            st.download_button("Download PDF", pdf, "notes.pdf", "application/pdf")
    with t2:
        for m in st.session_state["messages"]: st.chat_message(m["role"]).markdown(m["content"])
        if p := st.chat_input("Ask questions about your lecture..."):
            st.session_state["messages"].append({"role":"user","content":p}); st.chat_message("user").markdown(p)
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            res = model.generate_content(f"Context:\n{st.session_state['master_notes']}\nUser: {p}")
            st.chat_message("assistant").markdown(res.text)
            st.session_state["messages"].append({"role":"assistant","content":res.text})
    with t3:
        if st.button("Generate New Quiz 🎲"):
            with st.spinner("Creating Questions..."):
                q = generate_quiz(st.session_state["master_notes"], api_key)
                if q: st.session_state["quiz_data"] = q; st.rerun()
        if st.session_state["quiz_data"]:
            for i, q in enumerate(st.session_state["quiz_data"]):
                st.markdown(f"**{i+1}. {q['question']}**")
                k = f"q_{i}"
                if k not in st.session_state:
                    cols = st.columns(2)
                    for idx, opt in enumerate(q['options']):
                        if cols[idx%2].button(opt, key=f"btn_{i}_{idx}"):
                            st.session_state[k] = True; st.session_state[f"user_{i}"] = opt; st.rerun()
                else:
                    u = st.session_state[f"user_{i}"]; c = q['answer']
                    if u==c: st.markdown(f"<div class='correct-ans'>✅ Correct! ({u})</div>", unsafe_allow_html=True)
                    else: st.markdown(f"<div class='wrong-ans'>❌ Wrong. You picked {u}.<br>✅ Answer: {c}</div>", unsafe_allow_html=True)
                st.markdown("---")