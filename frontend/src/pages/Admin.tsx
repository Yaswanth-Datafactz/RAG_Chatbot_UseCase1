import { DocumentsTable } from '../components/admin/DocumentsTable'
import { ReindexPanel } from '../components/admin/ReindexPanel'

export function AdminPage() {
  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-6">
      <ReindexPanel />
      <DocumentsTable />
    </div>
  )
}
