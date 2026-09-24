import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import '@uswds/uswds/css/uswds.min.css';
import './styles.css';
import App from './App';
import { AuthProvider } from './auth/AuthProvider';
import { runtimeConfig } from './runtimeConfig';

document.title = runtimeConfig.appTitle;

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider><App /></AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
