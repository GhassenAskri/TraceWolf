import { AiObservability } from '@carbon/icons-react'
import { SideNav, SideNavItems, SideNavLink } from '@carbon/react'
import { Link } from 'react-router'
import { useCurrentProject } from '../hooks/useCurrentProject'
import { useMediaQuery } from '../hooks/useMediaQuery'

interface Props {
  /** Narrow screens only: whether the menu button has opened the navigation. */
  expanded: boolean
  onClose: () => void
}

export default function Sidebar({ expanded, onClose }: Props) {
  const project = useCurrentProject()
  // From Carbon's large breakpoint (66rem) the navigation is always shown, and Carbon only offsets
  // the page content when the navigation is marked expanded; below it the menu button opens it.
  const wide = useMediaQuery('(min-width: 66rem)')
  const visible = wide || expanded

  return (
    <SideNav aria-label="Navigation" expanded={visible} onOverlayClick={onClose} onSideNavBlur={onClose}>
      <SideNavItems>
        {/* The observability of the selected project; its conversations are listed in the page. */}
        <SideNavLink
          as={Link}
          to={project !== null ? `/projects/${encodeURIComponent(project)}` : '/'}
          renderIcon={AiObservability}
          isActive={project !== null}
          onClick={onClose}
        >
          Observe
        </SideNavLink>
      </SideNavItems>
    </SideNav>
  )
}
