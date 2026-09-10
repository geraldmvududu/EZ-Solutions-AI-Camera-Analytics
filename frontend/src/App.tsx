import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoginPage } from "./pages/Login";
import { DashboardPage } from "./pages/Dashboard";
import { CamerasPage } from "./pages/Cameras";
import { LiveCamerasPage } from "./pages/LiveCameras";
import { EventsPage } from "./pages/Events";
import { AlertsPage } from "./pages/Alerts";
import { RecordingsPage } from "./pages/Recordings";
import { RulesPage } from "./pages/Rules";
import { IncidentsPage } from "./pages/Incidents";
import { SystemHealthPage } from "./pages/SystemHealth";
import { UsersPage } from "./pages/Users";
import { AuditLogsPage } from "./pages/AuditLogs";
import { AnalyticsPage } from "./pages/Analytics";
import { ZonesEditorPage } from "./pages/ZonesEditor";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
        <Route path="/live-cameras" element={<ProtectedRoute><LiveCamerasPage /></ProtectedRoute>} />
        <Route
          path="/cameras"
          element={
            <ProtectedRoute permission="manage_cameras">
              <CamerasPage />
            </ProtectedRoute>
          }
        />
        <Route path="/events" element={<ProtectedRoute><EventsPage /></ProtectedRoute>} />
        <Route path="/alerts" element={<ProtectedRoute><AlertsPage /></ProtectedRoute>} />
        <Route path="/recordings" element={<ProtectedRoute><RecordingsPage /></ProtectedRoute>} />
        <Route
          path="/rules"
          element={
            <ProtectedRoute permission="manage_rules">
              <RulesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/zones"
          element={
            <ProtectedRoute permission="manage_rules">
              <ZonesEditorPage />
            </ProtectedRoute>
          }
        />
        <Route path="/incidents" element={<ProtectedRoute><IncidentsPage /></ProtectedRoute>} />
        <Route
          path="/analytics"
          element={
            <ProtectedRoute permission="view_reports">
              <AnalyticsPage />
            </ProtectedRoute>
          }
        />
        <Route path="/system-health" element={<ProtectedRoute><SystemHealthPage /></ProtectedRoute>} />
        <Route
          path="/users"
          element={
            <ProtectedRoute permission="manage_users">
              <UsersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/audit-logs"
          element={
            <ProtectedRoute permission="manage_system_settings">
              <AuditLogsPage />
            </ProtectedRoute>
          }
        />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  );
}
