# utils/ocr_utils.py
import pytesseract
import cv2
import numpy as np
import re

# --- HARDCODE THE TESSERACT PATH (FOR YOUR MACHINE) ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def preprocess_image(image_bytes):
    """
    Enhanced preprocessing to improve OCR accuracy.
    Returns processed image or None if invalid.
    """
    # Check if bytes are empty
    if not image_bytes or len(image_bytes) < 100:
        return None
    
    nparr = np.frombuffer(image_bytes, np.uint8)
    if len(nparr) == 0:
        return None
    
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Resize if too small (OCR works better on larger text)
    height, width = gray.shape
    if width < 800:
        scale = 800 / width
        new_width = int(width * scale)
        new_height = int(height * scale)
        gray = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
    
    # Apply sharpening filter
    kernel = np.array([[-1,-1,-1],
                       [-1, 9,-1],
                       [-1,-1,-1]])
    sharpened = cv2.filter2D(gray, -1, kernel)
    
    # Apply adaptive thresholding
    thresh = cv2.adaptiveThreshold(sharpened, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 11, 2)
    return thresh

def clean_ocr_text(text):
    """
    Fix common OCR errors.
    """
    replacements = {
        '@': '(',
        'B': '0',
        'y': '0',
        'J': '1',
        '|': '1',
        '©': '(',
        '‘': "'",
        '’': "'",
        '“': '"',
        '”': '"',
        '‑': '-',   # non-breaking hyphen
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def extract_text_from_image(image_bytes):
    """
    Takes uploaded image bytes, processes it, and returns extracted text.
    Returns error message as string if something fails.
    """
    try:
        # Preprocess the image
        thresh = preprocess_image(image_bytes)
        
        if thresh is None:
            return "ERROR: Image is empty or corrupted. Please upload a valid PNG/JPG file."
        
        # Run OCR with PSM 6 (block of text)
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-:() '
        text = pytesseract.image_to_string(thresh, config=custom_config)
        
        # If result is too short, try PSM 4 (column)
        if len(text.strip()) < 20:
            custom_config2 = r'--oem 3 --psm 4'
            text2 = pytesseract.image_to_string(thresh, config=custom_config2)
            if len(text2.strip()) > len(text.strip()):
                text = text2
        
        # Clean up common OCR errors
        text = clean_ocr_text(text)
        
        # Clean up extra spaces/newlines
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
        
    except Exception as e:
        return f"ERROR: OCR failed - {str(e)}"