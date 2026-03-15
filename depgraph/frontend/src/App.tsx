import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import { useAuth, AuthProvider } from "./context/AuthContext";
import { AppProvider } from "./context/AppContext";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import MainApp from "./pages/MainApp";
import AnalyzingPage from "./pages/AnalyzingPage";
import NotFound from "./pages/NotFound";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--void-hex)' }}>
        <span className="font-mono text-xs" style={{ color: 'var(--text-4-hex)' }}>Loading...</span>
      </div>
    );
  }
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

const App = () => (
  <AuthProvider>
    <AppProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/app" element={<ProtectedRoute><MainApp /></ProtectedRoute>} />
          <Route path="/analyzing" element={<ProtectedRoute><AnalyzingPage /></ProtectedRoute>} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </AppProvider>
  </AuthProvider>
);

export default App;
