"""
家庭收支小管家 - Google Sheets API Backend
部署於 Railway，透過 Service Account 讀寫 Google Sheets
"""

import os
import json
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import gspread

# ====== 設定 ======
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
SHEET_KEY = os.environ.get("SHEET_KEY", "10257dP7ZcVqT5gIp8OPf-t78rJK8XyouXpxzjZY7AHQ")
CRED_PATH = os.environ.get("CRED_PATH", "/etc/secrets/google_creds.json")

app = FastAPI(title="家庭收支小管家 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    except Exception:
        tx_sheet = sh.add_worksheet("收支紀錄", 1000, 7)
        tx_sheet.update("A1:G1", [["ID", "日期", "類別", "分類", "金額", "備註", "建立時間"]])
        tx_sheet.format("A1:G1", {"textFormat": {"bold": True}})

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


class TransactionUpdate(BaseModel):
    id: str
    date: Optional[str] = None
    type: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    note: Optional[str] = None


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
    for row in rows[1:]:
        if not row[0]:
            continue
        result.append({
            "id": row[0],
            "date": row[1],
            "type": row[2],
            "category": row[3],
            "amount": float(row[4]) if row[4] else 0,
            "note": row[5] if len(row) > 5 else "",
            "createdAt": row[6] if len(row) > 6 else "",
        })
    return {"success": True, "data": result}


@app.post("/api/transactions")
def add_transaction(tx: TransactionIn):
    tx_sheet, _ = ensure_sheets()
    tx_id = tx.id or str(int(datetime.now().timestamp() * 1000)) + "_" + os.urandom(3).hex()
    now = datetime.now().isoformat()
    amount = -abs(tx.amount) if tx.type == "expense" else abs(tx.amount)

    # Insert at row 2 (below header)
    tx_sheet.insert_row([tx_id, tx.date, tx.type, tx.category, amount, tx.note, now], 2)
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

    sign = 1 if old_amount >= 0 else -1
    new_amount = (abs(tx.amount) * sign) if tx.amount is not None else old_amount

    tx_sheet.update(f"B{row_idx}:F{row_idx}", [[
        tx.date or rows[row_idx - 1][1],
        tx.type or rows[row_idx - 1][2],
        tx.category or rows[row_idx - 1][3],
        new_amount,
        tx.note if tx.note is not None else rows[row_idx - 1][5],
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
