import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { useAuth } from './context/AuthContext'
import { WsProvider } from './context/WsContext'
import { Dashboard } from './pages/Dashboard'
import { Login } from './pages/Login'
import { NotFound } from './pages/NotFound'
import { Ops } from './pages/Ops'
import { TaskDetail } from './pages/TaskDetail'

function ProtectedArea() {
  const { apiKey } = useAuth()
  if (!apiKey) return <Navigate to="/login" replace />
  return (
    <WsProvider>
      <Layout />
    </WsProvider>
  )
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedArea />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/tasks/:id" element={<TaskDetail />} />
        <Route path="/ops" element={<Ops />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
