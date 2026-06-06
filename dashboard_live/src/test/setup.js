// Vitest global setup: register @testing-library/jest-dom matchers
// (toBeInTheDocument, toHaveTextContent, …) and auto-clean the DOM
// between tests so component renders don't bleed into each other.
import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => cleanup())
