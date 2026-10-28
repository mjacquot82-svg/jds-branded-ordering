import { reportProblemHref } from "../config/reportProblem.js";

export default function ReportProblemLink({ context = "", className = "report-problem-link" }) {
  const href = reportProblemHref(undefined, context);
  if (!href) return null;
  const external = href.startsWith("https:");
  return <a className={className} href={href} {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}>Report a problem</a>;
}
