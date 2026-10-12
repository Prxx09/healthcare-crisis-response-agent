import { useEffect, useRef } from "react";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";

type Props = {
  message: string | null;
  onDismiss: () => void;
  variant?: "info" | "success" | "error";
  className?: string;
  durationMs?: number;
};

export function NotificationBanner({ message, onDismiss, variant = "info", className = "", durationMs = 6000 }: Props) {
  const dismissRef = useRef(onDismiss);

  useEffect(() => { dismissRef.current = onDismiss; }, [onDismiss]);

  useEffect(() => {
    if (!message || durationMs <= 0) return;
    const timer = window.setTimeout(() => dismissRef.current(), durationMs);
    return () => window.clearTimeout(timer);
  }, [durationMs, message]);

  if (!message) return null;
  const Icon = variant === "error" ? AlertTriangle : variant === "success" ? CheckCircle2 : Info;

  return <div className={`notification-banner ${variant} ${className}`.trim()} role={variant === "error" ? "alert" : "status"} aria-live="polite">
    <span className="notification-content"><Icon size={18} aria-hidden="true" />{message}</span>
    <button type="button" onClick={onDismiss} aria-label="Dismiss notification" title="Dismiss"><X size={18} /></button>
  </div>;
}
