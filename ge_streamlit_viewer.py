# ge_streamlit_viewer.py
import streamlit as st
import fitz  # PyMuPDF
import os

# Requirement: Full width layout
st.set_page_config(layout="wide", page_title="AI Book Explorer")

# Requirement: Font size 16 for legibility
st.markdown("""
    <style>
    html, body, [class*="css"] { font-size: 16px !important; }
    </style>
    """, unsafe_allow_html=True)

# Requirement: Load from env AI_BOOK
BASE_DIR = os.getenv("AI_BOOK", r"C:\Default\Path")

# --- LEFT PANE (Sidebar) ---
with st.sidebar:
    st.header("Library")
    # Requirement: Search PDF files
    search_term = st.text_input("Search PDF Files...", "")
    
    if os.path.exists(BASE_DIR):
        files = [f for f in os.listdir(BASE_DIR) if f.lower().endswith('.pdf')]
        filtered_files = [f for f in files if search_term.lower() in f.lower()]
    else:
        filtered_files = []
        st.error(f"Directory not found: {BASE_DIR}")
        
    selected_file = st.radio("Select a file:", filtered_files, index=0 if filtered_files else None)

# --- RIGHT PANE (Preview) ---
if selected_file:
    file_path = os.path.join(BASE_DIR, selected_file)
    
    # Requirement: Display path at top
    st.markdown(f"**Current File:** `{file_path}`")
    
    doc = fitz.open(file_path)
    total_pages = len(doc)
    
    # Navigation and Zoom Controls
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        # Requirement: Paging
        page_num = st.number_input("Page", min_value=1, max_value=total_pages, value=1) - 1
    with col2:
        # Requirement: Zoom
        zoom = st.slider("Zoom Level", min_value=1.0, max_value=4.0, value=1.5, step=0.5)
    with col3:
        # Requirement: Search within PDF
        pdf_search = st.text_input("Find text in PDF (Press Enter):", "")
        if pdf_search:
            for i in range(total_pages):
                if pdf_search.lower() in doc[i].get_text().lower():
                    st.success(f"Found on page {i + 1}. Change page number to view.")
                    break
            else:
                st.warning("Text not found.")

    # Requirement: Direct render without converting to files
    page = doc[page_num]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    
    # CRITICAL FIX: Replaced 'use_container_width=True' with 'width="stretch"' 
    # to resolve the 2026 deprecation warning.
    st.image(pix.tobytes("jpeg"), width="stretch")

else:
    st.info("👈 Select a PDF from the sidebar to begin.")