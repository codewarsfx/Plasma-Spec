import { redirect } from "next/navigation";

/**
 * The legacy /analysis page has been replaced by /studio, which provides
 * the full workstation experience (toolbar, sidebar, contextual right panel,
 * results table) and supersedes everything /analysis used to offer.
 *
 * Keeping the URL alive via a redirect so saved links and browser history
 * keep working, but the user lands on the workstation immediately.
 */
export default function LegacyAnalysisRedirect() {
  redirect("/studio");
}
