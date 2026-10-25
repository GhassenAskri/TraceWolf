import { Route, Routes } from 'react-router'
import Layout from './components/Layout'
import Landing from './pages/Landing'
import NotFound from './pages/NotFound'
import ObservePage from './pages/ObservePage'
import ProjectPage from './pages/ProjectPage'
import VolumePage from './pages/VolumePage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="projects/:project" element={<ObservePage />}>
          <Route index element={<ProjectPage />} />
          {/* A wildcard so conversation names containing "/" work, encoded or not. */}
          <Route path="volumes/*" element={<VolumePage />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
