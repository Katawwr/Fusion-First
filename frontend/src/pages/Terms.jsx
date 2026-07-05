import React from 'react';
import { Navigate } from 'react-router-dom';

// Terms of Service is included in the Privacy page
export default function Terms() {
  return <Navigate to="/privacy" replace />;
}
