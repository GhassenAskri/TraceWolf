import { Modal, TextInput } from '@carbon/react'
import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import type { Project } from '../api/types'
import { useProjects } from '../hooks/useProjects'
import { projectNameProblem } from '../lib/projectName'
import { nextFreeSlug, slugify } from '../lib/slug'
import SdkSnippet from './SdkSnippet'

interface Props {
  onClose: () => void
  /** Creates the project; rejects with an `ApiError` (409 name taken, 422 not valid). */
  create: (name: string) => Promise<Project>
  onCreated: (project: Project) => void
}

function describe(error: unknown, name: string): string {
  if (error instanceof ApiError && error.status === 409) {
    return `A project named “${name}” already exists.`
  }
  return error instanceof Error ? error.message : String(error)
}

/** Asks for a project name. Mount it while it is open: closing it throws its state away. */
export default function NewProjectModal({ onClose, create, onCreated }: Props) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const { projects } = useProjects()

  // The slug this name will get: its generated form, numbered if it is taken (the API decides).
  const trimmed = name.trim()
  const slug = trimmed === '' ? null : nextFreeSlug(slugify(trimmed), new Set(projects.map((p) => p.slug)))

  const submit = async () => {
    const trimmed = name.trim()
    const problem = projectNameProblem(trimmed)
    if (problem) return setError(problem)
    setBusy(true)
    try {
      onCreated(await create(trimmed))
    } catch (e) {
      setError(describe(e, trimmed))
      setBusy(false)
    }
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    void submit()
  }

  return (
    <Modal
      open
      size="md"
      modalHeading="New project"
      primaryButtonText={busy ? 'Creating…' : 'Create'}
      secondaryButtonText="Cancel"
      primaryButtonDisabled={busy}
      onRequestClose={onClose}
      onRequestSubmit={() => void submit()}
    >
      <form onSubmit={onSubmit}>
        <TextInput
          id="new-project-name"
          data-modal-primary-focus
          labelText="Project name"
          helperText="A label for people. Its slug is generated from it."
          value={name}
          invalid={error !== null}
          invalidText={error ?? ''}
          onChange={(event) => {
            setName(event.target.value)
            setError(null)
          }}
        />
      </form>
      {slug !== null && (
        <section className="new-project-code" aria-live="polite">
          <p className="slug-preview">
            <span className="slug-preview-label">Slug</span>
            <code>{slug}</code>
          </p>
          <p className="muted">Your code passes the slug to the SDK. Copy this to send calls to the project:</p>
          <SdkSnippet slug={slug} />
        </section>
      )}
    </Modal>
  )
}
