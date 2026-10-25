import {
  Content,
  Header,
  HeaderGlobalBar,
  HeaderMenuButton,
  HeaderName,
  SkipToContent,
} from '@carbon/react'
import { useState } from 'react'
import { Link, Outlet } from 'react-router'
import { useCurrentProject } from '../hooks/useCurrentProject'
import ProjectsProvider from './ProjectsProvider'
import ProjectSwitcher from './ProjectSwitcher'
import Sidebar from './Sidebar'

export default function Layout() {
  // On narrow screens the side navigation is hidden behind the header's menu button; from the
  // large breakpoint up Carbon always shows it and ignores this state.
  const [navOpen, setNavOpen] = useState(false)
  // Inside a project the page is a conversations column beside the content: it uses the full width.
  const inProject = useCurrentProject() !== null

  return (
    <ProjectsProvider>
      <Header aria-label="AIControl">
        <SkipToContent href="#main-content" />
        <HeaderMenuButton
          aria-label={navOpen ? 'Close navigation' : 'Open navigation'}
          isActive={navOpen}
          onClick={() => setNavOpen((open) => !open)}
        />
        <HeaderName as={Link} to="/" prefix="">
          AIControl
        </HeaderName>
        <HeaderGlobalBar>
          <ProjectSwitcher />
        </HeaderGlobalBar>
      </Header>
      <Sidebar expanded={navOpen} onClose={() => setNavOpen(false)} />
      <Content id="main-content">
        <div className={inProject ? 'page page--wide' : 'page'}>
          <Outlet />
        </div>
      </Content>
    </ProjectsProvider>
  )
}
