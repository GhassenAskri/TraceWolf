import { Button } from '@carbon/react'
import { Link } from 'react-router'
import { useTitle } from '../hooks/useTitle'

export default function NotFound() {
  useTitle('Not found · AIControl')

  return (
    <>
      <h1 className="page-title">Page not found</h1>
      <Button as={Link} to="/" kind="tertiary">
        Back to the start
      </Button>
    </>
  )
}
