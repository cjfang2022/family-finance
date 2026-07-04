/**
 * 家庭收支小管家 - Google Sheets 後端 API
 * 部署方式：部署 → 新增部署作業 → 網頁應用程式
 * 執行身份：我 (使用者)
 * 存取權限：所有人
 */

// ====== 設定 ======
const SHEET_NAMES = {
  transactions: '收支紀錄',
  budgets: '預算設定'
};

// ====== 初始化試算表結構 ======
function setupSheets_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  
  // 收支紀錄工作表
  let txSheet = ss.getSheetByName(SHEET_NAMES.transactions);
  if (!txSheet) {
    txSheet = ss.insertSheet(SHEET_NAMES.transactions);
    txSheet.appendRow(['ID', '日期', '類別', '分類', '金額', '備註', '建立時間']);
    txSheet.getRange('1:1').setFontWeight('bold');
    txSheet.setFrozenRows(1);
  }
  
  // 預算設定工作表
  let bgSheet = ss.getSheetByName(SHEET_NAMES.budgets);
  if (!bgSheet) {
    bgSheet = ss.insertSheet(SHEET_NAMES.budgets);
    bgSheet.appendRow(['分類', '預算金額', '月份']);
    bgSheet.getRange('1:1').setFontWeight('bold');
    bgSheet.setFrozenRows(1);
  }
  
  return { txSheet, bgSheet };
}

// ====== CORS 支援 ======
function doGet(e) {
  return handleCORS_(() => {
    const sheets = setupSheets_();
    const action = e?.parameter?.action || 'all';
    
    if (action === 'transactions') {
      return { success: true, data: getTransactions_(sheets.txSheet) };
    }
    if (action === 'budgets') {
      const month = e?.parameter?.month || getCurrentMonth_();
      return { success: true, data: getBudgets_(sheets.bgSheet, month) };
    }
    
    // 'all' 或無參數
    return {
      success: true,
      data: {
        transactions: getTransactions_(sheets.txSheet),
        budgets: getBudgets_(sheets.bgSheet, getCurrentMonth_())
      }
    };
  });
}

function doPost(e) {
  return handleCORS_(() => {
    const sheets = setupSheets_();
    const body = JSON.parse(e.postData.contents);
    const action = body.action;
    
    if (action === 'add_tx') {
      return addTransaction_(sheets.txSheet, body);
    }
    if (action === 'update_tx') {
      return updateTransaction_(sheets.txSheet, body);
    }
    if (action === 'delete_tx') {
      return deleteTransaction_(sheets.txSheet, body);
    }
    if (action === 'save_budgets') {
      return saveBudgets_(sheets.bgSheet, body);
    }
    
    throw new Error('未知的 action：' + action);
  });
}

function doOptions(e) {
  return handleCORS_(() => ({ success: true }));
}

// ====== CORS 處理 ======
function handleCORS_(fn) {
  try {
    const result = fn();
    return ContentService
      .createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON)
      .setHeaders({
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
      });
  } catch(e) {
    return ContentService
      .createTextOutput(JSON.stringify({ success: false, error: e.message }))
      .setMimeType(ContentService.MimeType.JSON)
      .setHeaders({
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
      });
  }
}

// ====== 讀取交易紀錄 ======
function getTransactions_(sheet) {
  const data = sheet.getDataRange().getValues();
  if (data.length <= 1) return [];
  
  return data.slice(1).filter(row => row[0]).map(row => ({
    id: row[0],
    date: formatDate_(row[1]),
    type: row[2],
    category: row[3],
    amount: Number(row[4]),
    note: row[5] || '',
    createdAt: row[6] || ''
  }));
}

// ====== 新增交易 ======
function addTransaction_(sheet, body) {
  const id = body.id || (new Date().getTime() + '_' + Math.random().toString(36).slice(2, 6));
  const now = new Date().toISOString();
  const amount = body.type === 'expense' ? -Math.abs(body.amount) : Math.abs(body.amount);
  
  sheet.insertRow(2);
  sheet.getRange(2, 1, 1, 7).setValues([[
    id,
    body.date,
    body.type,
    body.category,
    amount,
    body.note || '',
    now
  ]]);
  
  return { success: true, id };
}

// ====== 更新交易 ======
function updateTransaction_(sheet, body) {
  const data = sheet.getDataRange().getValues();
  const rowIndex = data.findIndex((row, i) => i > 0 && row[0] === body.id);
  if (rowIndex === -1) throw new Error('找不到該筆紀錄');
  
  const row = rowIndex + 1;
  const sign = Number(data[rowIndex][4]) >= 0 ? 1 : -1;
  
  sheet.getRange(row, 2, 1, 5).setValues([[
    body.date || data[rowIndex][1],
    body.type || data[rowIndex][2],
    body.category || data[rowIndex][3],
    body.amount ? Math.abs(body.amount) * sign : data[rowIndex][4],
    body.note ?? data[rowIndex][5]
  ]]);
  
  return { success: true };
}

// ====== 刪除交易 ======
function deleteTransaction_(sheet, body) {
  const data = sheet.getDataRange().getValues();
  const rowIndex = data.findIndex((row, i) => i > 0 && row[0] === body.id);
  if (rowIndex === -1) throw new Error('找不到該筆紀錄');
  
  sheet.deleteRow(rowIndex + 1);
  return { success: true };
}

// ====== 預算 ======
function getBudgets_(sheet, month) {
  const data = sheet.getDataRange().getValues();
  if (data.length <= 1) return {};
  
  const result = {};
  data.slice(1).filter(row => row[0] && row[2] === month).forEach(row => {
    result[row[0]] = Number(row[1]);
  });
  return result;
}

function saveBudgets_(sheet, body) {
  const month = body.month || getCurrentMonth_();
  const budgets = body.budgets || {};
  
  // 清除該月的舊資料
  const data = sheet.getDataRange().getValues();
  const deleteRows = [];
  data.forEach((row, i) => {
    if (i > 0 && row[2] === month) deleteRows.push(i + 1);
  });
  deleteRows.reverse().forEach(r => sheet.deleteRow(r));
  
  // 寫入新預算
  if (Object.keys(budgets).length > 0) {
    const rows = Object.entries(budgets).map(([cat, amount]) => [cat, amount, month]);
    sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, 3).setValues(rows);
  }
  
  return { success: true };
}

// ====== 工具函式 ======
function formatDate_(v) {
  if (!v) return '';
  if (typeof v === 'string') return v;
  if (v instanceof Date) {
    const y = v.getFullYear();
    const m = String(v.getMonth() + 1).padStart(2, '0');
    const d = String(v.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }
  return String(v);
}

function getCurrentMonth_() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}
