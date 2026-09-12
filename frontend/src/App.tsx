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
import { FaceDashboardPage } from "./pages/faces/FaceDashboard";
import { EnrollPersonPage } from "./pages/faces/EnrollPerson";
import { EnrolledPeoplePage } from "./pages/faces/EnrolledPeople";
import { RecognitionEventsPage } from "./pages/faces/RecognitionEvents";
import { VideoIntelligenceDashboardPage } from "./pages/VideoIntelligenceDashboard";
import { VideoIntelligenceSettingsPage } from "./pages/VideoIntelligenceSettings";

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
        <Route path="/video-intelligence" element={<ProtectedRoute><VideoIntelligenceDashboardPage /></ProtectedRoute>} />
        <Route
          path="/video-intelligence/settings"
          element={
            <ProtectedRoute permission="manage_rules">
              <VideoIntelligenceSettingsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/faces"
          element={
            <ProtectedRoute permission="view_biometric_events">
              <FaceDashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/faces/enrolled"
          element={
            <ProtectedRoute permission="view_biometric_events">
              <EnrolledPeoplePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/faces/enroll"
          element={
            <ProtectedRoute permission="manage_biometrics">
              <EnrollPersonPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/faces/events"
          element={
            <ProtectedRoute permission="view_biometric_events">
              <RecognitionEventsPage />
            </ProtectedRoute>
          }
        />
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
