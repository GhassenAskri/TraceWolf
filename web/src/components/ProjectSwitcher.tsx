import { Add, ChevronDown } from '@carbon/icons-react'
import { Popover, PopoverContent, Search } from '@carbon/react'
import { useRef, useState, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router'
import type { Project } from '../api/types'
import { useCurrentProject } from '../hooks/useCurrentProject'
import { useProjects } from '../hooks/useProjects'

const counts = (p: Project) =>
  `${p.slug} · ${p.volume_count} conversation${p.volume_count === 1 ? '' : 's'} · ${p.call_count} call${p.call_count === 1 ? '' : 's'}`

/**
 * The project switcher at the top right of the header: a button with the current project that
 * opens a panel with a search box, the current project, the others and "New project".
 */
export default function ProjectSwitcher() {
  const { status, projects, error, openNewProject } = useProjects()
  const current = useCurrentProject()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const trigger = useRef<HTMLButtonElement>(null)

  const close = () => {
    setOpen(false)
    setQuery('')
  }
  const choose = (name: string) => {
    close()
    navigate(`/projects/${encodeURIComponent(name)}`)
  }
  // Captured, so Escape closes the panel even from the search box (which would clear itself first).
  const onKeyDownCapture = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      close()
      trigger.current?.focus()
    }
  }

  const needle = query.trim().toLowerCase()
  const matches = (p: Project) => p.name.toLowerCase().includes(needle) || p.slug.includes(needle)
  const matching = projects.filter(matches)
  const currentProject = projects.find((p) => p.slug === current)
  // The URL can name a project that does not exist yet: it is then shown by its slug.
  const currentMatches = current !== null && (currentProject ? matches(currentProject) : current.includes(needle))
  const others = matching.filter((p) => p.slug !== current)
  const label =
    currentProject?.name ??
    current ??
    (status === 'loading' ? 'Loading…' : projects.length === 0 ? 'No projects' : 'Select a project')

  return (
    <Popover open={open} align="bottom-end" autoAlign dropShadow caret={false} onRequestClose={close}>
      <button
        ref={trigger}
        type="button"
        className="project-switcher-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        title={current ? `Project: ${label}` : 'Projects'}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="project-switcher-name">{label}</span>
        <ChevronDown size={16} />
      </button>
      <PopoverContent className="project-switcher-panel" onKeyDownCapture={onKeyDownCapture}>
        {open && (
          <>
            <Search
              size="sm"
              autoFocus
              labelText="Search projects"
              placeholder="Search projects"
              closeButtonLabelText="Clear search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            {status === 'error' && <p className="project-switcher-note error">{`Could not load projects: ${error}`}</p>}

            {current !== null && currentMatches && (
              <>
                <div className="project-switcher-label">Current project</div>
                <button
                  type="button"
                  className="project-switcher-item"
                  aria-current="true"
                  onClick={() => choose(current)}
                >
                  <span className="project-switcher-item-name">{currentProject?.name ?? current}</span>
                  <span className="project-switcher-item-meta">
                    {currentProject ? counts(currentProject) : 'Does not exist yet'}
                  </span>
                </button>
              </>
            )}

            {others.length > 0 && (
              <>
                <div className="project-switcher-label">{current !== null ? 'Other projects' : 'Projects'}</div>
                <div className="project-switcher-list">
                  {others.map((project) => (
                    <button
                      key={project.slug}
                      type="button"
                      className="project-switcher-item"
                      onClick={() => choose(project.slug)}
                    >
                      <span className="project-switcher-item-name">{project.name}</span>
                      <span className="project-switcher-item-meta">{counts(project)}</span>
                    </button>
                  ))}
                </div>
              </>
            )}
            {status === 'ready' && !currentMatches && matching.length === 0 && (
              <p className="project-switcher-note">
                {projects.length === 0 ? 'No projects yet.' : `No project matches “${query.trim()}”.`}
              </p>
            )}

            <button
              type="button"
              className="project-switcher-new"
              onClick={() => {
                close()
                openNewProject()
              }}
            >
              <Add size={16} />
              New project
            </button>
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}
