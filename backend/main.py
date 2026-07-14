"""
家庭收支小管家 - Google Sheets API Backend
部署於 Railway，透過 Service Account 讀寫 Google Sheets
"""

import os
import json
from datetime import datetime
from typing import Optional

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import gspread

# ====== 設定 ======
# Serve static frontend files
STATIC_DIR = Path(__file__).resolve().parent.parent  # backend/ → project root (where index.html lives)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
SHEET_KEY = os.environ.get("SHEET_KEY", "10257dP7ZcVqT5gIp8OPf-t78rJK8XyouXpxzjZY7AHQ")
CRED_PATH = os.environ.get("CRED_PATH", "/etc/secrets/google_creds.json")

# Chinese font for PDF export
CJK_FONT = "/usr/share/fonts/truetype/arphic/uming.ttc"

app = FastAPI(title="家庭收支小管家 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static assets (icon.png, etc.)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Serve index.html at root
@app.get("/")
def serve_frontend():
    return FileResponse(str(STATIC_DIR / "index.html"), media_type="text/html")

SHEET = None  # lazy init


def get_sheet():
    global SHEET
    if SHEET is not None:
        return SHEET

    # Try Railway secret mount first, then env json, then local file
    creds_data = None
    if os.path.exists(CRED_PATH):
        with open(CRED_PATH) as f:
            creds_data = json.load(f)
    elif "GOOGLE_CREDS_JSON" in os.environ:
        creds_data = json.loads(os.environ["GOOGLE_CREDS_JSON"])

    if not creds_data:
        # Fallback: try local dev path
        local_path = "/home/clement/HermesProjects/google_creds.json"
        if os.path.exists(local_path):
            with open(local_path) as f:
                creds_data = json.load(f)

    if not creds_data:
        raise HTTPException(500, "Google credentials not configured")

    gc = gspread.service_account_from_dict(creds_data)
    sh = gc.open_by_key(SHEET_KEY)
    SHEET = sh
    return SHEET


def ensure_sheets():
    """Ensure required worksheets exist"""
    sh = get_sheet()
    try:
        tx_sheet = sh.worksheet("收支紀錄")
        # Ensure new column exists (migration for existing sheets)
        try:
            tx_sheet.update("H1", "支付方式")
        except Exception:
            pass
    except Exception:
        tx_sheet = sh.add_worksheet("收支紀錄", 1000, 8)
        tx_sheet.update("A1:H1", [["ID", "日期", "類別", "分類", "金額", "備註", "建立時間", "支付方式"]])
        tx_sheet.format("A1:H1", {"textFormat": {"bold": True}})

    try:
        bg_sheet = sh.worksheet("預算設定")
    except Exception:
        bg_sheet = sh.add_worksheet("預算設定", 1000, 3)
        bg_sheet.update("A1:C1", [["分類", "預算金額", "月份"]])
        bg_sheet.format("A1:C1", {"textFormat": {"bold": True}})

    return tx_sheet, bg_sheet


# ====== Pydantic Models ======
class TransactionIn(BaseModel):
    id: Optional[str] = None
    date: str
    type: str  # income / expense
    category: str
    amount: float
    note: str = ""
    pay_method: str = ""


class TransactionUpdate(BaseModel):
    id: str
    date: Optional[str] = None
    type: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    note: Optional[str] = None
    pay_method: Optional[str] = None


class TransactionDelete(BaseModel):
    id: str


class BudgetSave(BaseModel):
    budgets: dict
    month: Optional[str] = None


# ====== API Endpoints ======
@app.get("/")
def root():
    return {"status": "ok", "message": "家庭收支小管家 API"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/transactions")
def get_transactions():
    tx_sheet, _ = ensure_sheets()
    rows = tx_sheet.get_all_values()
    if len(rows) <= 1:
        return {"success": True, "data": []}

    result = []
    updates = {}  # row_index -> [id, createdAt]
    for i, row in enumerate(rows[1:], start=2):  # sheet row index (1-based)
        # 自動補上空白 ID 和建立時間
        if not row[0]:
            row[0] = str(int(datetime.now().timestamp() * 1000)) + "_" + os.urandom(3).hex()
            row[6] = datetime.now().isoformat()
            updates[i] = [row[0], row[6]]
        if not row[6]:
            now = datetime.now().isoformat()
            row[6] = now
            if i not in updates:
                updates[i] = [row[0], now]

        result.append({
            "id": row[0],
            "date": row[1],
            "type": row[2],
            "category": row[3],
            "amount": float(row[4]) if row[4] else 0,
            "note": row[5] if len(row) > 5 else "",
            "createdAt": row[6] if len(row) > 6 else "",
            "pay_method": row[7] if len(row) > 7 else "",
        })

    # 如果有缺 ID 或建立時間的列，寫回 Sheets 補上
    if updates:
        try:
            for row_idx, (new_id, new_ct) in updates.items():
                tx_sheet.update_cell(row_idx, 1, new_id)   # column A = ID
                tx_sheet.update_cell(row_idx, 7, new_ct)   # column G = 建立時間
        except Exception:
            pass  # 補寫失敗不影響回傳結果

    return {"success": True, "data": result}


@app.post("/api/transactions")
def add_transaction(tx: TransactionIn):
    tx_sheet, _ = ensure_sheets()
    tx_id = tx.id or str(int(datetime.now().timestamp() * 1000)) + "_" + os.urandom(3).hex()
    now = datetime.now().isoformat()
    amount = tx.amount

    # Insert at row 2 (below header)
    tx_sheet.insert_row([tx_id, tx.date, tx.type, tx.category, amount, tx.note, now, tx.pay_method], 2)
    return {"success": True, "id": tx_id}


@app.put("/api/transactions")
def update_transaction(tx: TransactionUpdate):
    tx_sheet, _ = ensure_sheets()
    rows = tx_sheet.get_all_values()

    row_idx = None
    old_amount = 0
    for i, row in enumerate(rows):
        if i > 0 and row[0] == tx.id:
            row_idx = i + 1
            old_amount = float(row[4]) if row[4] else 0
            break

    if row_idx is None:
        raise HTTPException(404, "找不到該筆紀錄")

    new_amount = tx.amount if tx.amount is not None else old_amount

    tx_sheet.update(f"B{row_idx}:H{row_idx}", [[
        tx.date or rows[row_idx - 1][1],
        tx.type or rows[row_idx - 1][2],
        tx.category or rows[row_idx - 1][3],
        new_amount,
        tx.note if tx.note is not None else rows[row_idx - 1][5],
        tx.pay_method if tx.pay_method is not None else rows[row_idx - 1][7] if len(rows[row_idx - 1]) > 7 else "",
    ]])
    return {"success": True}


@app.delete("/api/transactions")
def delete_transaction(tx: TransactionDelete):
    tx_sheet, _ = ensure_sheets()
    rows = tx_sheet.get_all_values()

    row_idx = None
    for i, row in enumerate(rows):
        if i > 0 and row[0] == tx.id:
            row_idx = i + 1
            break

    if row_idx is None:
        raise HTTPException(404, "找不到該筆紀錄")

    tx_sheet.delete_rows(row_idx)
    return {"success": True}


@app.get("/api/sync-version")
def get_sync_version():
    """快速回傳資料版號（輕量，不下載所有資料）"""
    tx_sheet, _ = ensure_sheets()
    rows = tx_sheet.get_all_values()
    # 根據資料列數 + 最後一筆 row 內容算 hash
    if len(rows) <= 1:
        return {"success": True, "version": "0", "count": 0}

    data_rows = rows[1:]
    # 用記錄數 + 最後一筆的 ID + 最後修改時間來判斷
    last_id = data_rows[-1][0] if data_rows and data_rows[-1][0] else ""
    last_date = data_rows[-1][1] if data_rows and len(data_rows[-1]) > 1 else ""
    count = len(data_rows)
    # 簡單但足夠的版號
    import hashlib
    raw = f"{count}|{last_id}|{last_date}"
    version = hashlib.md5(raw.encode()).hexdigest()[:12]
    return {"success": True, "version": version, "count": count}


@app.get("/api/budgets")
def get_budgets(month: Optional[str] = None):
    _, bg_sheet = ensure_sheets()
    if not month:
        now = datetime.now()
        month = f"{now.year}-{now.month:02d}"

    rows = bg_sheet.get_all_values()
    if len(rows) <= 1:
        return {"success": True, "data": {}}

    result = {}
    for row in rows[1:]:
        if row[0] and len(row) >= 3 and row[2] == month:
            result[row[0]] = float(row[1]) if row[1] else 0
    return {"success": True, "data": result}


@app.post("/api/budgets")
def save_budgets(bg: BudgetSave):
    _, bg_sheet = ensure_sheets()
    now = datetime.now()
    month = bg.month or f"{now.year}-{now.month:02d}"

    # Clear old data for this month
    rows = bg_sheet.get_all_values()
    delete_rows = []
    for i, row in enumerate(rows):
        if i > 0 and len(row) >= 3 and row[2] == month:
            delete_rows.append(i + 1)
    delete_rows.reverse()
    for r in delete_rows:
        bg_sheet.delete_rows(r)

    # Write new budgets
    if bg.budgets:
        new_rows = [[cat, amt, month] for cat, amt in bg.budgets.items() if amt > 0]
        if new_rows:
            bg_sheet.append_rows(new_rows)

    return {"success": True}


# ====== Settings / Categories ======
SETTINGS_SHEET = "系統設定"


def ensure_settings_sheet():
    sh = get_sheet()
    try:
        sheet = sh.worksheet(SETTINGS_SHEET)
    except Exception:
        sheet = sh.add_worksheet(SETTINGS_SHEET, 100, 2)
        sheet.update("A1:B1", [["key", "value"]])
        sheet.format("A1:B1", {"textFormat": {"bold": True}})
    return sheet


class SettingsData(BaseModel):
    categories: Optional[dict] = None


@app.get("/api/settings")
def get_settings():
    sheet = ensure_settings_sheet()
    rows = sheet.get_all_values()
    result = {}
    for row in rows[1:]:
        if row[0] and len(row) >= 2:
            try:
                result[row[0]] = json.loads(row[1])
            except Exception:
                result[row[0]] = row[1]
    return {"success": True, "data": result}


@app.post("/api/settings")
def save_settings(settings: SettingsData):
    sheet = ensure_settings_sheet()
    data = sheet.get_all_values()

    if settings.categories:
        key = "categories"
        value = json.dumps(settings.categories, ensure_ascii=False)

        row_idx = None
        for i, row in enumerate(data):
            if i > 0 and row[0] == key:
                row_idx = i + 1
                break

        if row_idx:
            sheet.update(f"B{row_idx}", [[value]])
        else:
            sheet.append_row([key, value])

    return {"success": True}


# ====== PDF Export (server-side, no font issues) ======
from fastapi.responses import StreamingResponse
from fpdf import FPDF
import io


@app.get("/api/export/pdf/{month}")
def export_pdf(month: str):
    main_sheet, _ = ensure_sheets()
    rows = main_sheet.get_all_values()
    data_rows = rows[1:] if len(rows) > 1 else []

    filtered = [r for r in data_rows if len(r) > 1 and r[1].startswith(month)]

    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("CJK", "", CJK_FONT, uni=True)
    pdf.set_font("CJK", "", 16)
    pdf.cell(0, 10, f"收支報表 - {month}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("CJK", "", 10)

    income_total = sum(float(r[4]) for r in filtered if len(r) > 4 and r[4] and float(r[4]) >= 0)
    expense_total = sum(-float(r[4]) for r in filtered if len(r) > 4 and r[4] and float(r[4]) < 0)
    balance = income_total - expense_total

    pdf.cell(0, 7, f"收入：+${income_total:,.0f}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"支出：-${expense_total:,.0f}", new_x="LMARGIN", new_y="NEXT")
    bal_str = f"+${balance:,.0f}" if balance >= 0 else f"-${abs(balance):,.0f}"
    pdf.cell(0, 7, f"結餘：{bal_str}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    col_w = [22, 26, 40, 28, 44, 30]
    header_labels = ["日期", "類別", "分類", "金額", "備註", "支付方式"]

    pdf.set_font("CJK", "", 9)
    for i, h in enumerate(header_labels):
        pdf.cell(col_w[i], 7, h, border=1, align="C")
    pdf.ln()

    for r in filtered:
        date = r[1][5:] if len(r) > 1 and len(r[1]) >= 10 else (r[1] if len(r) > 1 else "")
        typ = "收入" if len(r) > 4 and r[4] and float(r[4]) >= 0 else "支出"
        cat = r[3] if len(r) > 3 else ""
        amt_raw = float(r[4]) if len(r) > 4 and r[4] else 0
        amt_str = f"+${amt_raw:,.0f}" if amt_raw >= 0 else f"-${abs(amt_raw):,.0f}"
        note = r[5] if len(r) > 5 else ""
        pay = r[7] if len(r) > 7 else ""
        vals = [date, typ, cat, amt_str, note, pay]
        for i, v in enumerate(vals):
            pdf.cell(col_w[i], 7, v, border=1, align="C" if i in [0, 3] else "L")
        pdf.ln()

        if pdf.get_y() > 270:
            pdf.add_page()
            pdf.set_font("CJK", "", 9)
            for i, h in enumerate(header_labels):
                pdf.cell(col_w[i], 7, h, border=1, align="C")
            pdf.ln()

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{month}.pdf"}
    )
