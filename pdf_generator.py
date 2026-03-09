from fpdf import FPDF
import os
import tempfile
from datetime import datetime

class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.cyrillic_font = False
        fonts_dir = "fonts"
        if not os.path.exists(fonts_dir):
            os.makedirs(fonts_dir)
        
        dejavu_regular = os.path.join(fonts_dir, "DejaVuSans.ttf")
        dejavu_bold = os.path.join(fonts_dir, "DejaVuSans-Bold.ttf")
        dejavu_italic = os.path.join(fonts_dir, "DejaVuSans-Oblique.ttf")
        
        if os.path.exists(dejavu_regular):
            self.add_font('DejaVu', '', dejavu_regular, uni=True)
            self.add_font('DejaVu', 'B', dejavu_bold, uni=True)
            self.add_font('DejaVu', 'I', dejavu_italic, uni=True)
            self.set_font('DejaVu', '', 12)  # устанавливаем шрифт по умолчанию
            self.cyrillic_font = True
        else:
            print("WARNING: DejaVu fonts not found. PDF will not support Cyrillic. Download them and place in 'fonts' folder.")
            self.set_font('helvetica', '', 12)

    def header(self):
        self.set_font('DejaVu' if self.cyrillic_font else 'helvetica', 'B', 16)
        self.cell(0, 10, 'ЕГЭ 2026 - Конспект', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('DejaVu' if self.cyrillic_font else 'helvetica', 'I', 8)
        self.cell(0, 10, f'Страница {self.page_no()}', 0, 0, 'C')

    def add_title(self, title):
        self.set_font('DejaVu' if self.cyrillic_font else 'helvetica', 'B', 14)
        self.multi_cell(0, 10, title)
        self.ln(5)

    def add_content(self, content):
        self.set_font('DejaVu' if self.cyrillic_font else 'helvetica', '', 12)
        paragraphs = content.split('\n')
        for p in paragraphs:
            if p.strip():
                self.multi_cell(0, 10, p.strip())
                self.ln(5)

def generate_pdf(theme_name: str, content: str) -> str:
    pdf = PDF()
    pdf.add_page()
    pdf.add_title(theme_name)
    pdf.add_content(content)
    
    temp_dir = tempfile.gettempdir()
    filename = f"conspect_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = os.path.join(temp_dir, filename)
    pdf.output(filepath)
    return filepath