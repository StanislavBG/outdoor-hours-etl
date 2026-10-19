import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { initTelemetry } from 'host-kit';
import pkg from '../package.json';
import { OutdoorHoursPage } from './OutdoorHoursPage.js';
import './index.css';

initTelemetry({ app: 'outdoor-hours', version: pkg.version });

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {/* basename mirrors vite.config.ts `base`. Lets react-router useSearchParams work
        when served at /projects/outdoor-hours/. */}
    <BrowserRouter basename="/projects/outdoor-hours">
      <OutdoorHoursPage />
    </BrowserRouter>
  </React.StrictMode>,
);
