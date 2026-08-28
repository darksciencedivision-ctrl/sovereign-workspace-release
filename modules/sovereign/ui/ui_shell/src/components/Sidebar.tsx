import type { ChatSession } from "../types/chat";

interface Props {
  sessions: ChatSession[];
  activeId: string;
  onNewChat: () => void;
  onSelect: (id: string) => void;
}

export function Sidebar({ sessions, activeId, onNewChat, onSelect }: Props) {
  return (
    <nav className="sidebar" aria-label="Chat history">
      <button className="new-chat" onClick={onNewChat}>
        + New Chat
      </button>
      <div className="section-label">History</div>
      <div className="session-list">
        {sessions.length === 0 ? (
          <div className="empty-note">No previous sessions</div>
        ) : (
          sessions.map((s) => {
            const job = s.active_job ?? s.last_job;
            return (
            <button
              key={s.session_id}
              className={
                "session-item" + (s.session_id === activeId ? " active" : "")
              }
              aria-current={s.session_id === activeId ? "page" : undefined}
              onClick={() => onSelect(s.session_id)}
              title={s.title}
            >
              <span>{s.title}</span>
              {job && (
                <span className={`session-status status-${job.status}`}>
                  {job.status}
                </span>
              )}
            </button>
            );
          })
        )}
      </div>
    </nav>
  );
}
