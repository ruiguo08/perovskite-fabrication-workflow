import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";

interface NotReadyProps {
  section: string;
}

/**
 * Fallback for routes that no longer match any application section. Every
 * former legacy section has a React equivalent since the Phase 4 cutover
 * (docs/react-migration.md), so this only renders for unknown paths.
 */
export function NotReady({ section }: NotReadyProps) {
  return (
    <EmptyState
      title={`${section} is not part of the application`}
      description="The address does not match any application section. Use the link below to return to the overview."
      action={
        <Link className="button button--secondary" to="/">
          Back to overview
        </Link>
      }
    />
  );
}