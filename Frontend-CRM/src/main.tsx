import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { reportWebVitals } from './lib/webVitals'
import { preloadOnlyOfficeApi } from './lib/onlyofficePreload'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

reportWebVitals()

// Warm the OnlyOffice api.js script if we have a cached editor URL from a
// previous session. First-ever load is unaffected; every load after that has
// the editor script already in cache by the time the user opens a document.
preloadOnlyOfficeApi()

