import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Home from './pages/Home'
import Login from './pages/Login'
import Register from './pages/Register'
import Cart from './pages/Cart'
import Checkout from './pages/Checkout'
import Orders from './pages/Orders'
import OrderDetail from './pages/OrderDetail'
import Contact from './pages/Contact'
import RequestStatus from './pages/RequestStatus'
import Admin from './pages/Admin'
import SupportWidget from './components/SupportWidget'

/** Anyone can browse and fill a cart. Checkout, orders and the admin's page ask for a sign-in themselves. */
export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/cart" element={<Cart />} />
        <Route path="/checkout" element={<Checkout />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/orders/:id" element={<OrderDetail />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/requests" element={<RequestStatus />} />
        <Route path="/requests/:reference" element={<RequestStatus />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <SupportWidget />
    </Router>
  )
}
