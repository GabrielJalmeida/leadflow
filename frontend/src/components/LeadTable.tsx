import { useState } from 'react'
import {
  ArrowSortDownRegular,
  ArrowSortUpRegular,
  OpenRegular,
} from '@fluentui/react-icons'
import {
  createColumnHelper,
  createSortedRowModel,
  rowSortingFeature,
  sortFns,
  tableFeatures,
  useTable,
  type SortingState,
} from '@tanstack/react-table'
import type { LeadCard } from '../lib/types'
import { opportunityLabel, readinessLabel } from '../lib/ptBR'

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns,
})

const column = createColumnHelper<typeof features, LeadCard>()

const columns = column.columns([
  column.accessor((lead) => lead.opportunity?.score ?? 0, {
    id: 'fit',
    header: 'Potencial',
    cell: (info) => <span className="fit-value">{info.getValue()}</span>,
  }),
  column.accessor('name', {
    header: 'Empresa',
    cell: (info) => (
      <div className="company-cell">
        <strong>{info.getValue()}</strong>
        <span>{[info.row.original.location?.city, info.row.original.location?.state].filter(Boolean).join(' · ')}</span>
      </div>
    ),
  }),
  column.accessor((lead) => lead.opportunity?.type ?? 'review_needed', {
    id: 'opportunity',
    header: 'Oportunidade',
    cell: (info) => <span>{opportunityLabel(info.getValue()).toUpperCase()}</span>,
  }),
  column.accessor((lead) => readinessLabel(lead.opportunity?.actionable), {
    id: 'readiness',
    header: 'Estado',
    cell: (info) => {
      const ready = info.getValue() === 'PRONTO'
      return <span className={`state-label state-label--${ready ? 'ready' : 'verify'}`}>{info.getValue()}</span>
    },
  }),
  column.accessor((lead) => lead.contact?.phone ?? '', {
    id: 'phone',
    header: 'Celular',
    cell: (info) => info.getValue() || <span className="muted">—</span>,
  }),
  column.accessor((lead) => lead.website?.status ?? 'unknown', {
    id: 'website',
    header: 'Site',
    cell: (info) => {
      const lead = info.row.original
      return lead.website?.url ? (
        <span className="website-cell">{lead.website.url.replace(/^https?:\/\//, '').replace(/\/$/, '')}</span>
      ) : (
        <span className="muted">{info.getValue() === 'not_found' ? 'Não encontrado' : '—'}</span>
      )
    },
  }),
  column.display({
    id: 'open',
    header: '',
    enableSorting: false,
    cell: () => <OpenRegular aria-hidden="true" className="row-open-icon" />,
  }),
])

type Props = {
  leads: LeadCard[]
  selected: LeadCard | null
  onSelect: (lead: LeadCard) => void
}

export function LeadTable({ leads, selected, onSelect }: Props) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'fit', desc: true }])

  const table = useTable({
    key: 'lead-opportunity-table',
    features,
    data: leads,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
  })

  return (
    <div className="lead-table-wrap">
      <table className="lead-table">
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => (
                <th key={header.id}>
                  {header.isPlaceholder ? null : header.column.getCanSort() ? (
                    <button className="sort-button" onClick={header.column.getToggleSortingHandler()}>
                      <table.FlexRender header={header} />
                      {header.column.getIsSorted() === 'asc' ? <ArrowSortUpRegular /> : header.column.getIsSorted() === 'desc' ? <ArrowSortDownRegular /> : null}
                    </button>
                  ) : (
                    <table.FlexRender header={header} />
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => {
            const active = selected === row.original
            return (
              <tr
                key={row.id}
                className={active ? 'is-selected' : ''}
                tabIndex={0}
                aria-selected={active}
                onClick={() => onSelect(row.original)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onSelect(row.original)
                  }
                }}
              >
                {row.getAllCells().map((cell) => (
                  <td key={cell.id}><table.FlexRender cell={cell} /></td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
