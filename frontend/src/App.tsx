import {
  BrowserRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { SessionProvider, useSession, type Role } from "./auth/session";
import { AppShell } from "./components/AppShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ErrorState } from "./components/ErrorState";
import { ToastProvider } from "./components/Toast";
import { LoginPage } from "./pages/LoginPage";
import { NotReady } from "./pages/NotReady";
import { OverviewPage } from "./pages/OverviewPage";
import { CampaignsPage } from "./pages/CampaignsPage";
import { DeviceLayoutsPage } from "./pages/DeviceLayoutsPage";
import { MaterialsPage } from "./pages/MaterialsPage";
import { LayerPresetsPage } from "./pages/LayerPresetsPage";
import { BaselinesPage } from "./pages/BaselinesPage";
import { UsersPage } from "./pages/UsersPage";
import { ExperimentsPage } from "./pages/ExperimentsPage";
import { ExperimentDetailPage } from "./pages/ExperimentDetailPage";
import { ExperimentBuilderPage } from "./pages/ExperimentBuilderPage";
import { UploadResultPage } from "./pages/UploadResultPage";
import { ResultDetailPage } from "./pages/ResultDetailPage";
import { ResultsPage } from "./pages/ResultsPage";
import { FabricationBatchesPage } from "./pages/FabricationBatchesPage";
import { BatchDetailPage } from "./pages/BatchDetailPage";

function RequireAuth() {
  const { status, error, refresh } = useSession();
  const location = useLocation();
  if (status === "loading") {
    return (
      <div className="app-loading" role="status">
        Loading…
      </div>
    );
  }
  if (status === "unauthenticated") {
    return (
      <Navigate
        to="/login"
        replace
        state={{
          from: {
            pathname: location.pathname,
            search: location.search,
            hash: location.hash,
          },
        }}
      />
    );
  }
  if (status === "error") {
    return (
      <div className="app-loading">
        <ErrorState
          title="Unable to verify your session"
          message={error ?? "The session service did not respond."}
          action={
            <button
              type="button"
              className="button button--secondary"
              onClick={() => void refresh()}
            >
              Retry
            </button>
          }
        />
      </div>
    );
  }
  return <Outlet />;
}

const ROLE_RANK: Record<Role, number> = {
  student: 1,
  instructor: 2,
  administrator: 3,
};

function RequireRole({ minimum }: { minimum: Role }) {
  const { user } = useSession();
  if (!user || ROLE_RANK[user.role] < ROLE_RANK[minimum]) {
    return (
      <ErrorState
        title="Not authorized"
        message="Your account does not have permission to view this page."
      />
    );
  }
  return <Outlet />;
}

export default function App() {
  return (
    <BrowserRouter basename="/app">
      <SessionProvider>
        <ToastProvider>
          <ErrorBoundary>
            <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<RequireAuth />}>
              <Route element={<AppShell />}>
                <Route index element={<OverviewPage />} />
                <Route
                  path="experiments"
                  element={<ExperimentsPage />}
                />
                <Route
                  path="experiments/new"
                  element={<ExperimentBuilderPage />}
                />
                <Route
                  path="experiments/:experimentId"
                  element={<ExperimentDetailPage />}
                />
                <Route
                  path="experiments/:experimentId/upload"
                  element={<UploadResultPage />}
                />
                <Route
                  path="results"
                  element={<ResultsPage />}
                />
                <Route
                  path="results/:resultId"
                  element={<ResultDetailPage />}
                />
                <Route
                  path="experiments/:experimentId/batches/:batchId"
                  element={<BatchDetailPage />}
                />
                <Route
                  path="fabrication-batches"
                  element={<FabricationBatchesPage />}
                />
                <Route
                  path="materials"
                  element={<MaterialsPage />}
                />
                <Route
                  path="layer-presets"
                  element={<LayerPresetsPage />}
                />
                <Route
                  path="baselines"
                  element={<BaselinesPage />}
                />
                <Route
                  path="device-layouts"
                  element={<DeviceLayoutsPage />}
                />
                <Route
                  path="campaigns"
                  element={<CampaignsPage />}
                />
                <Route element={<RequireRole minimum="administrator" />}>
                  <Route path="users" element={<UsersPage />} />
                </Route>
                <Route path="*" element={<NotReady section="This page" />} />
              </Route>
            </Route>
          </Routes>
          </ErrorBoundary>
        </ToastProvider>
      </SessionProvider>
    </BrowserRouter>
  );
}
