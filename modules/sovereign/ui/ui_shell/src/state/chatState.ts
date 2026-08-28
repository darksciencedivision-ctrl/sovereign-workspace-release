import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { sovereignClient } from "../services/sovereignClient";
import {
  isActiveJobStatus,
  type ChatMessage,
  type ChatSession,
  type JobSnapshot,
  type RouteOverride,
} from "../types/chat";

const JOB_POLL_INTERVAL_MS = 1_500;

function sortSessions(sessions: ChatSession[]): ChatSession[] {
  return [...sessions].sort((a, b) =>
    b.updated_at.localeCompare(a.updated_at)
  );
}

function upsertSession(
  sessions: ChatSession[],
  session: ChatSession
): ChatSession[] {
  return sortSessions([
    session,
    ...sessions.filter((item) => item.session_id !== session.session_id),
  ]);
}

function acceptedMessage(
  messages: ChatMessage[],
  message: ChatMessage
): ChatMessage[] {
  if (messages.some((item) => item.id === message.id)) return messages;
  return [...messages, message];
}

export function useChatState() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Record<string, JobSnapshot>>({});
  const [routeOverride, setRouteOverride] =
    useState<RouteOverride>("AUTO");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const mounted = useRef(true);
  const loadGeneration = useRef(0);

  const active = useMemo(
    () =>
      activeId
        ? sessions.find((session) => session.session_id === activeId) ?? null
        : null,
    [activeId, sessions]
  );

  const activeJob = active
    ? jobs[active.session_id] ??
      active.active_job ??
      active.last_job ??
      null
    : null;

  const adoptJob = useCallback((sessionId: string, job: JobSnapshot) => {
    setJobs((previous) => ({ ...previous, [sessionId]: job }));
  }, []);

  const recoverSessionJob = useCallback(
    async (session: ChatSession) => {
      const embedded = session.active_job;
      if (embedded) {
        adoptJob(session.session_id, embedded);
        return;
      }
      if (!session.active_job_id) return;
      const result = await sovereignClient.getJob(session.active_job_id);
      if (mounted.current && result.ok && result.job) {
        adoptJob(session.session_id, result.job);
      }
    },
    [adoptJob]
  );

  const refreshSession = useCallback(
    async (sessionId: string, reportFailure = true): Promise<ChatSession | null> => {
      const result = await sovereignClient.loadSession(sessionId);
      if (!mounted.current) return null;
      if (!result.ok || !result.session) {
        if (reportFailure) {
          setError(result.error ?? "Unable to load the server session.");
        }
        return null;
      }
      setSessions((previous) => upsertSession(previous, result.session!));
      void recoverSessionJob(result.session);
      return result.session;
    },
    [recoverSessionJob]
  );

  const reloadSessions = useCallback(async () => {
    const generation = ++loadGeneration.current;
    setLoading(true);
    setError(null);
    const history = await sovereignClient.getChatHistory();
    if (!mounted.current || generation !== loadGeneration.current) return;
    if (!history.ok) {
      setSessions([]);
      setActiveId(null);
      setError(history.error ?? "Unable to load sessions from Sovereign.");
      setLoading(false);
      return;
    }

    let serverSessions = sortSessions(history.sessions);
    if (serverSessions.length === 0) {
      const created = await sovereignClient.createSession();
      if (!mounted.current || generation !== loadGeneration.current) return;
      if (!created.ok || !created.session) {
        setSessions([]);
        setActiveId(null);
        setError(created.error ?? "Unable to create a server session.");
        setLoading(false);
        return;
      }
      serverSessions = [created.session];
    }

    setSessions(serverSessions);
    const selected =
      (activeId &&
        serverSessions.find((session) => session.session_id === activeId)) ||
      serverSessions[0];
    setActiveId(selected.session_id);
    setLoading(false);
    await refreshSession(selected.session_id, false);
  }, [activeId, refreshSession]);

  useEffect(() => {
    mounted.current = true;
    void reloadSessions();
    return () => {
      mounted.current = false;
      loadGeneration.current += 1;
    };
    // One bootstrap only. User-triggered reloads use reloadSessions directly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const createChat = useCallback(async () => {
    if (creating) return;
    setCreating(true);
    setError(null);
    try {
      const result = await sovereignClient.createSession();
      if (!mounted.current) return;
      if (!result.ok || !result.session) {
        setError(result.error ?? "Unable to create a server session.");
        return;
      }
      setSessions((previous) => upsertSession(previous, result.session!));
      setActiveId(result.session.session_id);
      setRouteOverride("AUTO");
    } finally {
      if (mounted.current) setCreating(false);
    }
  }, [creating]);

  const selectChat = useCallback(
    async (id: string) => {
      setActiveId(id);
      setError(null);
      setPollError(null);
      await refreshSession(id);
    },
    [refreshSession]
  );

  const sendMessage = useCallback(
    async (input: string) => {
      const trimmed = input.trim();
      if (
        !trimmed ||
        !active ||
        submitting ||
        (activeJob && isActiveJobStatus(activeJob.status))
      ) {
        return;
      }

      const sessionId = active.session_id;
      setSubmitting(true);
      setError(null);
      setPollError(null);
      try {
        const result = await sovereignClient.sendMessage(
          trimmed,
          sessionId,
          routeOverride
        );
        if (!mounted.current) return;

        if (result.job) {
          adoptJob(sessionId, result.job);
        } else if (result.status) {
          adoptJob(sessionId, {
            job_id: `${result.status}-${Date.now()}`,
            session_id: sessionId,
            status: result.status,
            route: result.route,
            progress: { percent: result.status === "completed" ? 100 : 0 },
            message:
              result.status === "completed" ? result.message : undefined,
            evidence: result.message?.evidence,
            error: result.error,
          });
        }

        if (!result.ok) {
          setError(
            result.error ??
              `The ${result.route ?? "selected"} route did not accept the request.`
          );
          await refreshSession(sessionId, false);
          return;
        }

        const refreshed = await refreshSession(sessionId, false);
        if (!refreshed && result.status === "completed" && result.message) {
          // The direct response is itself authoritative server output. Keep it
          // visible if the follow-up refresh was transiently unavailable.
          setSessions((previous) =>
            previous.map((session) =>
              session.session_id === sessionId
                ? {
                    ...session,
                    messages: acceptedMessage(
                      session.messages,
                      result.message!
                    ),
                  }
                : session
            )
          );
          setPollError("Session refresh failed; reconnecting will verify persistence.");
        }
      } finally {
        if (mounted.current) setSubmitting(false);
      }
    },
    [
      active,
      activeJob,
      adoptJob,
      refreshSession,
      routeOverride,
      submitting,
    ]
  );

  const cancelActiveJob = useCallback(async () => {
    if (
      !active ||
      !activeJob ||
      !isActiveJobStatus(activeJob.status) ||
      cancelling
    ) {
      return;
    }
    setCancelling(true);
    setError(null);
    try {
      const result = await sovereignClient.cancelJob(activeJob.job_id);
      if (!mounted.current) return;
      if (result.job) adoptJob(active.session_id, result.job);
      if (!result.ok) {
        setError(result.error ?? "Sovereign could not cancel this run.");
      }
      await refreshSession(active.session_id, false);
    } finally {
      if (mounted.current) setCancelling(false);
    }
  }, [
    active,
    activeJob,
    adoptJob,
    cancelling,
    refreshSession,
  ]);

  useEffect(() => {
    if (
      !active ||
      !activeJob ||
      !isActiveJobStatus(activeJob.status) ||
      activeJob.job_id.startsWith("accepted-")
    ) {
      return;
    }

    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      const result = await sovereignClient.getJob(activeJob.job_id);
      if (cancelled || !mounted.current) return;
      if (!result.ok || !result.job) {
        setPollError(
          result.error ??
            "Connection lost while checking the run; retrying automatically."
        );
        timer = window.setTimeout(poll, JOB_POLL_INTERVAL_MS * 2);
        return;
      }

      setPollError(null);
      adoptJob(active.session_id, result.job);
      if (isActiveJobStatus(result.job.status)) {
        timer = window.setTimeout(poll, JOB_POLL_INTERVAL_MS);
      } else {
        await refreshSession(active.session_id, false);
      }
    };

    timer = window.setTimeout(poll, JOB_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [
    active?.session_id,
    activeJob?.job_id,
    activeJob?.status,
    adoptJob,
    refreshSession,
  ]);

  return {
    sessions,
    active,
    activeJob,
    routeOverride,
    loading,
    creating,
    submitting,
    cancelling,
    error,
    pollError,
    createChat,
    selectChat,
    sendMessage,
    cancelActiveJob,
    setRouteOverride,
    reloadSessions,
  };
}
