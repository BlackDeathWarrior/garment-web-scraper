import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Home from './pages/Home'
import Login from './pages/Login'
import Register from './pages/Register'
import Contact from './pages/Contact'
import RequestStatus from './pages/RequestStatus'
import SupportWidget from './components/SupportWidget'

// Simple protected route helper
function ProtectedRoute({ children }) {
  const isAuthenticated = localStorage.getItem('scraper_auth_token')
  return isAuthenticated ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/requests" element={<RequestStatus />} />
        <Route path="/requests/:reference" element={<RequestStatus />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Home />
            </ProtectedRoute>
          }
        />
        {/* Fallback to home */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <SupportWidget />
    </Router>
  )
}
