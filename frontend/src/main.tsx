import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './index.css';
import './assets.css';
import './rank-visibility.css';
import './polish.css';
import './ui-enhancements';
import './minutes-bar-fix';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);