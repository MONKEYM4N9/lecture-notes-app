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
import re 
import graphviz

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

# --- CUSTOM CSS DESIGN ---
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
    .stTextArea>div>div>textarea {
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
    
    /* ADVERTISEMENT STYLING */
    .ad-card {
        background-color: #1E1E1E;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #333;
        text-align: center;
        margin-bottom: 20px;
        transition: transform 0.2s;
    }
    .ad-card:hover {
        transform: scale(1.02);
        border-color: #E94057;
    }
    .ad-btn {
        margin-top: 10px;
        background-color: #4b6cb7;
        color: white;
        padding: 5px 10px;
        border-radius: 5px;
        font-size: 12px;
        font-weight: bold;
        display: inline-block;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SESSION STATE ---
if "master_notes" not in st.session_state: st.session_state["master_notes"] = ""
if "messages" not in st.session_state: st.session_state["messages"] = []
if "quiz_data" not in st.session_state: st.session_state["quiz_data"] = None
if "mindmap_code" not in st.session_state: st.session_state["mindmap_code"] = None

# --- ADVERTISEMENT ENGINE ---
def render_sidebar_ads():
    """Displays your Affiliate Links"""
    st.sidebar.caption("✨ STUDENT DEALS")
    
    # AMAZON LINK
    st.sidebar.markdown("""
    <a href="https://amzn.to/483S2zn" target="_blank" style="text-decoration: none; color: inherit;">
        <div class="ad-card">
            <div style="font-size: 30px;">🎧</div>
            <div style="font-weight: bold; margin-top: 5px; color: white;">Apple AirPods 4</div>
            <div style="font-size: 12px; color: #aaa; margin-top:5px;">Active Noise Cancellation. Perfect for lectures.</div>
            <div class="ad-btn">Check Price</div>
        </div>
    </a>
    """, unsafe_allow_html=True)

def render_footer_ad():
    """Displays a banner at the bottom"""
    st.markdown("""
    <br><br>
    <a href="https://www.coursera.org/" target="_blank" style="text-decoration: none;">
        <div style="background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%); padding: 25px; border-radius: 15px; text-align: center; color: white; margin-top: 50px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);">
            <span style="font-weight: bold; font-size: 20px;">🚀 Built with Python</span><br>
            <div style="margin-top: 8px; font-size: 14px; opacity: 0.9;">Want to build your own AI apps? Start learning today.</div>
            <button style="margin-top: 15px; background-color: white; color: #1e3c72; border: none; padding: 10px 20px; border-radius: 25px; font-weight: bold; cursor: pointer; transition: transform 0.2s;">Start Coding</button>
        </div>
    </a>
    <br><br>
    """, unsafe_allow_html=True)

# --- SIDEBAR (FIXED) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712009.png", width=50)
    
    # 1. TOP: Buy Me A Coffee
    st.markdown("""
    <a href="https://buymeacoffee.com/lecturetonotes" target="_blank">
        <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 45px !important;width: 160px !important;" >
    </a>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 2. MIDDLE: Tools
    st.write("### 🎨 Note Style")
    detail_level = st.radio("Choose Depth:", ["Summary (Concise)", "Comprehensive (Standard)", "Exhaustive (Everything)"], index=1)
    
    st.write("### 🎯 Custom Focus")
    custom_focus = st.text_area("Tell the AI what to focus on:", placeholder="e.g. 'Focus on dates', 'Explain like I'm 5'")
    
    st.markdown("---")
    
    # 3. LOWER MIDDLE: Ads
    render_sidebar_ads()
    
    st.markdown("---")
    
    # 4. BOTTOM: Admin Stuff (FIXED API VARIABLE HERE)
    st.title("Settings")
    if "GOOGLE_API_KEY" in st.secrets:
        # THIS IS THE FIX: We define api_key from the secrets file
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("✅ API Key Connected")
    else:
        api_key = st.text_input("🔑 Enter API Key", type="password")
        
    if st.button("🗑️ Clear All Data"):
        st.session_state.clear()
        st.rerun()

# --- PDF ENGINE (FAIL-SAFE HELVETICA VERSION) ---
class ModernPDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 20)
        self.set_text_color(44, 62, 80) 
        self.cell(0, 10, 'Lecture Notes', 0, 1, 'L')
        self.set_font('Helvetica', 'I', 10)
        self.set_text_color(127, 140, 141) 
        self.cell(0, 10, 'Generated by Lecture-to-Notes Pro', 0, 0, 'R')
        self.ln(12)
        self.set_draw_color(233, 64, 87) 
        self.set_line_width(1.5)
        self.line(10, 32, 200, 32)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(255, 255, 255) 
        self.set_fill_color(44, 62, 80)    
        clean_title = title.replace('#', '').strip()
        try:
            clean_title = clean_title.encode('windows-1252', 'replace').decode('windows-1252')
        except:
            pass
        self.cell(0, 10, f"  {clean_title}", 0, 1, 'L', 1)
        self.ln(5)

    def chapter_body(self, body):
        self.set_font('Helvetica', '', 11)
        self.set_text_color(20, 20, 20) 
        for line in body.split('\n'):
            line = line.strip()
            if not line:
                self.ln(2)
                continue
            safe_line = line.replace('•', chr(149)).replace('—', '-')
            if '**' in safe_line:
                parts = safe_line.split('**')
                for i, part in enumerate(parts):
                    if i % 2 == 0: self.set_font('Helvetica', '', 11)
                    else: self.set_font('Helvetica', 'B', 11)
                    try:
                        encoded_part = part.encode('windows-1252', 'replace').decode('windows-1252')
                        self.write(6, encoded_part)
                    except:
                        self.write(6, part)
                self.ln(6)
            else:
                self.set_font('Helvetica', '', 11)
                if safe_line.startswith(chr(149)) or safe_line.startswith('-') or safe_line.startswith('*'):
                    self.set_x(15)
                else:
                    self.set_x(10)
                try:
                    encoded_line = safe_line.encode('windows-1252', 'replace').decode('windows-1252')
                    self.multi_cell(0, 6, encoded_line)
                except:
                    self.multi_cell(0, 6, safe_line)
        self.ln(4)

def convert_markdown_to_pdf(markdown_text):
    pdf = ModernPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    current_body = ""
    clean_text = markdown_text.replace('📼', '').replace('📄', '').replace('?', '')
    for line in clean_text.split('\n'):
        if line.startswith('#'):
            if current_body:
                pdf.chapter_body(current_body)
                current_body = ""
            pdf.chapter_title(line)
        else:
            current_body += line + "\n"
    if current_body:
        pdf.chapter_body(current_body)
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- LOGIC FUNCTIONS ---
def get_system_prompt(detail_level, context_type, part_info="", custom_focus=""):
    base = f"You are an expert Academic Tutor. {part_info} "
    if custom_focus:
        base += f"\nIMPORTANT: The user specifically requested: '{custom_focus}'. PRIORITIZE THIS IN THE NOTES.\n"
    base += """
    STRUCTURE REQUIREMENTS:
    1. Start with a '## ⚡ TL;DR' section. Inside it, provide:
       - **Core Topic**: (1 sentence)
       - **Exam Probability**: (High/Medium/Low)
       - **Difficulty**: (1-10 scale)
    2. Then, provide the main notes below.\n
    """
    if "Summary" in detail_level: return base + f"Create a CONCISE SUMMARY of this {context_type}."
    elif "Exhaustive" in detail_level: return base + f"Create EXHAUSTIVE NOTES of this {context_type}. Include minute-by-minute details."
    else: return base + f"Create STANDARD STUDY NOTES of this {context_type}."

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
            start = text.find('['); end = text.rfind(']') + 1
            if start != -1 and end != -1: return json.loads(text[start:end])
        except Exception: time.sleep(4); continue
    st.error("Failed to generate quiz."); return None

def generate_mindmap(notes_text, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    prompt = f"""
    Create a Graphviz DOT code representation of these notes.
    CRITICAL:
    1. Start with: digraph G {{ graph [rankdir=LR, splines=ortho]; node [shape=box, style="filled", fontname="Arial"]; edge [color="#555555"];
    2. COLOR RULES: Root="#FFD700", L1="#D1C4E9", L2="#B3E5FC", L3="#C8E6C9".
    3. Max 6 words per label.
    4. OUTPUT ONLY RAW CODE inside dot tags.
    NOTES: {notes_text[:15000]}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text
        clean_dot = text.replace("```dot", "").replace("```", "").replace("graphviz", "").strip()
        return clean_dot
    except Exception as e:
        st.error(f"Mind Map Error: {e}")
        return None

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

def split_and_process_media(original_file_path, api_key, detail_level, custom_focus):
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
                
                # PASS CUSTOM FOCUS
                system_prompt = get_system_prompt(detail_level, context_type, f"Part {i+1}/{total_chunks}", custom_focus)
                
                response = model.generate_content([video_file, system_prompt])
                st.session_state["master_notes"] += f"\n\n# 📼 Part {i+1}\n{response.text}"
                status.update(label=f"✅ Part {i+1} Done!", state="complete", expanded=False)
            except Exception as e: st.error(f"Error: {e}")
            finally: 
                if os.path.exists(chunk_path): os.remove(chunk_path)
        progress_bar.progress((i + 1) / total_chunks)

def process_text_content(text_data, api_key, detail_level, source_name, custom_focus):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    with st.spinner(f'🧠 Analyzing...'):
        try:
            # PASS CUSTOM FOCUS
            system_prompt = get_system_prompt(detail_level, "transcript", "", custom_focus)
            
            response = model.generate_content([system_prompt, text_data])
            st.session_state["master_notes"] += f"\n\n# 📄 Notes from {source_name}\n{response.text}"
            st.balloons()
        except Exception as e: st.error(f"Error: {e}")

# --- MAIN UI ---
st.title("🎓 Lecture-to-Notes Pro")
st.caption("Your personal AI study companion. Upload lectures, get notes, take quizzes.")

if not st.session_state["master_notes"]:
    tab_upload, tab_youtube, tab_echo = st.tabs(["📁 Upload File", "🔗 YouTube Link", "📘 Echo360 Guide"])
    with tab_upload:
        st.write("### Upload Lecture File")
        uploaded_file = st.file_uploader("Drag and drop audio/video here", type=["mp4", "mov", "mp3", "m4a", "txt", "md"])
        if st.button("Process Uploaded File 🚀") and uploaded_file and api_key:
            file_ext = os.path.splitext(uploaded_file.name)[1].lower()
            if file_ext in ['.txt', '.md']:
                process_text_content(uploaded_file.read().decode("utf-8"), api_key, detail_level, "Text File", custom_focus); st.rerun()
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                    tmp_file.write(uploaded_file.read()); original_path = tmp_file.name
                try: split_and_process_media(original_path, api_key, detail_level, custom_focus); st.rerun()
                finally: 
                    if os.path.exists(original_path): os.unlink(original_path)
    with tab_youtube:
        st.write("### Paste YouTube URL")
        youtube_url = st.text_input("Link:", placeholder="https://youtube.com/watch?v=...")
        c1, c2, c3 = st.columns(3)
        if c1.button("⚡ Speed Run (Text)") and api_key and youtube_url:
             vid_id = get_video_id(youtube_url)
             transcript = get_transcript(vid_id)
             if transcript: process_text_content(transcript, api_key, detail_level, "Transcript", custom_focus); st.rerun()
             else: st.error("No transcript.")
        if c2.button("🎧 Audio Mode") and api_key and youtube_url:
            with st.spinner("Downloading Audio..."): path = download_audio_from_youtube(youtube_url)
            if path: 
                try: split_and_process_media(path, api_key, detail_level, custom_focus); st.rerun()
                finally: 
                    if os.path.exists(path): os.unlink(path)
        if c3.button("🧠 Video Mode") and api_key and youtube_url:
            with st.spinner("Downloading Video..."): path = download_video_from_youtube(youtube_url)
            if path:
                try: split_and_process_media(path, api_key, detail_level, custom_focus); st.rerun()
                finally:
                    if os.path.exists(path): os.unlink(path)
    with tab_echo:
        st.header("How to use Echo360 Recordings")
        st.write("Echo360 videos are private. You must download the file first.")
        st.subheader("Option 1: The Official Way")
        st.markdown("1. Go to your Echo360 Course page.\n2. Click the **Green Video Icon**.\n3. Select **Download Original**.\n4. Upload the `.mp4` file to the **📁 Upload File** tab.")
        st.subheader("Option 2: If Download is Disabled")
        st.markdown("1. Install **'Echo360 Downloader'** Chrome Extension.\n2. Go to the lecture page.\n3. Click the extension icon to save the video.\n4. Upload the file here.")

else:
    st.success("🎉 Processing Complete! Your study materials are ready.")
    t1, t2, t3, t4 = st.tabs(["📖 Notes", "💬 Chat", "📝 Quiz", "🧠 Mind Map"])
    
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
                
    with t4:
        st.write("### 🧠 Visual Concept Map")
        if st.button("Generate Mind Map ✨"):
            with st.spinner("Drawing connections..."):
                mm_code = generate_mindmap(st.session_state["master_notes"], api_key)
                if mm_code:
                    st.session_state["mindmap_code"] = mm_code
                    st.rerun()
        
        if st.session_state["mindmap_code"]:
            st.graphviz_chart(st.session_state["mindmap_code"])
    
    # RENDER FOOTER AD
    render_footer_ad()