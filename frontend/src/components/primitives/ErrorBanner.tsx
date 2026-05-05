interface ErrorBannerProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

/** Inline error message for failed data fetches. */
export function ErrorBanner({ title = 'Something went wrong', message, onRetry }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-l border border-bad/40 bg-bad/[0.06] px-4 py-3"
    >
      <div className="flex-1">
        <div className="text-[13px] font-bold text-bad">{title}</div>
        <div className="mt-0.5 text-[12px] text-paper-3">{message}</div>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-m border border-bad/40 bg-white px-3 py-1.5 text-[12px] font-semibold text-bad hover:bg-bad/10"
        >
          Try again
        </button>
      )}
    </div>
  );
}
