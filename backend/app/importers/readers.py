"""Turn an uploaded file (PDF, Excel or CSV) into a header row + data rows of plain strings."""
import csv
import io


class ImportError_(ValueError):
    pass


def _clean(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return " ".join(str(v).split())


def _find_header(rows: list[list[str]]) -> int:
    """The header is the first row with at least 2 non-empty cells."""
    for i, r in enumerate(rows):
        if sum(1 for c in r if c) >= 2:
            return i
    raise ImportError_("No table found in the file")


def _finish(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    rows = [[_clean(c) for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        raise ImportError_("The file is empty")
    h = _find_header(rows)
    header = rows[h]
    width = len(header)
    data = []
    for r in rows[h + 1:]:
        r = (r + [""] * width)[:width]
        if r == header:  # header repeated on each PDF page
            continue
        data.append(r)
    return header, data


def read_excel(content: bytes) -> tuple[list[str], list[list[str]]]:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001
        raise ImportError_(f"Could not open the Excel file: {e}") from e
    ws = wb.worksheets[0]
    return _finish([list(r) for r in ws.iter_rows(values_only=True)])


def read_csv(content: bytes) -> tuple[list[str], list[list[str]]]:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:2000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    return _finish(list(csv.reader(io.StringIO(text), delimiter=delim)))


def read_pdf(content: bytes) -> tuple[list[str], list[list[str]]]:
    import pdfplumber

    rows: list[list[str]] = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    rows.extend(table)
    except Exception as e:  # noqa: BLE001
        raise ImportError_(f"Could not read the PDF: {e}") from e
    if not rows:
        raise ImportError_(
            "No table found in the PDF. If it is a scan (photo of paper), "
            "export the original Word/Excel file instead."
        )
    return _finish(rows)


def read_table(filename: str, content: bytes) -> tuple[list[str], list[list[str]]]:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        return read_excel(content)
    if name.endswith(".csv"):
        return read_csv(content)
    if name.endswith(".pdf"):
        return read_pdf(content)
    raise ImportError_("Unsupported file type: use .xlsx, .csv or .pdf")
