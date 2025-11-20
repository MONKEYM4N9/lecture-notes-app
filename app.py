import streamlit as st
import google.generativeai as genai
import tempfile
import os
import time
import math
import subprocess
from moviepy import VideoFileClip, AudioFileClip
from imageio_ffmpeg import get_ffmpeg_exe

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Lecture to Notes AI | Free Student Study Tool", # <--- KEYWORDS HERE
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://twitter.com/yourhandle',
        'Report a bug': "https://github.com/yourrepo/issues",
        'About': "Turn video lectures into exam-ready notes using AI. Upload MP4, MP3, or PDF."
    }
)

# --- CSS FOR PRETTY UI ---
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

# Initialize Session State
if "master_notes" not in st.session_state:
    st.session_state["master_notes"] = ""

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # 1. AUTOMATIC: Check if the key is in secrets.toml
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("✅ API Key Loaded from Secrets")
    
    # 2. MANUAL: Fallback if the file is missing (e.g., for your customers)
    else:
        api_key = st.text_input("Enter Google Gemini API Key", type="password")
        if not api_key:
            st.warning("⚠️ Add a secrets.toml file to skip this step!")
            
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
        Keep it short and high-level.
        """
    elif "Exhaustive" in detail_level:
        return f"""
        You are a dedicated Scribe. {part_info}
        The student wants **EXHAUSTIVE, DEEP NOTES** of this {context_type}.
        Output Structure:
        1. **Minute-by-Minute Walkthrough:** Detailed chronological notes.
        2. **All Arguments:** Explain the logic behind every point.
        3. **All Examples:** Write down every example given.
        4. **Visuals:** Describe every graph/chart in detail.
        Leave nothing out.
        """
    else: 
        return f"""
        You are an expert Academic Tutor. {part_info}
        The student wants **STANDARD STUDY NOTES** of this {context_type}.
        Output Structure:
        1. **Key Concepts:** Definitions and Explanations.
        2. **Main Arguments:** The core logic.
        3. **Visuals:** Describe important charts/diagrams.
        4. **Exam Predictions:** What is likely to be tested?
        """

# --- MEDIA FUNCTIONS ---
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
    except Exception as e:
        st.error(f"Error reading duration: {e}")
        return 0

def cut_media_fast(input_path, output_path, start_time, end_time):
    ffmpeg_exe = get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe, "-y", "-i", input_path,
        "-ss", str(start_time), "-to", str(end_time),
        "-c", "copy", output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def split_and_process_media(original_file_path, api_key, detail_level):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-pro")
    
    duration_sec = get_media_duration(original_file_path)
    if duration_sec == 0: return

    chunk_size_sec = 2400 
    total_chunks = math.ceil(duration_sec / chunk_size_sec)
    
    # --- HERE IS THE FIX ---
    # I added the message back and made it a Warning box (Yellow) so it pops.
    st.warning(f"🍿 Video is {duration_sec/60:.0f} mins long. Style: {detail_level}.\n\nThis will take a few minutes... Time for a Reels break! 📱")
    
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
                
                context_type = "audio recording" if ext in ['.mp3', '.wav', '.m4a'] else "video lecture"
                part_info = f"You are analyzing Part {i+1} of a {total_chunks}-part lecture."
                system_prompt = get_system_prompt(detail_level, context_type, part_info)
                
                response = model.generate_content([video_file, system_prompt])
                
                st.session_state["master_notes"] += f"\n\n# 📼 Part {i+1} ({start_time//60}m - {end_time//60}m)\n"
                st.session_state["master_notes"] += response.text
                
                status.update(label=f"✅ Part {i+1} Done!", state="complete", expanded=False)
                
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)
        
        progress_bar.progress((i + 1) / total_chunks)

def process_text_file(file_content, api_key, detail_level):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-pro")
    
    with st.spinner(f'🧠 Generating {detail_level} notes...'):
        try:
            system_prompt = get_system_prompt(detail_level, "transcript text", "")
            response = model.generate_content([system_prompt, file_content])
            st.session_state["master_notes"] += "\n\n# 📄 Transcript Notes\n"
            st.session_state["master_notes"] += response.text
            st.success("Transcript Analyzed!")
        except Exception as e:
            st.error(f"Error processing text: {e}")

# --- MAIN APP ---
st.title("🎓 Lecture-to-Notes Pro")
st.write("Upload Video, Audio, or Transcripts. Choose your detail level.")

uploaded_file = st.file_uploader("Upload File", type=["mp4", "mov", "avi", "mkv", "mp3", "wav", "m4a", "txt", "md", "srt", "vtt"])

if uploaded_file is not None:
    if not api_key:
        st.error("⚠️ Please enter API Key in sidebar.")
    else:
        if st.button("Start Magic Processing ✨"):
            file_ext = os.path.splitext(uploaded_file.name)[1].lower()
            
            if file_ext in ['.txt', '.md', '.srt', '.vtt']:
                string_data = uploaded_file.read().decode("utf-8")
                process_text_file(string_data, api_key, detail_level)
                st.balloons()
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    original_path = tmp_file.name
                
                try:
                    split_and_process_media(original_path, api_key, detail_level)
                    st.balloons()
                finally:
                    if os.path.exists(original_path):
                        os.unlink(original_path)

# --- RESULTS AREA ---
if st.session_state["master_notes"]:
    st.markdown("---")
    st.success("🎉 Processing Complete! Your notes are ready below.")
    
    tab1, tab2 = st.tabs(["📖 Read Notes", "📋 Copy Raw Text"])
    
    with tab1:
        st.markdown(st.session_state["master_notes"])
    
    with tab2:
        st.text_area("Click inside, Select All (Ctrl+A), then Copy (Ctrl+C)", 
                     value=st.session_state["master_notes"], 
                     height=400)
    
    st.download_button(
        label="📥 Download as File",
        data=st.session_state["master_notes"],
        file_name="Lecture_Study_Guide.md",
        mime="text/markdown"
    )