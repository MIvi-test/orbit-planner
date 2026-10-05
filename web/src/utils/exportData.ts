/** Выгрузка таблицы в CSV, JSON и XLSX. Значения — уже готовые строки/числа в порядке колонок. */
export interface ExportColumn<T> {
  header: string
  value: (row: T) => string | number | boolean | null
}

export type ExportFormat = 'csv' | 'json' | 'xlsx'

function save(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

const stamp = () => new Date().toISOString().slice(0, 10)

export async function exportRows<T>(rows: T[], columns: ExportColumn<T>[], format: ExportFormat, baseName: string) {
  const name = `${baseName}-${stamp()}.${format}`
  if (format === 'json') {
    const data = rows.map((row) => Object.fromEntries(columns.map((c) => [c.header, c.value(row)])))
    save(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }), name)
    return
  }
  if (format === 'csv') {
    // BOM и «;», чтобы русский Excel открыл файл сразу и в правильной кодировке.
    const esc = (v: string | number | boolean | null) => {
      const t = v === null ? '' : String(v)
      return /[";\n\r]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t
    }
    const lines = [columns.map((c) => esc(c.header)).join(';'), ...rows.map((r) => columns.map((c) => esc(c.value(r))).join(';'))]
    save(new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }), name)
    return
  }
  // XLSX подгружается только при выгрузке: библиотека не нужна на остальных экранах.
  const { default: writeExcelFile } = await import('write-excel-file/browser')
  const sheet = [
    columns.map((c) => ({ value: c.header, fontWeight: 'bold' as const })),
    ...rows.map((r) =>
      columns.map((c) => {
        const v = c.value(r)
        return v === null ? null : typeof v === 'number' || typeof v === 'boolean' ? v : String(v)
      }),
    ),
  ]
  await writeExcelFile(sheet as never).toFile(name)
}
