import React from 'react';
import ReactDOM from 'react-dom/client';
import 'bootstrap/dist/css/bootstrap.min.css';
import App from './app.jsx';
import { AppProvider } from './context/AppContext.jsx';
import { AuthProvider } from './auth/AuthContext.jsx';

import './styles/variables.css';
import './styles/base.css';
import './styles/layout.css';
import './styles/components/ui.css';
import './styles/components/login.css';
import './styles/components/shell.css';
import './styles/components/tecnico.css';
import './styles/pages/dashboard.css';
import './styles/pages/presupuestos.css';
import './styles/pages/clientes.css';
import './styles/pages/obras.css';
import './styles/pages/cobranzas.css';
import './styles/pages/alertas.css';
import './styles/pages/reportes.css';
import './styles/pages/usuarios.css';
import './styles/pages/comercial.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthProvider>
      <AppProvider>
        <App />
      </AppProvider>
    </AuthProvider>
  </React.StrictMode>
);
