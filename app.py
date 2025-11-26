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
from moviepy.editor import VideoFileClip, AudioFileClip
import imageio_ffmpeg
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs
import re 
import graphviz

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="LecturePro", 
    page_icon="🎓", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- SESSION STATE SETUP ---
if "page" not in st.session_state: st.session_state["page"] = "landing"
if "master_notes" not in st.session_state: st.session_state["master_notes"] = ""
if "messages" not in st.session_state: st.session_state["messages"] = []
if "quiz_data" not in st.session_state: st.session_state["quiz_data"] = None
if "mindmap_code" not in st.session_state: st.session_state["mindmap_code"] = None

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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #31333F; 
    }
    
    /* WIDER CONTAINER & TOP PADDING FIX */
    .block-container {
        padding-top: 6rem; /* Increased to prevent cutting off top content */
        padding-bottom: 2rem;
        max-width: 95rem;
    }
    
    /* V2 BADGE */
    .v2-badge {
        background-color: #F3E8FF;
        color: #6B21A8;
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 12px;
        display: inline-block;
        margin-bottom: 20px;
        border: 1px solid #E9D5FF;
    }

    /* HEADER STYLES */
    .main-header {
        font-size: 50px;
        font-weight: 800;
        text-align: center;
        margin-bottom: 0px;
        color: #1a1a1a;
    }
    .highlight-pink {
        background: -webkit-linear-gradient(0deg, #D946EF, #E94057);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .sub-header {
        font-size: 18px;
        color: #666;
        text-align: center;
        margin-bottom: 40px;
        max-width: 600px;
        margin-left: auto;
        margin-right: auto;
    }
    
    /* UPLOAD BOX STYLING */
    .upload-area-text {
        text-align: center;
        margin-bottom: -10px;
        font-weight: 700;
        font-size: 20px;
    }
    .upload-subtext {
        text-align: center;
        color: #888;
        font-size: 14px;
        margin-bottom: 20px;
    }
    
    /* ECHO360 BOX */
    .echo-box {
        background-color: #F0F8FF;
        border: 1px solid #cce5ff;
        border-radius: 12px;
        padding: 20px;
        margin-top: 30px;
        color: #004085;
    }
    
    /* SIDEBAR ELEMENTS */
    .sidebar-logo {
        font-size: 24px;
        font-weight: 700;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    /* --- BUTTON STYLING --- */
    
    /* Standard Buttons */
    div.stButton > button:first-child {
        border-radius: 8px;
        font-weight: 600;
        border: 1px solid #E2E8F0;
        background-color: #FFFFFF;
        color: #1E293B;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        transition: all 0.2s;
        min-height: 55px;
        height: 100%;
    }
    
    div.stButton > button:first-child:hover {
        border-color: #D946EF;
        color: #D946EF;
        background-color: #FDF4FF;
    }
    
    /* Primary Button Override (Full Video - Red) */
    button[kind="primary"] {
        background-color: #E94057 !important;
        color: white !important;
        border: none !important;
        box-shadow: 0 4px 6px -1px rgba(233, 64, 87, 0.5) !important;
    }
    
    button[kind="primary"]:hover {
        background-color: #D63349 !important;
        box-shadow: 0 10px 15px -3px rgba(233, 64, 87, 0.6) !important;
    }

    </style>
    """, unsafe_allow_html=True)

# --- LOGIC FUNCTIONS (Hidden for brevity, same as before) ---
class ModernPDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 20); self.set_text_color(44, 62, 80); self.cell(0, 10, 'Lecture Notes', 0, 1, 'L')
        self.set_font('Helvetica', 'I', 10); self.set_text_color(127, 140, 141); self.cell(0, 10, 'Generated by LecturePro', 0, 0, 'R')
        self.ln(12); self.set_draw_color(233, 64, 87); self.set_line_width(1.5); self.line(10, 32, 200, 32); self.ln(10)
    def footer(self):
        self.set_y(-15); self.set_font('Helvetica', 'I', 8); self.set_text_color(150, 150, 150); self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')
    def chapter_title(self, title):
        self.set_font('Helvetica', 'B', 14); self.set_text_color(255, 255, 255); self.set_fill_color(44, 62, 80)
        clean_title = title.replace('#', '').strip().encode('windows-1252', 'replace').decode('windows-1252')
        self.cell(0, 10, f"  {clean_title}", 0, 1, 'L', 1); self.ln(5)
    def chapter_body(self, body):
        self.set_font('Helvetica', '', 11); self.set_text_color(20, 20, 20)
        for line in body.split('\n'):
            line = line.strip()
            if not line: self.ln(2); continue
            safe_line = line.replace('•', chr(149)).replace('—', '-')
            if '**' in safe_line:
                parts = safe_line.split('**')
                for i, part in enumerate(parts):
                    if i % 2 == 0: self.set_font('Helvetica', '', 11)
                    else: self.set_font('Helvetica', 'B', 11)
                    self.write(6, part.encode('windows-1252', 'replace').decode('windows-1252'))
                self.ln(6)
            else:
                self.set_font('Helvetica', '', 11)
                if safe_line.startswith(chr(149)) or safe_line.startswith('-'): self.set_x(15)
                else: self.set_x(10)
                self.multi_cell(0, 6, safe_line.encode('windows-1252', 'replace').decode('windows-1252'))
        self.ln(4)

def convert_markdown_to_pdf(markdown_text):
    pdf = ModernPDF(); pdf.add_page(); pdf.set_auto_page_break(auto=True, margin=15)
    current_body = ""; clean_text = markdown_text.replace('📼', '').replace('📄', '').replace('?', '')
    for line in clean_text.split('\n'):
        if line.startswith('#'):
            if current_body: pdf.chapter_body(current_body); current_body = ""
            pdf.chapter_title(line)
        else: current_body += line + "\n"
    if current_body: pdf.chapter_body(current_body)
    return pdf.output(dest='S').encode('latin-1', 'replace')

def get_system_prompt(detail_level, context_type, part_info="", custom_focus=""):
    base = f"You are an expert Academic Tutor. {part_info} "
    if custom_focus: base += f"\nIMPORTANT: User requested: '{custom_focus}'. PRIORITIZE THIS.\n"
    base += """
    STRUCTURE REQUIREMENTS:
    1. Start with a '## ⚡ TL;DR' section (Core Topic, Difficulty /10, Exam Probability).
    2. Then, provide main notes.
    """
    if "Summary" in detail_level: return base + f"Create a CONCISE SUMMARY of this {context_type}."
    elif "Exhaustive" in detail_level: return base + f"Create EXHAUSTIVE NOTES of this {context_type}."
    else: return base + f"Create STANDARD STUDY NOTES of this {context_type}."

def generate_quiz(notes_text, api_key):
    genai.configure(api_key=api_key); model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    prompt = f"Create 5 multiple choice questions. OUTPUT ONLY RAW JSON. Structure: [ {{\"question\": \"?\", \"options\": [\"A) x\", \"B) y\"], \"answer\": \"B) y\"}} ]. NOTES: {notes_text[:15000]}"
    for attempt in range(3):
        try:
            response = model.generate_content(prompt); text = response.text
            start = text.find('['); end = text.rfind(']') + 1
            if start != -1 and end != -1: return json.loads(text[start:end])
        except Exception: time.sleep(4); continue
    st.error("Quiz failed."); return None

def generate_mindmap(notes_text, api_key):
    genai.configure(api_key=api_key); model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    prompt = f"""
    Create Graphviz DOT code.
    CRITICAL:
    1. Start: digraph G {{ graph [rankdir=LR, splines=ortho]; node [shape=box, style="filled", fontname="Arial"]; edge [color="#555555"];
    2. COLORS: Root="#FFD700", L1="#D1C4E9", L2="#B3E5FC", L3="#C8E6C9".
    3. Max 6 words/label.
    4. OUTPUT ONLY RAW CODE inside dot tags.
    NOTES: {notes_text[:15000]}
    """
    try:
        response = model.generate_content(prompt); text = response.text
        return text.replace("```dot", "").replace("```", "").replace("graphviz", "").strip()
    except Exception as e: st.error(f"Mind Map Error: {e}"); return None

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

def run_master_editor(all_chunk_notes, api_key, detail_level, custom_focus):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-pro") 
    combined_raw_text = "\n\n".join(all_chunk_notes)
    system_prompt = f"""
    You are the "Master Editor". MERGE these notes into one cohesive document.
    Detail: {detail_level}. Focus: {custom_focus}.
    RAW NOTES: {combined_raw_text}
    """
    try:
        response = model.generate_content(system_prompt)
        return response.text
    except Exception as e: return f"Error: {e}"

def split_and_process_media(original_file_path, api_key, detail_level, custom_focus):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-pro") 
    duration_sec = get_media_duration(original_file_path)
    if duration_sec == 0: return
    chunk_size_sec = 2400 
    total_chunks = math.ceil(duration_sec / chunk_size_sec)
    
    st.info(f"Processing {total_chunks} segments...")
    progress_bar = st.progress(0)
    raw_notes_accumulator = [] 

    for i in range(total_chunks):
        start_time = i * chunk_size_sec
        end_time = min((i + 1) * chunk_size_sec, duration_sec)
        with st.status(f"Processing Part {i+1}...", expanded=True) as status:
            ext = os.path.splitext(original_file_path)[1]
            chunk_path = f"temp_chunk_{i}{ext}"
            cut_media_fast(original_file_path, chunk_path, start_time, end_time)
            try:
                video_file = genai.upload_file(path=chunk_path)
                while video_file.state.name == "PROCESSING": time.sleep(2); video_file = genai.get_file(video_file.name)
                is_audio = ext.lower() in ['.mp3', '.wav', '.m4a']
                sys_prompt = get_system_prompt("Exhaustive", "audio" if is_audio else "video", f"Part {i+1}", custom_focus)
                response = model.generate_content([video_file, sys_prompt])
                raw_notes_accumulator.append(response.text)
                status.update(label="Done", state="complete")
            except Exception as e: st.error(str(e))
            finally: 
                if os.path.exists(chunk_path): os.remove(chunk_path)
        progress_bar.progress((i + 1) / total_chunks)

    final_polished_notes = run_master_editor(raw_notes_accumulator, api_key, detail_level, custom_focus)
    st.session_state["master_notes"] = final_polished_notes
    st.balloons()
    st.rerun()

def process_text_content(text_data, api_key, detail_level, source_name, custom_focus):
    genai.configure(api_key=api_key); model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    with st.spinner(f'Analyzing...'):
        try:
            system_prompt = get_system_prompt(detail_level, "transcript", "", custom_focus)
            response = model.generate_content([system_prompt, text_data])
            st.session_state["master_notes"] += f"\n\n# 📄 Notes from {source_name}\n{response.text}"
            st.rerun()
        except Exception as e: st.error(f"Error: {e}")

# --- MAIN RENDER ---
def render_app():
    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown('<div class="sidebar-logo">🎓 LecturePro</div>', unsafe_allow_html=True)
        # Full width Buy Me A Coffee
        st.markdown("""
        <a href="https://buymeacoffee.com/lecturetonotes" target="_blank" style="display: block; width: 100%;">
            <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="width: 100%; height: auto; border-radius: 8px; margin-bottom: 20px;">
        </a>
        """, unsafe_allow_html=True)
        
        st.caption("NOTE STYLE")
        detail_level = st.radio("Style", ["Summary (Concise)", "Comprehensive", "Exhaustive"], index=1, label_visibility="collapsed")
        
        st.caption("CUSTOM FOCUS")
        custom_focus = st.text_area("Focus", placeholder="e.g. 'Focus on dates and names' or 'Explain like I'm 5'", label_visibility="collapsed")
        
        st.markdown("---")
        
        # Student Deal Card (Apple AirPods 4)
        st.markdown("""
        <div style="background-color: #0F172A; padding: 15px; border-radius: 10px; color: white; text-align: center; margin-bottom: 20px;">
            <div style="font-size: 24px; margin-bottom: 5px;">🎧</div>
            <div style="font-weight: bold; font-size: 14px;">Apple AirPods 4</div>
            <div style="font-size: 11px; color: #94A3B8; margin: 5px 0 10px 0;">Active Noise Cancellation. Perfect for lectures.</div>
            <a href="https://amzn.to/483S2zn" target="_blank" style="background-color: white; color: black; padding: 5px 15px; border-radius: 4px; text-decoration: none; font-weight: bold; font-size: 12px; display: inline-block;">Check Price</a>
        </div>
        """, unsafe_allow_html=True)
        
        st.caption("API CONFIGURATION")
        if "GOOGLE_API_KEY" in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
            st.success("✅ API Key Connected")
        else:
            api_key = st.text_input("API Key", type="password", placeholder="Enter Gemini API Key", label_visibility="collapsed")
            
        if st.button("Reset App"): st.session_state.clear(); st.rerun()

    # --- MAIN CONTENT OR RESULT ---
    if st.session_state["master_notes"]:
        # RESULT VIEW
        st.success("🎉 Notes Generated!")
        t1, t2, t3, t4 = st.tabs(["📖 Notes", "💬 Chat", "📝 Quiz", "🧠 Mind Map"])
        
        with t1:
            st.markdown(st.session_state["master_notes"])
            pdf = convert_markdown_to_pdf(st.session_state["master_notes"])
            st.download_button("Download PDF", pdf, "notes.pdf", "application/pdf")
            if st.button("Start Over"): st.session_state.clear(); st.rerun()
            
        with t2:
            for m in st.session_state["messages"]: st.chat_message(m["role"]).markdown(m["content"])
            if p := st.chat_input("Ask about your lecture..."):
                st.session_state["messages"].append({"role":"user","content":p}); st.chat_message("user").markdown(p)
                genai.configure(api_key=api_key); model = genai.GenerativeModel("gemini-2.5-flash")
                res = model.generate_content(f"Context: {st.session_state['master_notes']}\nUser: {p}")
                st.chat_message("assistant").markdown(res.text); st.session_state["messages"].append({"role":"assistant","content":res.text})
                
        with t3:
            if st.button("Generate Quiz"): 
                q = generate_quiz(st.session_state["master_notes"], api_key)
                if q: st.session_state["quiz_data"] = q; st.rerun()
            if st.session_state["quiz_data"]:
                for i, q in enumerate(st.session_state["quiz_data"]):
                    st.markdown(f"**{i+1}. {q['question']}**")
                    cols = st.columns(2)
                    for idx, opt in enumerate(q['options']):
                        if cols[idx%2].button(opt, key=f"q{i}{idx}"):
                             if opt == q['answer']: st.success("Correct!")
                             else: st.error(f"Wrong. Answer: {q['answer']}")
                             
        with t4:
            if st.button("Generate Map"):
                c = generate_mindmap(st.session_state["master_notes"], api_key)
                if c: st.session_state["mindmap_code"] = c; st.rerun()
            if st.session_state["mindmap_code"]: st.graphviz_chart(st.session_state["mindmap_code"])

    else:
        # LANDING PAGE VIEW
        col1, col2, col3 = st.columns([1, 6, 1])
        with col2:
            st.markdown('<div style="text-align: center;"><span class="v2-badge">🚀 V2.0: AUTO-SPLICING ENGINE ACTIVE</span></div>', unsafe_allow_html=True)
            st.markdown('<div class="main-header">Turn Lectures into <span class="highlight-pink">Super Notes</span></div>', unsafe_allow_html=True)
            st.markdown('<div class="sub-header">Upload any video, audio, or YouTube link. Our AI breaks it down, analyzes every second, and creates the ultimate study guide.</div>', unsafe_allow_html=True)
            
            # 1. FILE UPLOAD BOX
            with st.container():
                # Added margin-top to separate slightly from header
                st.markdown("""
                <div style="border: 2px dashed #E0E7FF; border-radius: 15px; padding: 30px; text-align: center; background-color: white; margin-bottom: 20px; margin-top: 20px;">
                    <div style="font-size: 40px; margin-bottom: 10px; background-color: #EEF2FF; width: 80px; height: 80px; line-height: 80px; border-radius: 50%; margin-left: auto; margin-right: auto; color: #4F46E5;">📤</div>
                    <div style="font-weight: 700; font-size: 18px; color: #1e293b;">Drop your lecture file</div>
                    <div style="color: #64748b; font-size: 14px; margin-bottom: 15px;">MP4, MP3, MOV, M4A (Max 2GB - Auto-Spliced)</div>
                </div>
                """, unsafe_allow_html=True)
                uploaded_file = st.file_uploader("Upload", type=["mp4", "mov", "mp3", "m4a", "txt", "md"], label_visibility="collapsed")
                
                if uploaded_file and api_key:
                    if st.button("Process Uploaded File 🚀", use_container_width=True):
                        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
                        if file_ext in ['.txt', '.md']: process_text_content(uploaded_file.read().decode("utf-8"), api_key, detail_level, "Text", custom_focus)
                        else:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp: tmp.write(uploaded_file.read()); path = tmp.name
                            try: split_and_process_media(path, api_key, detail_level, custom_focus)
                            finally: os.unlink(path)

            # 2. YOUTUBE SECTION
            st.markdown("---")
            c_input, c_btn1, c_btn2, c_btn3 = st.columns([3, 1, 1, 1])
            with c_input:
                yt_url = st.text_input("YouTube URL", placeholder="Paste YouTube URL here...", label_visibility="collapsed")
            
            # Action Buttons
            if c_btn1.button("⚡ Speed Run"):
                if api_key and yt_url:
                    vid_id = get_video_id(yt_url); trans = get_transcript(vid_id)
                    if trans: process_text_content(trans, api_key, detail_level, "YouTube", custom_focus)
                    else: st.error("No transcript found.")
            
            if c_btn2.button("🎧 Audio"):
                if api_key and yt_url:
                    path = download_audio_from_youtube(yt_url)
                    if path: split_and_process_media(path, api_key, detail_level, custom_focus)
            
            if c_btn3.button("📹 Full Video", type="primary"):
                 if api_key and yt_url:
                    path = download_video_from_youtube(yt_url)
                    if path: split_and_process_media(path, api_key, detail_level, custom_focus)

            # 3. ECHO360 GUIDE
            st.markdown("""
            <div class="echo-box">
                <div style="font-weight: bold; margin-bottom: 10px;">ℹ️ How to use Echo360 Recordings</div>
                <div style="display: flex; gap: 20px;">
                    <div style="flex: 1;">
                        <b>Option 1: Official Download</b><br>
                        1. Go to your Echo360 Course page.<br>
                        2. Click the green video icon.<br>
                        3. Select "Download Original".
                    </div>
                    <div style="flex: 1;">
                        <b>Option 2: Extension</b><br>
                        1. Install "Echo360 Downloader".<br>
                        2. Go to the lecture page.<br>
                        3. Click extension icon to save.
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

render_app()