import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '@/components/shell/AppShell';
import type { ViewportTier } from '@/components/shell/SidebarStateProvider';
import { WorklistPage } from '@/pages/WorklistPage';
import { DatasetsPage } from '@/pages/DatasetsPage';
import { ReviewPage } from '@/pages/ReviewPage';
import { AnnotationEditorPage } from '@/pages/AnnotationEditorPage';
import { ClinicianReviewPage } from '@/pages/ClinicianReviewPage';
import { ModelsPage } from '@/pages/ModelsPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { AdminPage } from '@/pages/AdminPage';
import { TodayPage } from '@/pages/TodayPage';
import { ReportPage } from '@/pages/ReportPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { NavigationGuardProvider } from '@/components/shell/NavigationGuard';
import { WorkspaceProvider } from '@/components/shell/workspace';
import { LocalTimingObserver } from '@/components/shell/LocalTimingObserver';
import { AuthGate } from '@/components/shell/AuthGate';

interface AppRoutesProps {
  /** Test-only viewport override — see AppShell. */
  forceTier?: ViewportTier;
}

/**
 * Route registration for the clinician workstation.
 *
 * The primary routes cover worklist, review, datasets, audit, settings, and
 * the explicit annotation and clinician-review flows.
 *
 *   /worklist   clinician worklist
 *   /datasets   dataset workspace
 *   /review     case-review surface
 *   /models     provider readiness / audit
 *   /settings   preferences
 *
 * Any unknown path renders the 404 page so the shell never lands in an empty
 * state.
 */
export function AppRoutes({ forceTier }: AppRoutesProps = {}) {
  return (
    <AuthGate><NavigationGuardProvider><WorkspaceProvider>
      <LocalTimingObserver />
      <Routes>
        <Route element={<AppShell forceTier={forceTier} />}>
          <Route index element={<Navigate to="/today" replace />} />
          <Route path="/today" element={<TodayPage />} />
          <Route path="/worklist" element={<WorklistPage />} />
          <Route path="/datasets" element={<DatasetsPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/review/:imageId" element={<ReviewPage />} />
          <Route path="/edit/:imageId" element={<AnnotationEditorPage />} />
          <Route path="/clinician-review/:imageId" element={<ClinicianReviewPage />} />
          <Route path="/report/:imageId" element={<ReportPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </WorkspaceProvider></NavigationGuardProvider></AuthGate>
  );
}
