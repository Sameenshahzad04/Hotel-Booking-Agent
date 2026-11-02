from pathlib import Path

import pdfplumber
from docx import Document
from tabulate import tabulate
from typing import List, Dict, Any, Set
from config import config

class TableExtractor:
    def __init__(self):
        pass
    
    def extract_tables_from_pdf(self, file_path: Path) -> List[Dict[str, Any]]:
        tables = []
        try:
            with pdfplumber.open(str(file_path)) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_tables = page.extract_tables()
                    for table_idx, table_data in enumerate(page_tables):
                        if table_data and len(table_data) > 1:
                            cleaned_data = self._clean_table_data(table_data)
                            markdown = self._convert_to_markdown(cleaned_data)
                            tables.append({
                                "page": page_num + 1,
                                "table_index": table_idx,
                                "data": cleaned_data,
                                "markdown": markdown,
                                "num_rows": len(cleaned_data),
                                "num_cols": len(cleaned_data[0]) if cleaned_data else 0
                            })
        except Exception as e:
            print(f"⚠️ Table extraction skipped for {file_path.name}: {e}")
        return tables
    
    def extract_tables_from_docx(self, file_path: Path) -> List[Dict[str, Any]]:
        tables = []
        try:
            doc = Document(str(file_path))

            # Build an ordered list of all block elements (paragraphs + tables)
            # so we can find the nearest heading/paragraph before each table
            from docx.oxml.ns import qn
            body = doc.element.body
            block_items = list(body)  # raw XML elements in order

            # Map each table XML element to its index in the body
            table_xml_to_idx = {tbl._element: i for i, tbl in enumerate(doc.tables)}

            # Collect all body elements with their text (paragraphs only)
            body_paragraphs = []
            for elem in block_items:
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag == "p":
                    text = "".join(
                        node.text or ""
                        for node in elem.iter()
                        if node.tag.endswith("}t") or node.tag == "t"
                    ).strip()
                    body_paragraphs.append(("p", text, elem))
                elif tag == "tbl":
                    body_paragraphs.append(("tbl", None, elem))

            for table_idx, table in enumerate(doc.tables):
                table_data = []
                for row in table.rows:
                    row_data = [cell.text.strip() for cell in row.cells]
                    table_data.append(row_data)

                if table_data and len(table_data) > 1:
                    markdown = self._convert_to_markdown(table_data)

                    # Find the nearest non-empty paragraph before this table element
                    tbl_elem = table._element
                    heading = ""
                    for kind, text, elem in reversed(body_paragraphs):
                        if elem is tbl_elem:
                            continue
                        if kind == "p" and text:
                            heading = text
                            break

                    tables.append({
                        "page": 0,
                        "table_index": table_idx,
                        "data": table_data,
                        "markdown": markdown,
                        "heading": heading,          # ← captured section heading
                        "num_rows": len(table_data),
                        "num_cols": len(table_data[0]) if table_data else 0
                    })
        except Exception as e:
            print(f"⚠️ Failed to extract tables from DOCX {file_path.name}: {str(e)}")

        return tables
    
    def _clean_table_data(self, table_data: List[List[str]]) -> List[List[str]]:
        cleaned = []
        for row in table_data:
            cleaned_row = []
            for cell in row:
                if cell is None:
                    cleaned_row.append("")
                else:
                    cleaned_row.append(str(cell).strip())
            cleaned.append(cleaned_row)
        return cleaned
    
    def _convert_to_markdown(self, table_data: List[List[str]]) -> str:
        if not table_data or len(table_data) < 2:
            return ""
        try:
            headers = table_data[0]
            data_rows = table_data[1:]
            return tabulate(data_rows, headers=headers, tablefmt="github")
        except Exception:
            return self._simple_markdown_fallback(table_data)
    
    def _simple_markdown_fallback(self, table_data: List[List[str]]) -> str:
        if not table_data:
            return ""
        lines = []
        header = "| " + " | ".join(str(cell) for cell in table_data[0]) + " |"
        lines.append(header)
        separator = "| " + " | ".join("---" for _ in table_data[0]) + " |"
        lines.append(separator)
        for row in table_data[1:]:
            data_row = "| " + " | ".join(str(cell) for cell in row) + " |"
            lines.append(data_row)
        return "\n".join(lines)
    
    def extract_all_tables(self, file_path: Path) -> List[Dict[str, Any]]:
        file_ext = file_path.suffix.lower()
        if file_ext == ".pdf":
            return self.extract_tables_from_pdf(file_path)
        elif file_ext in [".docx", ".doc"]:
            return self.extract_tables_from_docx(file_path)
        return []

def _is_outside_all_tables(obj: dict, table_bboxes: list) -> bool:
    """
    Returns True if the PDF object is NOT inside any table bounding box.
    Used with pdfplumber's page.filter() to exclude table regions cleanly.

    How it works:
    - Every character/word in pdfplumber is a dict with x0, top, x1, bottom keys
    - A table bbox is a rectangle: (x0, top, x1, bottom)
    - If the object sits inside that rectangle → it belongs to the table → exclude it
    - If it's outside all tables → it's paragraph text → keep it
    """
    obj_x0 = obj.get("x0", 0)
    obj_x1 = obj.get("x1", 0)
    obj_top = obj.get("top", 0)
    obj_bottom = obj.get("bottom", 0)
    for (tbl_x0, tbl_top, tbl_x1, tbl_bottom) in table_bboxes:
        if (obj_x0 >= tbl_x0 and obj_x1 <= tbl_x1
                and obj_top >= tbl_top and obj_bottom <= tbl_bottom):
            return False   # inside a table → exclude
    return True            # outside all tables → keep


def extract_from_pdf(file_path: Path) -> str:
    """
    Extract only paragraph text from a PDF, skipping table regions.

    Strategy:
    1. For each page, find all table bounding boxes using find_tables()
    2. Use page.filter() to get a new page containing only NON-table objects
    3. Call extract_text() on that filtered page normally — preserves line breaks

    Tables are already extracted cleanly by TableExtractor.extract_tables_from_pdf(),
    so we must NOT duplicate table content here in a garbled form.
    """
    try:
        text = ""
        with pdfplumber.open(str(file_path)) as pdf:
            for i, page in enumerate(pdf.pages):
                # Step 1: find where tables are on this page
                table_bboxes = [tbl.bbox for tbl in page.find_tables()]

                if table_bboxes:
                    # Step 2: filter page — keep only objects OUTSIDE table regions
                    # page.filter(fn) returns a new DerivedPage where fn(obj) is True
                    filtered_page = page.filter(
                        lambda obj: _is_outside_all_tables(obj, table_bboxes)
                    )
                    # Step 3: extract text normally — line breaks preserved ✅
                    page_text = (filtered_page.extract_text() or "").strip()
                else:
                    # No tables on this page → extract everything as-is
                    page_text = (page.extract_text() or "").strip()

                if page_text:
                    text += f"\n--- Page {i + 1} ---\n"
                    text += page_text

        return text.strip()
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF {file_path}: {str(e)}")

def extract_from_docx(file_path: Path) -> str:
    try:
        doc = Document(str(file_path))
        text = ""
        for para in doc.paragraphs:
            if para.text.strip():
                text += para.text + "\n"
        return text.strip()
    except Exception as e:
        raise ValueError(f"Failed to extract text from DOCX {file_path}: {str(e)}")

def extract_from_txt(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        return file_path.read_text(encoding="latin-1").strip()

def extract_text(file_path: Path) -> str:
    file_ext = file_path.suffix.lower()
    if file_ext == ".pdf":
        return extract_from_pdf(file_path)
    elif file_ext in [".docx", ".doc"]:
        return extract_from_docx(file_path)
    elif file_ext == ".txt":
        return extract_from_txt(file_path)
    return ""

def load_documents(exclude_filenames: Set[str] = None) -> List[Dict[str, Any]]:
    exclude_filenames = exclude_filenames or set()
    documents_data = []
    table_extractor = TableExtractor()
    doc_id_counter = 1

    if not config.CORPUS_DIR.exists():
        print(f"⚠️ Warning: Corpus directory {config.CORPUS_DIR} not found.")
        return []

    for file_path in config.CORPUS_DIR.glob("**/*"):
        if file_path.is_file():
            if file_path.name in exclude_filenames:
                continue

            if file_path.suffix.lower() not in [".pdf", ".docx", ".doc", ".txt"]:
                continue

            try:
                text_content = extract_text(file_path)
                tables_data = table_extractor.extract_all_tables(file_path)
                
                filename_lower = file_path.name.lower()
                if any(kw in filename_lower for kw in ["refund", "bill", "invoice", "payment", "pricing", "legal", "terms"]):
                    doc_category = "policy_refund"
                elif any(kw in filename_lower for kw in ["sop", "front office", "housekeeping", "concierge"]):
                    doc_category = "operations_sop"
                elif any(kw in filename_lower for kw in ["banquet", "event", "rooftop"]):
                    doc_category = "events_banquet"
                else:
                    doc_category = "amenities_general"
                
                if text_content or tables_data:
                    documents_data.append({
                        "doc_id": doc_id_counter,
                        "filename": file_path.name,
                        "file_type": file_path.suffix.lower(),
                        "category": doc_category,
                        "text": text_content,
                        "tables": tables_data
                    })
                    doc_id_counter += 1
            except Exception as e:
                print(f"⚠️ Error parsing file {file_path.name}: {e}")

    return documents_data
