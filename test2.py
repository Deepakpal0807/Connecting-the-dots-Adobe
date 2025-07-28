import os
import json
import time
import re
import fitz
from collections import Counter

class PDFOutlineExtractor:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self.text_elements_by_page = {}
        self.font_sizes = []
        self._extract_text_elements()

    def _extract_text_elements(self):
        for page_num in range(self.doc.page_count):
            page = self.doc.load_page(page_num)
            blocks = page.get_text("dict")["blocks"]
            page_elements = []
            for b in blocks:
                if b['type'] == 0:
                    for line in b["lines"]:
                        for span in line["spans"]:
                            text = span["text"].strip()
                            if text:
                                font_size = round(span["size"], 2)
                                font_name = span["font"]
                                is_bold = "bold" in font_name.lower() or "heavy" in font_name.lower()
                                bbox = span["bbox"]
                                y_pos = bbox[1] 
                                x_pos = bbox[0]
                                page_elements.append({
                                    "text": text,
                                    "font_size": font_size,
                                    "font_name": font_name,
                                    "is_bold": is_bold,
                                    "x_pos": x_pos,
                                    "y_pos": y_pos,
                                    "page": page_num + 1
                                })
                                self.font_sizes.append(font_size)
            self.text_elements_by_page[page_num + 1] = page_elements

    def _get_common_font_sizes(self):
        if not self.font_sizes:
            return {}
        rounded_font_sizes = [round(s, 1) for s in self.font_sizes]
        font_counts = Counter(rounded_font_sizes)
        sorted_fonts = sorted(font_counts.items(), key=lambda item: (-item[1], -item[0]))
        return {size: count for size, count in sorted_fonts}

    def extract_outline(self):
        outline = []
        title = ""
        
        common_fonts = self._get_common_font_sizes()
        
        body_font_size = None
        if common_fonts:
            for size, count in common_fonts.items():
                if size < 20 and count > (self.doc.page_count * 5): 
                    body_font_size = size
                    break
            if body_font_size is None and common_fonts:
                 body_font_size = min(common_fonts.keys())

        title_candidates = []
        max_title_size = 0
        
        for page_num in range(1, min(4, self.doc.page_count + 1)):
            page = self.doc.load_page(page_num - 1)
            for element in self.text_elements_by_page.get(page_num, []):
                if element["y_pos"] < (page.rect.height / 3) and element["font_size"] > max_title_size:
                    max_title_size = element["font_size"]
                    title_candidates.append(element)

        if title_candidates:
            title_candidates.sort(key=lambda x: (-x["font_size"], x["y_pos"], x["x_pos"]))
            
            if body_font_size:
                if title_candidates[0]["font_size"] > (body_font_size * 1.5): 
                    title = title_candidates[0]["text"]
            else:
                if title_candidates[0]["font_size"] > 18:
                    title = title_candidates[0]["text"]
        
        all_elements_sorted = []
        for page_num in range(1, self.doc.page_count + 1):
            all_elements_sorted.extend(sorted(self.text_elements_by_page.get(page_num, []), key=lambda x: (x["y_pos"], x["x_pos"])))

        unique_sizes = sorted(list(set(self.font_sizes)), reverse=True)
        
        h1_size_threshold = 0
        h2_size_threshold = 0
        h3_size_threshold = 0

        if unique_sizes:
            relevant_sizes = [s for s in unique_sizes if body_font_size is None or s > (body_font_size * 1.05)]
            
            if relevant_sizes:
                h1_size_threshold = relevant_sizes[0]
                if len(relevant_sizes) > 1:
                    h2_size_threshold = relevant_sizes[1]
                else:
                    h2_size_threshold = h1_size_threshold * 0.9 if h1_size_threshold > 12 else h1_size_threshold
                
                if len(relevant_sizes) > 2:
                    h3_size_threshold = relevant_sizes[2]
                else:
                    h3_size_threshold = h2_size_threshold * 0.9 if h2_size_threshold > 10 else h2_size_threshold

            if h2_size_threshold >= h1_size_threshold and len(relevant_sizes) > 1:
                h2_size_threshold = (h1_size_threshold + relevant_sizes[1]) / 2 if h1_size_threshold > relevant_sizes[1] else h1_size_threshold * 0.95
            if h3_size_threshold >= h2_size_threshold and len(relevant_sizes) > 2:
                h3_size_threshold = (h2_size_threshold + relevant_sizes[2]) / 2 if h2_size_threshold > relevant_sizes[2] else h2_size_threshold * 0.95

            if h1_size_threshold - h2_size_threshold < 1.0 and h2_size_threshold > 1.0:
                h2_size_threshold = max(h2_size_threshold, h1_size_threshold - 1.5)
            if h2_size_threshold - h3_size_threshold < 1.0 and h3_size_threshold > 1.0:
                h3_size_threshold = max(h3_size_threshold, h2_size_threshold - 1.5)

        min_heading_font_size = body_font_size * 1.1 if body_font_size else 12 

        for element in all_elements_sorted:
            text = element["text"]
            font_size = element["font_size"]
            is_bold = element["is_bold"]
            page_num = element["page"]
            x_pos = element["x_pos"]

            if title and (text.strip().lower() == title.strip().lower()) and abs(font_size - max_title_size) < 1:
                continue
            
            if len(text.split()) < 2 and not re.match(r'^\d+(\.\d+)*$', text.strip()): 
                continue

            is_numbered_heading = bool(re.match(r'^((\d+(\.\d+)*)|([IVXLCDM]+\.)|([A-Z]\.))\s+.*', text.strip()))
            
            level = None
            if font_size >= h1_size_threshold and font_size >= min_heading_font_size and (is_bold or is_numbered_heading):
                level = "H1"
            elif font_size >= h2_size_threshold and font_size < h1_size_threshold and font_size >= min_heading_font_size and (is_bold or is_numbered_heading):
                level = "H2"
            elif font_size >= h3_size_threshold and font_size < h2_size_threshold and font_size >= min_heading_font_size and (is_bold or is_numbered_heading):
                level = "H3"
            elif is_numbered_heading and font_size >= min_heading_font_size * 0.9:
                if font_size >= h3_size_threshold:
                    level = "H3"
                elif font_size >= h2_size_threshold:
                    level = "H2"
                else: 
                    level = "H3"

            if level:
                if not outline or not (outline[-1]["text"].strip().lower() == text.strip().lower() and outline[-1]["page"] == page_num):
                    outline.append({
                        "level": level,
                        "text": text.strip(),
                        "page": page_num
                    })

        processed_outline = []
        last_level_h1 = None
        last_level_h2 = None

        for item in outline:
            current_level = item["level"]
            
            if current_level == "H1":
                processed_outline.append(item)
                last_level_h1 = item
                last_level_h2 = None
            elif current_level == "H2":
                if last_level_h1 is None:
                    item["level"] = "H1"
                    processed_outline.append(item)
                    last_level_h1 = item
                    last_level_h2 = None
                else:
                    processed_outline.append(item)
                    last_level_h2 = item
            elif current_level == "H3":
                if last_level_h2 is None and last_level_h1 is None:
                    item["level"] = "H1"
                    processed_outline.append(item)
                    last_level_h1 = item
                    last_level_h2 = None
                elif last_level_h2 is None:
                    item["level"] = "H2"
                    processed_outline.append(item)
                    last_level_h2 = item
                else:
                    processed_outline.append(item)

        return {
            "title": title,
            "outline": processed_outline
        }

    def close(self):
        self.doc.close()

def process_pdf_file(input_pdf_path, output_json_path):
    individual_start_time = time.time()
    try:
        print(f"Processing {os.path.basename(input_pdf_path)}...")
        extractor = PDFOutlineExtractor(input_pdf_path)
        extracted_data = extractor.extract_outline()
        
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(extracted_data, f, ensure_ascii=False, indent=4)
        
        extractor.close()
        individual_end_time = time.time()
        print(f"Completed {os.path.basename(input_pdf_path)} in {individual_end_time - individual_start_time:.2f} seconds.")
    except Exception as e:
        print(f"Error processing {os.path.basename(input_pdf_path)}: {e}")
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump({"error": str(e), "message": f"Failed to process {os.path.basename(input_pdf_path)}"}, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    global_start_time = time.time()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(base_dir, "app", "input")
    output_dir = os.path.join(base_dir, "app", "output")

    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".pdf")]

    if not pdf_files:
        print(f"No PDF files found in {input_dir}.")
        print(f"Please place your PDF documents inside the '{input_dir}' folder to process them.")
    else:
        for pdf_file in pdf_files:
            input_pdf_path = os.path.join(input_dir, pdf_file)
            output_json_filename = os.path.splitext(pdf_file)[0] + ".json"
            output_json_path = os.path.join(output_dir, output_json_filename)
            
            process_pdf_file(input_pdf_path, output_json_path)

    global_end_time = time.time()
    print(f"\nTotal script execution time: {global_end_time - global_start_time:.2f} seconds.")






