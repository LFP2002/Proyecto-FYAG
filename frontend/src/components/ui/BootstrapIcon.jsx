import React from 'react';

export default function BootstrapIcon({ name, className = '', label }) {
  return <i className={`bi bi-${name}${className ? ` ${className}` : ''}`} aria-hidden={label ? undefined : 'true'} aria-label={label} role={label ? 'img' : undefined} />;
}
