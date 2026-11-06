// Compatibility entry point for the maintained Documents browser checks.
process.env.DOCUMENT_TABLE_ORIGIN ||= process.env.DOCUMENT_WIDTHS_ORIGIN || 'http://127.0.0.1:5193'
process.env.DOCUMENT_TABLE_EVIDENCE ||=
  process.env.DOCUMENT_WIDTHS_EVIDENCE || '/tmp/document-width-evidence'
await import('./check-document-navigation.mjs')
