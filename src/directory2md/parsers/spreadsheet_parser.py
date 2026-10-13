"""Spreadsheet document parser for Excel (.xlsx), OpenDocument (.ods), and CSV/TSV files.

Extracts structured sheet names, headers, table rows, and numerical data into plain text
for search indexing, entity recognition, and financial data analysis.
"""

from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import List, Tuple

from directory2md.models import DocumentMetadata
from directory2md.parsers.base import BaseParser


class SpreadsheetParser(BaseParser):
    """Parser for spreadsheet formats including Excel (.xlsx), ODF Spreadsheet (.ods), and CSV/TSV."""

    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        """Parse spreadsheet file and return its metadata and extracted textual tabular data.

        Args:
            filepath: Path to the target spreadsheet.

        Returns:
            Tuple of (:class:`DocumentMetadata`, extracted_full_text).
        """
        metadata = self.build_initial_metadata(filepath)
        suffix = filepath.suffix.lower()

        extracted_text = ""
        try:
            if suffix in (".csv", ".tsv"):
                extracted_text = self._parse_csv_tsv(filepath)
            elif suffix == ".xlsx":
                extracted_text = self._parse_xlsx(filepath)
            elif suffix == ".ods":
                extracted_text = self._parse_ods(filepath)
            else:
                extracted_text = self._parse_csv_tsv(filepath)
        except Exception as exc:
            extracted_text = f"[Error parsing spreadsheet {filepath.name}: {exc}]"

        clean_text = extracted_text.strip()
        words = clean_text.split()
        metadata.word_count = len(words)
        metadata.text_snippet = " ".join(words[:40]) if words else ""
        metadata.extracted_text = clean_text

        return metadata, clean_text

    def _parse_csv_tsv(self, filepath: Path) -> str:
        """Parse CSV or TSV file detecting common delimiters.

        Args:
            filepath: Path to the CSV/TSV file.

        Returns:
            Structured plain text representation of the tabular rows.
        """
        encodings = ["utf-8", "latin-1", "cp1252"]
        content = None
        for enc in encodings:
            try:
                content = filepath.read_text(encoding=enc)
                break
            except (UnicodeDecodeError, OSError):
                continue

        if not content:
            return ""

        # Detect delimiter
        sample = content[:4096]
        delimiter = ","
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample, delimiters=[",", ";", "\t", "|"])
            delimiter = dialect.delimiter
        except Exception:
            if "\t" in sample:
                delimiter = "\t"
            elif ";" in sample:
                delimiter = ";"

        lines: List[str] = []
        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        for row in reader:
            cleaned_cells = [cell.strip() for cell in row if cell.strip()]
            if cleaned_cells:
                lines.append(" | ".join(cleaned_cells))

        return "\n".join(lines)

    def _parse_xlsx(self, filepath: Path) -> str:
        """Extract sheets and cells from an OpenXML .xlsx archive.

        Args:
            filepath: Path to the .xlsx workbook.

        Returns:
            Structured textual representation of all sheets and rows.
        """
        output_sections: List[str] = []

        with zipfile.ZipFile(filepath, "r") as zf:
            # 1. Read shared strings if present
            shared_strings: List[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                xml_data = zf.read("xl/sharedStrings.xml")
                root = ET.fromstring(xml_data)
                # XML namespace handling
                ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for si in root.findall(".//main:si", ns) or root.findall(".//si"):
                    texts = [t.text for t in (si.findall(".//main:t", ns) or si.findall(".//t")) if t.text]
                    shared_strings.append("".join(texts))

            # 2. Read sheet names from workbook.xml
            sheet_names: List[str] = []
            if "xl/workbook.xml" in zf.namelist():
                wb_data = zf.read("xl/workbook.xml")
                wb_root = ET.fromstring(wb_data)
                for sheet in wb_root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet") or wb_root.findall(".//sheet"):
                    name = sheet.attrib.get("name")
                    if name:
                        sheet_names.append(name)

            # 3. Read sheet XMLs
            sheet_files = sorted([f for f in zf.namelist() if f.startswith("xl/worksheets/sheet") and f.endswith(".xml")])
            for idx, sheet_file in enumerate(sheet_files):
                sheet_title = sheet_names[idx] if idx < len(sheet_names) else f"Sheet{idx+1}"
                sheet_lines: List[str] = [f"--- Sheet: {sheet_title} ---"]
                
                sheet_data = zf.read(sheet_file)
                sheet_root = ET.fromstring(sheet_data)

                # Find rows
                rows = sheet_root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row") or sheet_root.findall(".//row")
                for row in rows:
                    cells = row.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c") or row.findall(".//c")
                    row_vals: List[str] = []
                    for c in cells:
                        cell_type = c.attrib.get("t", "")
                        v_tag = c.find(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                        if v_tag is None:
                            v_tag = c.find(".//v")
                        
                        if v_tag is not None and v_tag.text:
                            raw_val = v_tag.text.strip()
                            if cell_type == "s" and raw_val.isdigit():
                                str_idx = int(raw_val)
                                if 0 <= str_idx < len(shared_strings):
                                    row_vals.append(shared_strings[str_idx])
                                else:
                                    row_vals.append(raw_val)
                            else:
                                row_vals.append(raw_val)
                        else:
                            # Inline string
                            t_tag = c.find(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t") or c.find(".//t")
                            if t_tag is not None and t_tag.text:
                                row_vals.append(t_tag.text.strip())

                    if row_vals:
                        sheet_lines.append(" | ".join(row_vals))

                if len(sheet_lines) > 1:
                    output_sections.append("\n".join(sheet_lines))

        return "\n\n".join(output_sections)

    def _parse_ods(self, filepath: Path) -> str:
        """Extract tables and cell text from an OpenDocument Spreadsheet (.ods) as Markdown tables.

        Args:
            filepath: Path to the .ods file.

        Returns:
            Structured Markdown representation of all sheets and rows.
        """
        output_sections: List[str] = []

        with zipfile.ZipFile(filepath, "r") as zf:
            if "content.xml" not in zf.namelist():
                return ""

            xml_data = zf.read("content.xml")
            root = ET.fromstring(xml_data)

            # Namespaces
            ns = {
                "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
                "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
            }

            tables = root.findall(".//table:table", ns)
            for table in tables:
                table_name = table.attrib.get(f"{{{ns['table']}}}name", "Sheet")
                sheet_lines: List[str] = [f"## Sheet: {table_name}\n"]

                rows = table.findall(".//table:table-row", ns)
                is_first_row = True
                for row in rows:
                    cells = row.findall(".//table:table-cell", ns)
                    row_vals: List[str] = []
                    for cell in cells:
                        paragraphs = cell.findall(".//text:p", ns)
                        cell_texts = [p.text.strip().replace("|", "\\|") for p in paragraphs if p.text and p.text.strip()]
                        if cell_texts:
                            row_vals.append(" ".join(cell_texts))
                    
                    if row_vals:
                        sheet_lines.append(f"| {' | '.join(row_vals)} |")
                        if is_first_row:
                            sheet_lines.append(f"| {' | '.join([':---'] * len(row_vals))} |")
                            is_first_row = False

                if len(sheet_lines) > 1:
                    output_sections.append("\n".join(sheet_lines))

        return "\n\n".join(output_sections)

