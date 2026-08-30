import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Spinner } from './components/Spinner'
import { useAuth } from './context/AuthContext'
import { WsProvider } from './context/WsContext'
import { Dashboard } from './pages/Dashboard'
import { Login } from './pages/Login'
import { NotFound } from './pages/NotFound'
import { Ops } from './pages/Ops'
import { TaskDetail } from './pages/TaskDetail'
import { WorkflowDetail } from './pages/WorkflowDetail'
import { Workflows } from './pages/Workflows'

function ProtectedArea() {
  const { user, isReady } = useAuth()
  if (!isReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-plane">
        <Spinner />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
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
        <Route path="/workflows" element={<Workflows />} />
        <Route path="/workflows/:id" element={<WorkflowDetail />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
